"""LLM input and output safety checks for production website / coding chat.

Runs before model calls (input) and before file apply (output). Heuristics are
intentionally conservative on high-severity labels (injection, abuse, secrets,
path traversal, phishing) while allowing normal website-builder briefs.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

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
        r"print\s+(your\s+)?(system|developer|hidden)\s+prompt",
        r"jailbreak",
        r"dan\s+mode",
        r"developer\s+mode\s+enabled",
        r"exfiltrat(e|ion)",
        r"do\s+not\s+follow\s+(the\s+)?(safety|content)\s+policy",
        r"override\s+(your\s+)?(safety|content)\s+(filters|policies|guidelines)",
        r"you\s+are\s+now\s+unrestricted",
        r"act\s+as\s+if\s+you\s+have\s+no\s+restrictions",
        r"bypass\s+(your\s+)?(safety|guardrails|filters|moderation)",
        r"pretend\s+(you\s+are|to\s+be)\s+(unfiltered|uncensored|jailbroken)",
        r"new\s+persona[:\s].{0,40}(no\s+rules|no\s+limits|uncensored)",
        r"system\s*:\s*you\s+are\s+now",
        r"<\s*/?\s*system\s*>",
        r"\[(?:system|developer|INST)\]",
    )
]

# High-severity abuse / illegal intent (not ordinary website copy).
_ABUSE_PATTERNS: List[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\b(child\s*porn|csam|underage\s+sex|sexual(?:ly)?\s+(?:with\s+)?(?:a\s+)?(?:minor|child))\b",
        r"\b(how\s+to\s+(make|build)\s+(a\s+)?(bomb|explosive|weapon))\b",
        r"\b(credit\s*card\s+(stuffing|skimmer)|carding\s+tutorial)\b",
        r"\b(ransomware|keylogger)\b.{0,40}\b(build|create|generate|deploy)\b",
        r"\b(phishing\s+(page|kit|site)|clone\s+(a\s+)?(bank|paypal|login)\s+page\s+to\s+steal)\b",
        r"\bsteal\s+(passwords|credentials|credit\s*cards)\b",
    )
]

# Harassment / slur-heavy prompts that are the request itself (not site content).
_PROFANITY_HEAVY = re.compile(
    r"(?:\b(?:fuck|shit|bitch|asshole|cunt|motherfucker)\b.*){3,}",
    re.IGNORECASE | re.DOTALL,
)

_SECRET_PATTERNS: List[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"sk-[a-zA-Z0-9]{20,}",
        r"sk-proj-[a-zA-Z0-9_-]{20,}",
        r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----",
        r"ghp_[a-zA-Z0-9]{20,}",
        r"github_pat_[a-zA-Z0-9_]{20,}",
        r"xox[baprs]-[a-zA-Z0-9-]{10,}",
        r"AKIA[0-9A-Z]{16}",
        r"AIza[0-9A-Za-z\-_]{30,}",
        r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
    )
]

# Dangerous patterns in generated website/code output (real-world misuse).
_OUTPUT_MALICE_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    (
        "phishing_pattern",
        re.compile(
            r"(verify\s+your\s+account|enter\s+your\s+(password|ssn|social\s+security|"
            r"credit\s*card|cvv|pin)\s+here|urgent.{0,40}account\s+suspended)",
            re.IGNORECASE,
        ),
    ),
    (
        "credential_harvest",
        re.compile(
            r"(fetch|axios|XMLHttpRequest).{0,120}(password|passwd|credit.?card|ssn|"
            r"cardNumber|cvv).{0,80}(http|webhook|discord\.com/api/webhooks)",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "unsafe_eval",
        re.compile(
            r"\beval\s*\(|new\s+Function\s*\(|document\.write\s*\(\s*[^)]*location|"
            r"innerHTML\s*=\s*[^;]*(?:location\.|document\.URL|document\.cookie)",
            re.IGNORECASE,
        ),
    ),
    (
        "crypto_miner",
        re.compile(r"coinhive|cryptonight|wasm.?miner|mine\.js", re.IGNORECASE),
    ),
    (
        "malware_hint",
        re.compile(
            r"(keydown.?logger|key.?logger|steal.?cookie|exfiltrat)",
            re.IGNORECASE,
        ),
    ),
]

# Refusal shown whenever a turn would reveal, invent, or hard-code a credential
# or personally identifiable information.
RESPONSIBLE_AI_MESSAGE = (
    "API keys and PII is not under responsible AI. I can't reveal, invent, or "
    "hard-code credentials or personal data. I can wire the code to read them "
    "from an environment variable or a secrets manager instead."
)

_SECRET_TARGET = (
    r"(?:\b(?:api[\s_-]?keys?|secret[\s_-]?keys?|private[\s_-]?keys?|"
    r"access[\s_-]?tokens?|auth(?:orization)?[\s_-]?tokens?|bearer[\s_-]?tokens?|"
    r"client[\s_-]?secrets?|credentials?|passwords?|passphrases?|openai[\s_-]?keys?|"
    r"(?:aws[\s_-]?)?(?:secret[\s_-]?)?access[\s_-]?keys?|aws[\s_-]?keys?|"
    r"dotenv)\b|\.env\b)"
)

_PII_TARGET = (
    r"\b(?:pii|personally identifiable information|"
    r"personal (?:data|information|details)|social security numbers?|ssns?|"
    r"aadhaar(?:\s+numbers?)?|passport numbers?|credit[\s_-]?card numbers?|"
    r"card numbers?|cvv|bank account numbers?|driver'?s licen[cs]e numbers?|"
    r"national id numbers?|tax id numbers?)\b"
)

_DISCLOSE_VERBS = (
    r"reveal|show|display|print|log|expose|leak|dump|list|output|share|send|"
    r"give|tell|paste|echo|what(?:'s| is| are)|hand over"
)

# Asking the assistant to hand over an existing secret or personal record.
_DISCLOSURE_PATTERNS: List[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in (
        rf"\b(?:{_DISCLOSE_VERBS})\b[^.\n]{{0,40}}{_SECRET_TARGET}",
        rf"\b(?:{_DISCLOSE_VERBS})\b[^.\n]{{0,40}}{_PII_TARGET}",
    )
]

# Asking the assistant to invent or bake a real credential / PII into the code.
# Never suppressed: hard-coding a secret is unsafe wherever it is written.
_FABRICATION_PATTERNS: List[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in (
        rf"\b(?:hard[\s_-]?cod(?:e|ing)|inline|embed|bake|paste)\b"
        rf"[^.\n]{{0,40}}{_SECRET_TARGET}",
        rf"\b(?:generate|create|make|invent|fabricate|provide|need|want|get me)\b"
        rf"[^.\n]{{0,30}}\b(?:real|valid|working|live|actual|free|new)\b"
        rf"[^.\n]{{0,20}}{_SECRET_TARGET}",
        rf"\b(?:generate|create|make|invent|fabricate|produce|list|give)\b"
        rf"[^.\n]{{0,40}}{_PII_TARGET}",
    )
]

# Ordinary secret *plumbing* is legitimate and must not be refused.
_SAFE_SECRET_USAGE = re.compile(
    r"\b(?:from|via|using|with|through|in|into)\s+(?:the\s+|an?\s+|your\s+)?"
    r"(?:env(?:ironment)?(?:\s+variables?)?|\.env|os\.environ|os\.getenv|"
    r"process\.env|dotenv|secrets?\s+manager|vault|keyring|keychain)\b",
    re.IGNORECASE,
)

_UNSAFE_PATH = re.compile(r"(^|/)\.\.(/|$)|^/|^~|[\x00-\x1f]")
_EXECUTABLE_EXTS = re.compile(
    r"\.(?:exe|dll|bat|cmd|ps1|sh|bash|msi|apk|ipa|wasm)$",
    re.IGNORECASE,
)
_MAX_FILE_CHANGES = 25
_MAX_FILE_CONTENT_CHARS = 200_000
_MAX_INPUT_CHARS = 7000


@dataclass
class GuardResult:
    """Result of a guardrail check.

    Attributes:
        allowed: Whether the content may proceed.
        reason: Human-readable explanation when blocked or flagged.
        score: Risk score in [0, 1].
        labels: Machine-readable risk labels.
        sanitized_text: Optional cleaned input when sanitization ran.
    """

    allowed: bool = True
    reason: str = ""
    score: float = 0.0
    labels: List[str] = field(default_factory=list)
    sanitized_text: Optional[str] = None

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


def sanitize_user_input(user_text: str) -> str:
    """Normalize and strip hazardous control characters from user chat input.

    Removes null bytes / most C0 controls (keeps tab/newline), normalizes Unicode,
    and collapses pathological whitespace. Does not change legitimate website briefs.

    Args:
        user_text: Raw user message.

    Returns:
        Sanitized text safe to pass into the LLM pipeline.
    """
    text = user_text or ""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\x00", "")
    text = "".join(
        ch
        for ch in text
        if ch in "\t\n\r" or unicodedata.category(ch)[0] != "C"
    )
    # Neutralize common delimiter injection wrappers without deleting the brief.
    text = re.sub(r"<\s*/?\s*system\s*>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\[(?:SYSTEM|DEV|INST)\]", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"[ \t]{3,}", "  ", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


def check_sensitive_data_request(user_text: str) -> GuardResult:
    """Detect requests to reveal, invent, or hard-code credentials or PII.

    Reading a secret from an environment variable or secrets manager is normal
    application work and stays allowed; only disclosure and fabrication of real
    key material or personal data is refused.

    Args:
        user_text: Raw user message.

    Returns:
        GuardResult carrying ``RESPONSIBLE_AI_MESSAGE`` when the request is refused.
    """
    text = sanitize_user_input(user_text)
    if not text:
        return GuardResult(allowed=True, score=0.0)

    fabricates = any(pattern.search(text) for pattern in _FABRICATION_PATTERNS)
    discloses = any(pattern.search(text) for pattern in _DISCLOSURE_PATTERNS)
    if discloses and _SAFE_SECRET_USAGE.search(text):
        discloses = False
    if not fabricates and not discloses:
        return GuardResult(allowed=True, score=0.0)

    return GuardResult(
        allowed=False,
        reason=RESPONSIBLE_AI_MESSAGE,
        score=1.0,
        labels=["sensitive_data_request"],
        sanitized_text=text,
    )


def check_input(user_text: str) -> GuardResult:
    """Sanitize then detect jailbreak / abuse / oversized user input.

    Args:
        user_text: Raw user message.

    Returns:
        GuardResult with allow/block decision and ``sanitized_text`` when allowed.
    """
    sanitized = sanitize_user_input(user_text)
    if not sanitized:
        return GuardResult(
            allowed=False,
            reason="Empty input after sanitization",
            score=1.0,
            labels=["empty"],
            sanitized_text=sanitized,
        )

    labels: List[str] = []
    score = 0.0

    for pattern in _INJECTION_PATTERNS:
        if pattern.search(sanitized):
            labels.append("prompt_injection")
            score = max(score, 0.95)
            break

    for pattern in _ABUSE_PATTERNS:
        if pattern.search(sanitized):
            labels.append("abuse_intent")
            score = max(score, 0.98)
            break

    if _PROFANITY_HEAVY.search(sanitized):
        labels.append("inappropriate_language")
        score = max(score, 0.9)

    # Raw control-char floods (before sanitization) are suspicious.
    raw = user_text or ""
    if sum(1 for ch in raw if ch == "\x00" or (ord(ch) < 32 and ch not in "\t\n\r")) > 8:
        labels.append("malicious_input")
        score = max(score, 0.9)

    if len(sanitized) > _MAX_INPUT_CHARS:
        labels.append("oversized_input")
        score = max(score, 0.4)

    if labels and score >= 0.85:
        reason = "Request blocked by input safety policy"
        if "prompt_injection" in labels:
            reason = "Potential jailbreak / prompt-injection detected"
        elif "abuse_intent" in labels:
            reason = "Request blocked: unsafe or illegal intent"
        elif "inappropriate_language" in labels:
            reason = "Please rephrase without abusive language and describe the website you need"
        elif "malicious_input" in labels:
            reason = "Request blocked: malformed or malicious input"
        return GuardResult(
            allowed=False,
            reason=reason,
            score=score,
            labels=sorted(set(labels)),
            sanitized_text=sanitized,
        )
    if labels:
        return GuardResult(
            allowed=True,
            reason="Flagged but allowed",
            score=score,
            labels=sorted(set(labels)),
            sanitized_text=sanitized,
        )
    return GuardResult(allowed=True, score=0.0, sanitized_text=sanitized)


def check_output(
    raw_content: str,
    file_changes: Optional[Sequence[FileChangeProposal]] = None,
) -> GuardResult:
    """Validate model output before applying file changes.

    Blocks secret leaks, path traversal, oversized payloads, and common
    real-world website misuse patterns (phishing, credential harvest, miners).

    Args:
        raw_content: Full assistant raw text.
        file_changes: Parsed file change proposals.

    Returns:
        GuardResult with allow/block decision.
    """
    labels: List[str] = []
    score = 0.0
    text = raw_content or ""
    changes = list(file_changes or [])
    combined = text + "\n" + "\n".join((c.content or "") for c in changes)

    for pattern in _SECRET_PATTERNS:
        if pattern.search(combined):
            labels.append("secret_leak")
            score = max(score, 0.95)
            break

    for label, pattern in _OUTPUT_MALICE_PATTERNS:
        if pattern.search(combined):
            labels.append(label)
            score = max(score, 0.92)

    if len(changes) > _MAX_FILE_CHANGES:
        labels.append("too_many_file_changes")
        score = max(score, 0.9)

    for change in changes:
        path = (change.path or "").strip()
        if not path or _UNSAFE_PATH.search(path) or "\\" in path:
            labels.append("unsafe_path")
            score = max(score, 0.95)
            break
        if _EXECUTABLE_EXTS.search(path):
            labels.append("unsafe_file_type")
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
            reason=(
                RESPONSIBLE_AI_MESSAGE
                if "secret_leak" in labels
                else "Output failed safety checks"
            ),
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
