"""Fail closed on revised candidate safety; never approve or rewrite a baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rag_enterprise_langgraph.eval_calibration import validate_correction_report
from rag_enterprise_langgraph.eval_runner import read_eval_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    ids = {
        case.case_id
        for filename in (
            "eval-set-northwind-candidate.json",
            "eval-set-operations-manual-v3.2-candidate.json",
        )
        for case in read_eval_json(root / "config" / filename)
    }
    try:
        validate_correction_report(json.loads(args.report.read_text()), ids)
    except (ValueError, OSError):
        print(
            "Revised candidate safety/metadata checks failed; baseline promotion remains blocked."
        )
        return 1
    print(
        "Revised critical/refusal/RT-06 checks pass; calibration and owner approval are still required."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
