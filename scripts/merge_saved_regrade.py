"""Replace selected preserved rows with saved-answer regrades and recompute counts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def merge(report: dict[str, Any], regrade: dict[str, Any]) -> dict[str, Any]:
    replacements = {row["case_id"]: row for row in regrade.get("rows", [])}
    if not replacements:
        raise ValueError("saved-answer regrade contains no rows")
    rows = report.get("rows")
    if not isinstance(rows, list) or len(rows) != 90:
        raise ValueError("preserved report must contain exactly 90 rows")
    found: set[str] = set()
    for row in rows:
        replacement = replacements.get(row.get("case_id"))
        if not replacement:
            continue
        found.add(row["case_id"])
        expected_eval = dict(row.get("expected_eval") or {})
        expected_eval["typed"] = replacement["typed"]
        expected_eval["judge_metadata"] = replacement.get("judge_metadata")
        expected_eval.pop("judge_error", None)
        row["expected_eval"] = expected_eval
        row["eval_status"] = replacement["revised_answer_status"]
        row["failure_class"] = (
            "infrastructure"
            if replacement.get("failure_class") == "infrastructure"
            else ("quality" if row["eval_status"] != "pass" else None)
        )
    if found != set(replacements):
        raise ValueError("saved-answer regrade case IDs do not match the preserved report")

    report["passed"] = sum(row.get("eval_status") == "pass" for row in rows)
    report["failed"] = sum(row.get("eval_status") == "fail" for row in rows)
    report["manual_review"] = sum(row.get("eval_status") == "manual_review" for row in rows)
    report["infrastructure_failures"] = sum(
        row.get("failure_class") == "infrastructure" for row in rows
    )
    transport = {"backend_auth_failed", "backend_timeout", "tool_error"}
    report["transport_failures"] = sum(row.get("grounding_status") in transport for row in rows)
    report["grader_failures"] = sum(
        bool((row.get("expected_eval") or {}).get("judge_error")) for row in rows
    )
    report["other_infrastructure_failures"] = max(
        0,
        report["infrastructure_failures"]
        - report["transport_failures"]
        - report["grader_failures"],
    )
    report["status"] = (
        "pass"
        if report["failed"] == 0
        and report["manual_review"] == 0
        and report["infrastructure_failures"] == 0
        else "fail"
    )
    report.setdefault("release_notes", {})["saved_answer_regrade_case_ids"] = sorted(found)
    report["release_notes"]["answers_regenerated"] = False
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("regrade", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    revised = merge(
        json.loads(args.report.read_text(encoding="utf-8")),
        json.loads(args.regrade.read_text(encoding="utf-8")),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(revised, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 2 if revised["infrastructure_failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
