from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

SECRET_MARKER = "[REDACTED_SECRET]"

_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN(?: [A-Z0-9]+)* PRIVATE KEY-----.*?"
    r"-----END(?: [A-Z0-9]+)* PRIVATE KEY-----",
    re.IGNORECASE | re.DOTALL,
)
_PREFIXED_TOKEN_RE = re.compile(
    r"\b(?:sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{16,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|AKIA[0-9A-Z]{16})\b"
)
_JWT_RE = re.compile(
    r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
)
_AUTH_HEADER_RE = re.compile(
    r"(?i)\b(?P<prefix>authorization\s*:\s*(?:bearer|basic)\s+)"
    r"(?P<value>[A-Za-z0-9._~+/=-]{12,})"
)
_CONNECTION_URL_RE = re.compile(
    r"(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://"
    r"[^\s/:@]+:[^\s/@]+@[^\s]+"
)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(?P<key>[a-z0-9_-]*(?:api[_-]?key|client[_-]?secret|"
    r"access[_-]?token|auth[_-]?token|password|database[_-]?url|"
    r"private[_-]?key))(?P<separator>\s*[:=]\s*[\"']?)"
    r"(?P<value>(?!\[REDACTED_SECRET\])[^\s\"',;]{8,})"
)

_OPERATIONAL_REQUEST_RE = re.compile(
    r"\b(?:write|create|generate|provide|give|build|make|develop|produce|supply)"
    r"\b.{0,80}\b(?:code|script|payload|instructions?|steps?|procedure|recipe|"
    r"protocol|exploit)\b|\b(?:step[- ]by[- ]step|how to)\b",
    re.IGNORECASE,
)
_CREDENTIAL_THEFT_RE = re.compile(
    r"\b(?:steal|harvest|exfiltrat\w*|phish\w*|dump|capture|scrape)\w*\b"
    r".{0,80}\b(?:passwords?|credentials?|api keys?|access tokens?)\b|"
    r"\b(?:passwords?|credentials?|api keys?|access tokens?)\b.{0,80}"
    r"\b(?:steal|harvest|exfiltrat\w*|phish\w*|dump|capture|scrape)\w*\b",
    re.IGNORECASE,
)
_OFFENSIVE_CYBER_RE = re.compile(
    r"\b(?:ransomware|keylogger|credential stealer|botnet|remote access trojan|"
    r"malware payload|exploit payload|zero-day exploit)\b",
    re.IGNORECASE,
)
_WEAPON_RE = re.compile(
    r"\b(?:bomb|explosive device|chemical weapon|biological weapon|weaponized "
    r"pathogen|weaponized toxin)\b",
    re.IGNORECASE,
)
_MINOR_SEXUAL_ABUSE_RE = re.compile(
    r"\b(?:child|children|minor|underage)\b.{0,80}"
    r"\b(?:sexual|pornograph\w*|explicit images?)\b|"
    r"\b(?:sexual|pornograph\w*|explicit images?)\b.{0,80}"
    r"\b(?:child|children|minor|underage)\b",
    re.IGNORECASE,
)
_CONTENT_REQUEST_RE = re.compile(
    r"\b(?:create|generate|provide|show|find|share|send|write)\b", re.IGNORECASE
)
_ACADEMIC_CONTEXT_RE = re.compile(
    r"\b(?:paper|study|research|literature|authors?|summar(?:y|ize)|analy[sz]e|"
    r"critique|compare|historical|ethics?)\b",
    re.IGNORECASE,
)
_DEFENSIVE_CONTEXT_RE = re.compile(
    r"\b(?:detect(?:ion)?|mitigat(?:e|ion)|prevent(?:ion)?|defen[cs](?:e|ive)|"
    r"risk|safety|protect(?:ion)?)\b",
    re.IGNORECASE,
)
_DIRECT_ABUSE_TARGET_RE = re.compile(
    r"\b(?:target(?:ing)?|victims?|employees?|customers?|real accounts?|deploy|"
    r"working|undetected)\b",
    re.IGNORECASE,
)

SAFE_COMPLETION_GUIDANCE = """Safety boundary:
- The request asks for operational details that could directly enable harm.
- Continue with legitimate academic analysis grounded in the SOURCE PACKET.
- Omit executable code, procedural steps, exact harmful parameters, and evasion or
  optimization instructions that would make abuse easier.
- You may still explain findings, mechanisms at a high level, limitations, risks,
  detection, mitigation, prevention, and ethical implications when supported.
"""


@dataclass(frozen=True)
class SecretRedaction:
    text: str
    count: int


@dataclass(frozen=True)
class GuardrailDecision:
    action: Literal["allow", "safe_complete", "block"]
    category: str | None = None


def redact_secrets(text: str) -> SecretRedaction:
    """Redact only credential shapes with strong structural signals."""
    redacted = text
    count = 0

    for pattern in (
        _PRIVATE_KEY_RE,
        _CONNECTION_URL_RE,
        _PREFIXED_TOKEN_RE,
        _JWT_RE,
    ):
        redacted, replacements = pattern.subn(SECRET_MARKER, redacted)
        count += replacements

    redacted, replacements = _AUTH_HEADER_RE.subn(
        lambda match: f"{match.group('prefix')}{SECRET_MARKER}", redacted
    )
    count += replacements
    redacted, replacements = _SECRET_ASSIGNMENT_RE.subn(
        lambda match: (
            f"{match.group('key')}{match.group('separator')}{SECRET_MARKER}"
        ),
        redacted,
    )
    count += replacements
    return SecretRedaction(redacted, count)


def classify_intent(text: str) -> GuardrailDecision:
    """Require both explicit operational intent and a severe abuse target."""
    operational = bool(_OPERATIONAL_REQUEST_RE.search(text))
    if not operational:
        return GuardrailDecision("allow")
    if _CREDENTIAL_THEFT_RE.search(text):
        if _ACADEMIC_CONTEXT_RE.search(text) and not _DIRECT_ABUSE_TARGET_RE.search(
            text
        ):
            return GuardrailDecision("allow")
        if _DIRECT_ABUSE_TARGET_RE.search(text):
            return GuardrailDecision("block", "credential_theft")
        return GuardrailDecision("safe_complete", "credential_theft")
    if _MINOR_SEXUAL_ABUSE_RE.search(text) and _CONTENT_REQUEST_RE.search(text):
        return GuardrailDecision("block", "minor_sexual_abuse")
    if _OFFENSIVE_CYBER_RE.search(text):
        if _DEFENSIVE_CONTEXT_RE.search(text):
            return GuardrailDecision("allow")
        return GuardrailDecision("safe_complete", "offensive_cyber")
    if _WEAPON_RE.search(text):
        if _DEFENSIVE_CONTEXT_RE.search(text):
            return GuardrailDecision("allow")
        return GuardrailDecision("safe_complete", "weapon_construction")
    return GuardrailDecision("allow")
