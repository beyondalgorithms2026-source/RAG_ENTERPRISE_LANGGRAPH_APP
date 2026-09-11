from __future__ import annotations

import argparse
import json
from pathlib import Path

from rag_enterprise_langgraph.eval_baseline import BaselineError, compare_eval_reports


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline", type=Path)
    parser.add_argument("current", type=Path)
    args = parser.parse_args()
    try:
        comparison = compare_eval_reports(
            json.loads(args.baseline.read_text(encoding="utf-8")),
            json.loads(args.current.read_text(encoding="utf-8")),
        )
    except (OSError, json.JSONDecodeError, BaselineError) as exc:
        print(json.dumps({"status": "infrastructure_failure", "error": str(exc)}))
        return 2
    print(json.dumps(comparison, indent=2, sort_keys=True))
    return 0 if comparison["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
