"""LLM input and output safety checks."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from app.schemas.chat import FileChangeProposal

# Heuristic prompt-injection / jailbreak patterns (case-insensitive).
_INJECTION_PATTERNS: List[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
        r"disregard\s+(all\s+)?(previous|prior|your)\s+(instructions|rules|prompt)",
        r"forget\s+(everything|your\s+instructions|the\s+system\s+prompt)",
        r"reveal\s+(your\s+)?(system\s+)?prompt",
        r"show\s+(me\s+)?(your\s+)?(hidden\s+)?system\s+prompt",
        r"jailbreak",
        r"dan\s+mode",
        r"developer\s+mode\s+enabled",
        r"exfiltrat(e|ion)",
        r"do\s+not\s+follow\s+(the\s+)?(safety|content)\s+policy",
        r"override\s+(your\s+)?(safety|content)\s+(filters|policies|guidelines)",
        r"you\s+are\s+now\s+unrestricted",
        r"act\s+as\s+if\s+you\s+have\s+no\s+restrictions",
    )
]

_SECRET_PATTERNS: List[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"sk-[a-zA-Z0-9]{20,}",
        r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----",
        r"ghp_[a-zA-Z0-9]{20,}",
        r"xox[baprs]-[a-zA-Z0-9-]{10,}",
        r"AKIA[0-9A-Z]{16}",
    )
]

_UNSAFE_PATH = re.compile(r"(^|/)\.\.(/|$)|^/|^~")
_MAX_FILE_CHANGES = 25
_MAX_FILE_CONTENT_CHARS = 200_000


@dataclass
class GuardResult:
    """Result of a guardrail check.

    Attributes:
        allowed: Whether the content may proceed.
        reason: Human-readable explanation when blocked or flagged.
        score: Risk score in [0, 1].
        labels: Machine-readable risk labels.
    """

    allowed: bool = True
    reason: str = ""
    score: float = 0.0
    labels: List[str] = field(default_factory=list)

    def to_metadata(self, prefix: str) -> dict:
        """Serialize for chat/trace metadata.

        Args:
            prefix: Attribute prefix (e.g. input / output).

        Returns:
            Flat metadata dict.
        """
        return {
            f"guardrail_{prefix}_allowed": self.allowed,
            f"guardrail_{prefix}_score": self.score,
            f"guardrail_{prefix}_labels": ",".join(self.labels),
            f"guardrail_{prefix}_reason": self.reason or "",
        }


def message_fingerprint(text: str) -> str:
    """Return a short SHA-256 fingerprint of user text.

    Args:
        text: Raw user content.

    Returns:
        First 16 hex chars of the digest.
    """
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


def check_input(user_text: str) -> GuardResult:
    """Detect likely prompt-injection / jailbreak attempts in user input.

    Args:
        user_text: Raw user message.

    Returns:
        GuardResult with allow/block decision.
    """
    text = (user_text or "").strip()
    if not text:
        return GuardResult(allowed=False, reason="Empty input", score=1.0, labels=["empty"])

    labels: List[str] = []
    score = 0.0
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            labels.append("prompt_injection")
            score = max(score, 0.9)
            break

    if len(text) > 7000:
        labels.append("oversized_input")
        score = max(score, 0.4)

    if labels and score >= 0.85:
        return GuardResult(
            allowed=False,
            reason="Potential prompt injection detected",
            score=score,
            labels=labels,
        )
    if labels:
        return GuardResult(
            allowed=True,
            reason="Flagged but allowed",
            score=score,
            labels=labels,
        )
    return GuardResult(allowed=True, score=0.0)


def check_output(
    raw_content: str,
    file_changes: Optional[Sequence[FileChangeProposal]] = None,
) -> GuardResult:
    """Validate model output before applying file changes.

    Args:
        raw_content: Full assistant raw text.
        file_changes: Parsed file change proposals.

    Returns:
        GuardResult with allow/block decision.
    """
    labels: List[str] = []
    score = 0.0
    text = raw_content or ""

    for pattern in _SECRET_PATTERNS:
        if pattern.search(text):
            labels.append("secret_leak")
            score = max(score, 0.95)
            break

    changes = list(file_changes or [])
    if len(changes) > _MAX_FILE_CHANGES:
        labels.append("too_many_file_changes")
        score = max(score, 0.9)

    for change in changes:
        path = (change.path or "").strip()
        if not path or _UNSAFE_PATH.search(path) or "\\" in path:
            labels.append("unsafe_path")
            score = max(score, 0.95)
            break
        content = change.content or ""
        if len(content) > _MAX_FILE_CONTENT_CHARS:
            labels.append("oversized_file_content")
            score = max(score, 0.85)
            break

    if labels and score >= 0.85:
        return GuardResult(
            allowed=False,
            reason="Output failed safety checks",
            score=score,
            labels=sorted(set(labels)),
        )
    if labels:
        return GuardResult(
            allowed=True,
            reason="Flagged but allowed",
            score=score,
            labels=sorted(set(labels)),
        )
    return GuardResult(allowed=True, score=0.0)
