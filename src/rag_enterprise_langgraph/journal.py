from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SENSITIVE_KEYS = {
    "debug_info",
    "traceback",
    "raw",
    "system_prompt",
    "user_prompt",
    "prompt",
    "messages",
    "authorization",
    "cookie",
    "token",
    "password",
    "secret",
    "api_key",
}


def sanitize_for_journal(value: Any) -> Any:
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.lower()
            if lowered in SENSITIVE_KEYS or any(secret in lowered for secret in ("password", "token", "secret", "api_key", "authorization", "cookie")):
                continue
            output[key_text] = sanitize_for_journal(item)
        return output
    if isinstance(value, list):
        return [sanitize_for_journal(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_for_journal(item) for item in value]
    if isinstance(value, str):
        cleaned = re.sub(r'File "[^"]+"', 'File "[path-redacted]"', value)
        return re.sub(r"/Users/[^\\s\"']+", "[path-redacted]", cleaned)
    return value


def write_journal_entry(path: str | Path | None, entry: dict[str, Any]) -> Path | None:
    if not path:
        return None
    journal_path = Path(path)
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **sanitize_for_journal(entry),
    }
    with journal_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    return journal_path
