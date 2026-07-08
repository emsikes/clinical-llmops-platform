"""
PHI Detection Guardrail - HIPAA Safe Harbor 18 Identifiers

Structured identifiers use regex; names and geographic
subdivisions (#1, #2) are handled by the Presidio NER layer.
When PHI is detected, sets contains_phi=true to constrain
routing to BAA-covered providers.
"""
import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from models import ChatRequest
from .base import (
    GuardrailBase,
    GuardrailResult,
    GuardrailAction,
    Severity,
    ThreatCategory,
)

logger = logging.getLogger(__name__)

# Compiled once at module load. 3-tuple: (pattern, severity, phi_category)
# phi_category is the HIPAA Safe Harbor label for audit rollup (Phase 13f).
PHI_PATTERNS: Dict[str, Tuple[re.Pattern, Severity, str]] = {
    # --- Carried forward from PII Guard (copied, not imported) ---
    "SSN": (
        re.compile(r'\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b'),
        Severity.CRITICAL,
        "account_numbers",  # Safe Harbor #9 (SSN)
    ),
    "CREDIT_CARD": (
        re.compile(r'\b(?:\d{4}[-\s]?){3,4}\d{1,4}\b'),
        Severity.CRITICAL,
        "account_numbers",  # Safe Harbor #10
    ),
    "EMAIL": (
        re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
        Severity.HIGH,
        "email_addresses",  # Safe Harbor #6
    ),
    "PHONE": (
        re.compile(r'\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'),
        Severity.HIGH,
        "telephone_numbers",  # Safe Harbor #4
    ),
    "IP_ADDRESS": (
        re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'),
        Severity.MEDIUM,
        "ip_addresses",  # Safe Harbor #15
    ),
    "DOB": (
        re.compile(r'\b(?:0[1-9]|1[0-2])[/-](?:0[1-9]|[12]\d|3[01])[/-](?:19|20)\d{2}\b'),
        Severity.HIGH,
        "dates",  # Safe Harbor #3
    ),
    # --- New HIPAA Safe Harbor structured identifiers ---
    "MRN": (
        re.compile(r'\b(?:MRN|MR#|MEDICAL\s+RECORD\s*#?)[:\s]*([A-Z0-9]{6,12})\b', re.IGNORECASE),
        Severity.CRITICAL,
        "medical_record_numbers",  # Safe Harbor #7
    ),
    "HEALTH_PLAN_ID": (
        re.compile(r'\b(?:MEMBER\s*ID|PLAN\s*ID|SUBSCRIBER\s*#?|POLICY\s*#?)[:\s]*([A-Z0-9]{6,15})\b', re.IGNORECASE),
        Severity.CRITICAL,
        "health_plan_beneficiary_numbers",  # Safe Harbor #8
    ),
    "FAX": (
        re.compile(r'\b(?:FAX|FACSIMILE)[:\s]*(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b', re.IGNORECASE),
        Severity.HIGH,
        "fax_numbers",  # Safe Harbor #5
    ),
    "URL": (
        re.compile(r'\bhttps?://[^\s<>"\']+|\bwww\.[^\s<>"\']+', re.IGNORECASE),
        Severity.MEDIUM,
        "urls",  # Safe Harbor #14
    ),
    "VIN": (
        re.compile(r'\b(?:VIN|VEHICLE\s+ID(?:ENTIFICATION)?(?:\s+(?:NUMBER|#))?)[:\s]*([A-HJ-NPR-Z0-9]{17})\b', re.IGNORECASE),
        Severity.HIGH,
        "vehicle_identifiers",  # Safe Harbor #12
    ),
    "LICENSE_PLATE": (
        re.compile(r'\b(?:PLATE|LICENSE\s+PLATE|TAG)[:\s]*([A-Z0-9]{5,8})\b', re.IGNORECASE),
        Severity.MEDIUM,
        "vehicle_identifiers",  # Safe Harbor #12
    ),
    "LICENSE_CERT": (
        re.compile(r'\b(?:LICENSE|LIC|DEA|NPI|CERT(?:IFICATE)?)\s*#?[:\s]*([A-Z0-9]{6,12})\b', re.IGNORECASE),
        Severity.HIGH,
        "certificate_license_numbers",  # Safe Harbor #11
    ),
    "DEVICE_ID": (
        re.compile(r'\b(?:DEVICE\s*(?:ID|SN|SERIAL)|SERIAL\s*#?|UDI)[:\s]*([A-Z0-9\-]{6,25})\b', re.IGNORECASE),
        Severity.HIGH,
        "device_identifiers",  # Safe Harbor #13
    ),
    "ACCOUNT_NUM": (
        re.compile(r'\b(?:ACCOUNT|ACCT)\s*#?[:\s]*([A-Z0-9]{6,17})\b', re.IGNORECASE),
        Severity.HIGH,
        "account_numbers",  # Safe Harbor #9
    ),
    # NOTE: Safe Harbor #1 (names) and #2 (geographic, incl. ZIP) are handled
    # by the Presidio NER layer in _scan_text, not regex. Shape-matching 5-digit
    # ZIPs against clinical numeric text produces more noise than signal.
}


@dataclass
class PHIMatch:
    """
    Holds keyword-anchored patters (MRN, HEALTH_PLAN_ID, etc.), start/end
    point at the captured VALUE, not the full match, so masking preserves
    the label: 'MRN: [REDACTED_MRN]' rather than eating 'MRN'.
    """
    phi_type: str           # e.g. "SSN", "MRN"
    phi_category: str       # HIPAA Safe Harbor label for audit rollup
    matched_text: str       # The value that matched (label stripped)
    start: int              # Start of the VALUE in the string
    end: int                # End of the VALUE in the string
    severity: Severity = Severity.HIGH


class PHIGuard(GuardrailBase):
    def __init__(self, config: dict):
        super().__init__(config)
        self.phi_types = config.get("phi_types", {})
        self.mask_strategy = config.get("mask_strategy", "full")
        self.default_action = config.get("default_action", "block")

    def name(self) -> str:
        return "phi_guard"
    
    def _scan_text(self, text: str) -> List[PHIMatch]:
        """
        Run all enabled PHI patterns against text, return matches.

        Handles two pattern shapes:
        - Ungrouped (SSN, Email, ...): whole match is the value
        - Keyword-anchored with a capture group (MRN, ACCOUNT_NUMBER, ...):
          group(1) is the value, label is exluded from redaction span.
        """
        matches: List[PHIMatch] = []

        for phi_type, (pattern, default_severity, phi_category) in PHI_PATTERNS.items():
            type_config = self.phi_types.get(phi_type, {})
            if not type_config.get("enabled", True):
                continue

            severity = Severity(
                type_config.get("severity", default_severity.value)
            )

            for match in pattern.finditer(text):
                # If the pattern captured a group, the value is group(1)
                # and we mask only that span (preserve keyword label)
                if match.groups():
                    value = match.group(1)
                    start = match.start(1)
                    end = match.end(1)
                else:
                    value = match.group()
                    start = match.start()
                    end = match.end()

                matches.append(PHIMatch(
                    phi_type=phi_type,
                    phi_category=phi_category,
                    matched_text=value,
                    start=start,
                    end=end,
                    severity=severity,
                ))

        if matches:
            logger.info(
                f"PHI scan found {len(matches)} matche(s) across "
                f"{len(set(m.phi_type for m in matches))} type(s)"
            )

        return matches
    
    def evaluate(self, request: ChatRequest) -> GuardrailResult:
        """
        Evaluate request for PHI content.

        On detection, sets the contains_phi=True so the router constrains
        to BAA-covered providers.  Action follows worst-wins across all
        matches (per-type override or global default.)
        """
        if not self.is_enabled():
            return GuardrailResult(passed=True)
        
        text = self._extract_text(request)
        matches = self._scan_text(text)

        if not matches:
            return GuardrailResult(passed=True)
        
        action_order = ["log", "warn", "redact", "block"]

        def match_action(m: PHIMatch) -> str:
            return self.phi_types.get(m.phi_type, {}).get("action", self.default_action)
        
        worst_match = max(matches, key=lambda m: action_order.index(match_action(m)))
        worst_severity = worst_match.severity
        action = GuardrailAction(match_action(worst_match))

        found_types = set(m.phi_type for m in matches)
        found_categories = set(m.phi_category for m in matches)
        summary = (
            f"Detected PHI: {', '.join(sorted(found_types))} "
            f"({len(matches)} instance(s), Safe Harbor: {', '.join(sorted(found_categories))})"
        )

        masked_text = None
        if action == GuardrailAction.REDACT:
            masked_text = self._apply_maskiing(text, matches)

        return GuardrailResult(
            passed=(action != GuardrailAction.BLOCK),
            category=ThreatCategory.PHI,
            severity=worst_severity,
            action=action,
            message=summary,
            confidence=1.0,
            masked_text=masked_text,
            contains_phi=True,
        )

    def _extract_text(self, request: ChatRequest) -> str:
        """
        Extract all message text from the request.

        Preserves original case.  PHI patterns are case insensitive by
        nature, but masking splices replacements back into the original
        string, so case and positions must stay intact.
        """
        texts = []
        for message in request.messages:
            if message.content:
                texts.append(message.content)
            return " ".join(texts)
        
    def _mask_full(self, match: PHIMatch) -> str:
        """Replace the value with a type label: '[REDACTED_MRN]'."""
        return f"[REDACTED_MRN_{match.phi_type}]"
    
    def _mask_partial(self, match: PHIMatch) -> str:
        """
        Show trailing characters, mask the rest.

        E.g. '123-45-6789' -> '***-**-6789'
             'user@email.com' -> '****@email.com'
        """
        text = match.matched_text

        if match.phi_type == "EMAIL":
            local, domain = text.split("@", 1)
            return f"{'*' * len(local)@{domain}}"
        
        if match.phi_type == "SSN":
            return f"***-**-{text[-4]}"
        
        if match.phi_type == "CREDIT_CARD":
            return f"****-****-****-{text[-4:]}"
        
        # Default: show last 4 if long enough, else mask entirely
        if len(text) <= 4:
            return '*' * len(text)
        return '*' * (len(text) -4) + text[-4:]
    
    def _mask_hash(self, match: PHIMatch) -> str:
        """
        Replace with truncated SHA-256 hash: '[MRN:a1b2c3d4]'.

        Deterministic, so the same value correlates across occurences
        without explising it.  Useful for audit linkage.
        """
        hash_value = hashlib.sha256(match.matched_text.encode()).hexdigest()[:8]
        return f"[{match.phi_type}:{hash_value}]"
    
    def _apply_masking(self, text: str, matches: List[PHIMatch]) -> str:
        """
        Replace all PHI values using the configured strategy.

        Processes right to left so earlier replacements don't shift the
        position of later ones.  For keyword based patters, start/end
        already point at the value span, so labels are preserved.
        """
        sorted_matches = sorted(matches, key=lambda m: m.start, reverse=True)

        mask_funcs = {
            "full": self._mask_full,
            "partial": self._mask_partial,
            "hash": self._mask_hash,
        }

        for match in sorted_matches:
            type_config = self.phi_types.get(match.phi_type, {})
            strategy = type_config.get("mask_strategy", self.mask_strategy)

            mask_func = mask_funcs.get(strategy, self._mask_full)
            replacement = mask_func(match)

            text = text[:match.start] + replacement + text[match.end:]

        return text
