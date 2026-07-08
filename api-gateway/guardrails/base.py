"""
Base class for all guardrails
Defines the interface that content_safety, pii_guard, etc. will implement
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from models import ChatRequest


class ThreatCategory(str, Enum):
    """Categories of content threats = aligned with guardrails-settings.yaml"""
    SELF_HARM = "self_harm"
    VIOLENCE = "violence"
    HATE_SPEECH = "hate_speech"
    SEXUAL_CONTENT = "sexual_content"
    ILLEGAL_ACTIVITY = "illegal_activity"
    CONTROLLED_SUBSTANCES = "controlled_substances"
    WEAPONS = "weapons"
    CYBER_CRIME = "cyber_crimes"
    CHILD_SAFETY = "child_safety"
    TERRORISM = "terrorism"
    PROMPT_INJECTION = "prompt_injection"
    OFFENSIVE_LANGUAGE = "offensive_language"
    PII = "pii"
    PHI = "phi"


class Severity(str, Enum):
    """Define how serious the detected threat is"""
    CRITICAL = "critical"           # Immediate block, alert security team
    HIGH = "high"                   # Block request, log incident
    MEDIUM = "medium"               # Block or want based on config
    LOW = "low"                     # Log only, allow through


class GuardrailAction(str, Enum):
    """The action to take when content is flagged"""
    BLOCK = "block"                 # Reject request, return error to client (default for critical/high)
    WARN = "warn"                   # Allow through but log warning (Allow but flag for review)
    LOG = "log"                     # Silent logging, no immediate user impact (track over time)
    REDACT = "redact"               # Remove / mask flagged content, continue request (mask PII)


@dataclass
class GuardrailResult:
    """Standard result returned by all guardrails"""
    passed: bool                                # True = safe, False = flagged
    category: Optional[ThreatCategory] = None   # What was detected
    severity: Optional[Severity] = None         # How serious
    action: GuardrailAction = GuardrailAction.LOG   # What to do
    message: str = ""                           # Human readable explanation
    confidence: float = 0.0                     # 0.0-1.0 detection confidence 
    masked_text: Optional[str] = None           # Holds redacted text


class GuardrailBase(ABC):
    """Abstract base class all guardrails must implement"""

    def __init__(self, config: dict):
        """
        Initialize with configuration from guardrails-settings.yaml

        Args:
            config: Category settings loaded from ConfigMap
        """
        self.config = config
        self.enabled = config.get("enabled", True)

    @abstractmethod
    def evaluate(self, request: ChatRequest) -> GuardrailResult:
        """
        Evaluate a chat request for policy violations

        Args:
            request: The incoming ChatRequest to evaluate

        Returns:
            GuardrailResult with pass/fail and details
        """
        pass

    @abstractmethod
    def name(self) -> str:
        """Return the guardrail for logging"""
        pass

    def is_enabled(self) -> bool:
        """Check if this guardrail is enabled"""
        return self.enabled