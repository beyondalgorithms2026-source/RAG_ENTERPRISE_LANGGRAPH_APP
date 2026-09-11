"""Fail fast when the pinned P12B OpenAI model is unavailable.

The diagnostic deliberately prints only allowlisted model identifiers. It never
prints request headers, credentials, or the raw provider response.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_CANDIDATE_PREFIXES = ("gpt-4.1-mini", "gpt-4o-mini", "gpt-5-mini")


def _get_json(url: str, api_key: str) -> tuple[int, dict]:
    request = Request(url, headers={"Authorization": f"Bearer {api_key}"})
    try:
        with urlopen(request, timeout=15) as response:
            return int(response.status), json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return int(exc.code), {}
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise SystemExit(f"OpenAI model-access preflight failed: {type(exc).__name__}") from exc


def _candidate_ids(payload: dict) -> list[str]:
    identifiers = {
        str(row.get("id", "")) for row in payload.get("data", []) if isinstance(row, dict)
    }
    return sorted(
        identifier for identifier in identifiers if identifier.startswith(_CANDIDATE_PREFIXES)
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    api_key = os.environ.get("EVAL_OPENAI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("EVAL_OPENAI_API_KEY is absent")

    status, payload = _get_json("https://api.openai.com/v1/models", api_key)
    if status != 200:
        raise SystemExit(f"OpenAI model listing returned HTTP {status}")
    candidates = _candidate_ids(payload)
    print("Accessible allowlisted calibration models: " + (", ".join(candidates) or "none"))

    if args.model not in candidates:
        exact_status, _ = _get_json(
            f"https://api.openai.com/v1/models/{args.model}",
            api_key,
        )
        if exact_status != 200:
            print(
                f"Pinned model is unavailable (HTTP {exact_status}): {args.model}",
                file=sys.stderr,
            )
            return 1
    print(f"Pinned model is accessible: {args.model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
