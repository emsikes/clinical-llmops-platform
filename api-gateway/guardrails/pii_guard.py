"""PII Detection and Masking Guardrail"""

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from models import ChatRequest
from .base import (
    GuardrailBase, GuardrailResult, GuardrailAction, Severity, ThreatCategory,
)

logger = logging.getLogger(__name__)


@dataclass
class PIIMatch:
    """Holds single PII detection result."""
    pii_type: str       # e.g. "SSN", "EMAIL"
    matched_text: str   # The actual text that matched
    start: int          # Start position in the string
    end: int            # End position in the string
    severity: Severity = Severity.HIGH


# Compiled once at modul load - avoids recompiling on every request
PII_PATTERNS: Dict[str, Tuple[re.Pattern, Severity]] = {
    "SSN": (
        re.compile(r'\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b'),
        Severity.CRITICAL,  # PHI under HIPAA
    ),
    "CREDIT_CARD": (
        re.compile(r'\b(?:\d{4}[-\s]?){3,4}\d{1,4}\b'),
        Severity.CRITICAL,  # PCI-DSS
    ),
    "EMAIL": (
        re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
        Severity.HIGH,
    ),
    "PHONE": (
        re.compile(r'\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'),
        Severity.HIGH,
    ),
    "IP_ADDRESS": (
        re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'),
        Severity.MEDIUM,
    ),
    "DOB": (
        re.compile(r'\b(?:0[1-9]|1[0-2])[/-](?:0[1-9]|[12]\d|3[01])[/-](?:19|20)\d{2}\b'),
        Severity.HIGH   # PHI when combined with other data
    ),
}



class PIIGuard(GuardrailBase):
    def __init__(self, config: dict):
        super().__init__(config)
        self.pii_types = config.get("pii_types", {})
        self.mask_strategy = config.get("mask_strategy", "full")
        self.default_action = config.get("default_action", "block")

    def name(self) -> str:
        return "pii_guard"
    
    def evaluate(self, request: ChatRequest) -> GuardrailResult:
        """
        Evaluate request for PII content.

        Flow:
            1. Extract all message text
            2. Scan for PII matches
            3. If found, determine action:
                - BLOCK: reject the request entirely
                - REDACT: mask the PII, let the request continue
                - WARN: flag it but let it through
                - LOG: silently log, no user impact
        """   
        if not self.is_enabled():
            return GuardrailResult(passed=True)
        
        text = self._extract_text(request)
        matches = self._scan_text(text)

        if not matches:
            return GuardrailResult(passed=True)
        
        # Use the highest severity found accross all matches
        worst_severity = max(matches, key=lambda m: ["log", "warn", "redact", "block"].index(
            self.pii_types.get(m.pii_type, {}).get("action", self.default_action)
        )).severity

        # Determine action - per type override or global default
        worst_match = max(matches, key=lambda m: ["log", "warn", "redact", "block"].index(
            self.pii_types.get(m.pii_type, {}).get("action", self.default_action)
        ))

        action = GuardrailAction(
            self.pii_types.get(worst_match.pii_type, {}).get("action", self.default_action)
        )

        # Build summary of what was found
        found_types = set(m.pii_type for m in matches)
        summary = f"Detected PII: {', '.join(found_types)} ({len(matches)} instance(s))"

        # For REDACT action, mask the PII and attach cleaned text to result
        masked_text = None
        if action == GuardrailAction.REDACT:
            masked_text = self._apply_masking(text, matches)

        return GuardrailResult(
            passed=(action != GuardrailAction.BLOCK),
            category=ThreatCategory.PII,
            severity=worst_severity,
            action=action,
            message=summary,
            confidence=1.0,
            masked_text=masked_text,
        )
    
    def _extract_text(self, request: ChatRequest) -> str:
        """
        Extract all message text from the request.

        Unlike ContentSafetyGuard, we preserve original case.
        PII patterns (emails, SSNs, etc.) are case insensitive
        by nature, and we need original case intact for security masking -
        replacing text back into the message won't work if lowered
        """
        texts = []
        for message in request.messages:
            if message.content:
                texts.append(message.content)
        return " ".join(texts)

    def _scan_text(self, text: str) -> List[PIIMatch]:
        """
        Run all enabled PII patterns against text, return matches.
        
        Iterates through PII_PATTERNS, skipping any types disabled in config.
        Uses re.finditer() to catch ALL occurences, not just the first one.
        """
        matches: List[PIIMatch] = []

        for pii_type, (pattern, default_severity) in PII_PATTERNS.items():
            # Check if this PII type is enabled in config
            type_config = self.pii_types.get(pii_type, {})
            if not type_config.get("enabled", True):
                continue

            # Override severity from config if provided
            severity = Severity(
                type_config.get("severity", default_severity.value)
            )

            # Finditer gives us ALL matches along with the position
            for match in pattern.finditer(text):
                matches.append(PIIMatch(
                    pii_type=pii_type,
                    matched_text=match.group(),
                    start=match.start(),
                    end=match.end(),
                    severity=severity,
                ))

        if matches:
            logger.info(f"PII scan found {len(matches)} match(es) across {len(set(m.pii_type for m in matches))} type(s)")

        return matches
    
    def _mask_full(self, match: PIIMatch) -> str:
        """
        Repalce the entire match with a type label.
        
        E.g. - '123-45-6789' -> '[REDACTED_SSN]'
                'user@email.com' -> '[REDACTED_EMAIL]
        """
        return f"[REDACTED_{match.pii_type}]"
    
    def _mask_partial(self, match: PIIMatch) -> str:
        """
        Show the last few characters, mask the rest.

        E.g. '123-45-6789' -> '***-**-4444'
             '4111-2222-3333-4444' → '****-****-****-4444'
             'user@email.com' → '****@email.com'
            '(555) 123-4567' → '(***) ***-4567'
        """
        text = match.matched_text

        if match.pii_type == "EMAIL":
            local, domain = text.split("@", 1)
            return f"{'*' * len(local)}@{domain}"
        
        if match.pii_type == "SSN":
            return f"***-**-{text[-4:]}"
        
        if match.pii_type == "CREDIT_CARD":
            return f"****-****-****-{text[-4:]}"
        
        # Default: show last 4, mask the rest
        if len(text) < 4:
            return '*' * (len(text) - 4) + text[-4]
        
        return '*' * len(text)
    
    def _mask_hash(self, match: PIIMatch) -> str:
        """
        Replace with truncated SHA-256 hash.

        '123-45-6789' -> '[SSN:a1b2c3d4]'

        Same input always produces the same hash, useful for
        deduplication or correlation with exposing the value
        """
        hash_value = hashlib.sha256(match.matched_text.encode()).hexdigest()[:8]
        return f"[{match.pii_type}:{hash_value}]"
    
    def _apply_masking(self, text: str, matches: List[PIIMatch]) -> str:
        """
        Replace all PII matches in text using the configured masking strategy.

        Processes matches in reverse order (right to left) so that
        replacing earlier matches doesn't shift the positions of later ones.
        """
        # Sort by start position, descending
        sorted_matches = sorted(matches, key=lambda m: m.start, reverse=True)

        # Pick the masking function
        mask_funcs = {
            "full": self._mask_full,
            "partial": self._mask_partial,
            "hash": self._mask_hash,
        }

        for match in sorted_matches:
            # Per type strategy overrides from config, fall back to global
            type_config = self.pii_types.get(match.pii_type, {})
            strategy = type_config.get("mask_strategy", self.mask_strategy)

            mask_func = mask_funcs.get(strategy, self._mask_full)
            replacement = mask_func(match)

            # Splice the replacement
            text = text [:match.start] + replacement + text[match.end:]

        return text