from __future__ import annotations

import base64
import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class PromptSafetyVerdict:
    blocked: bool
    signals: tuple[str, ...] = ()
    reason: str | None = None


_SYSTEM_EXTRACTION = re.compile(
    r"(?:reveal|show|print|repeat|dump|expose|translate|return).{0,60}"
    r"(?:system\s+prompt|hidden\s+(?:prompt|instructions?)|developer\s+message|"
    r"mensaje\s+del\s+sistema|invite\s+syst[eè]me|systemanweisung)",
    re.IGNORECASE,
)
_ROLE_OVERRIDE = re.compile(
    r"(?:ignore|disregard|forget|override)\s+(?:all\s+)?(?:previous|prior|above|system)"
    r".{0,30}(?:instructions?|rules?|message|prompt)|"
    r"(?:you\s+are\s+now|act\s+as)\s+(?:an?\s+)?(?:unrestricted|developer|system|admin)|"
    r"ignora\s+(?:todas\s+)?las\s+instrucciones\s+anteriores|"
    r"ignorez\s+(?:toutes\s+)?les\s+instructions\s+pr[eé]c[eé]dentes|"
    r"ignoriere\s+(?:alle\s+)?vorherigen\s+anweisungen",
    re.IGNORECASE,
)
_TOOL_EXFILTRATION = re.compile(
    r"(?:call|invoke|use|execute).{0,50}(?:tool|function).{0,80}"
    r"(?:api[_ -]?key|token|authorization|cookie|password|credential|secret)|"
    r"(?:send|post|exfiltrate).{0,80}(?:tool\s+arguments?|credentials?|secrets?)",
    re.IGNORECASE,
)
_BASE64_FRAGMENT = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{20,}={0,2}(?![A-Za-z0-9+/])")


def _plain_signals(text: str) -> set[str]:
    signals: set[str] = set()
    if _SYSTEM_EXTRACTION.search(text):
        signals.add("system_prompt_extraction")
    if _ROLE_OVERRIDE.search(text):
        signals.add("role_override")
    if _TOOL_EXFILTRATION.search(text):
        signals.add("tool_argument_exfiltration")
    return signals


def _decoded_fragments(text: str) -> list[str]:
    decoded: list[str] = []
    for match in _BASE64_FRAGMENT.finditer(text[:12000]):
        try:
            raw = base64.b64decode(match.group(0), validate=True)
            value = raw.decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            continue
        if value and sum(character.isprintable() for character in value) / len(value) >= 0.9:
            decoded.append(value[:4000])
    return decoded


def assess_prompt_safety(value: str, *, max_chars: int = 12000) -> PromptSafetyVerdict:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    signals = _plain_signals(text[:max_chars])
    for decoded in _decoded_fragments(text):
        decoded_signals = _plain_signals(decoded)
        if decoded_signals:
            signals.add("encoded_instruction")
            signals.update(decoded_signals)
    ordered = tuple(sorted(signals))
    return PromptSafetyVerdict(
        blocked=bool(ordered),
        signals=ordered,
        reason="unsafe_instruction_request" if ordered else None,
    )


SAFE_PROMPT_REFUSAL = (
    "I cannot reveal hidden instructions, change system roles, or send secrets through tools. "
    "Ask a question about the indexed enterprise sources instead."
)
