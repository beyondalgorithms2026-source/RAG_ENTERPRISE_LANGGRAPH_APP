"""Build a reviewable baseline candidate from 10-15 successful calibration reports."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("runs", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--justification", required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("refusing to overwrite an existing baseline")
    if not 10 <= len(args.runs) <= 15:
        raise SystemExit("baseline calibration requires 10 to 15 reports")
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in args.runs]
    for report in reports:
        if report.get("infrastructure_failures"):
            raise SystemExit("infrastructure-failed reports cannot enter calibration")
        if report.get("refusal_passed") != report.get("refusal_total"):
            raise SystemExit("every calibration report must pass all refusal cases")
        if report.get("rt06", {}).get("status") != "pass":
            raise SystemExit("every calibration report must include a passing RT-06 result")

    pinned_configurations = []
    for report in reports:
        configuration = report.get("configuration")
        if not isinstance(configuration, dict) or not configuration:
            raise SystemExit("every calibration report must include configuration metadata")
        pinned_configurations.append(
            json.dumps(
                {key: value for key, value in configuration.items() if key != "repositories"},
                sort_keys=True,
            )
        )
    if len(set(pinned_configurations)) != 1:
        raise SystemExit("calibration reports use different pinned configurations")

    case_sets = [{row["case_id"] for row in report["rows"]} for report in reports]
    if any(case_set != case_sets[0] for case_set in case_sets[1:]):
        raise SystemExit("calibration reports contain different case ids")
    stable_required = math.ceil(len(reports) * 0.9)
    for case_id in case_sets[0]:
        statuses = Counter(
            next(row["eval_status"] for row in report["rows"] if row["case_id"] == case_id)
            for report in reports
        )
        if statuses.most_common(1)[0][1] < stable_required:
            raise SystemExit(f"unstable calibration case: {case_id} {dict(statuses)}")

    pass_counts = sorted(int(report["passed"]) for report in reports)
    median_pass_count = pass_counts[(len(pass_counts) - 1) // 2]
    median_candidates = [
        report for report in reports if int(report["passed"]) == median_pass_count
    ]
    selected = min(median_candidates, key=lambda report: int(report["manual_review"]))
    selected["baseline_approval"] = {
        "status": "candidate",
        "justification": args.justification,
        "calibration_run_count": len(reports),
        "generated_at": datetime.now(UTC).isoformat(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(selected, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote baseline candidate to {args.output}; owner review is still required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
