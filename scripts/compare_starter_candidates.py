"""Compare like-for-like STARTER diagnostics; offline judge cost is separate."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path


def metrics(report: dict) -> dict:
    rows = report.get("rows", [])
    if not rows or any(r.get("failure_class") == "infrastructure" for r in rows):
        raise ValueError("performance comparison requires infrastructure-successful answers")
    latency = sorted(float(r["latency_ms"]) for r in rows)
    return {
        "sample_size": len(rows),
        "median_latency_ms": statistics.median(latency),
        "p95_latency_ms": latency[math.ceil(len(latency) * 0.95) - 1],
        "average_input_tokens": statistics.mean(r["usage"]["prompt_tokens"] for r in rows),
        "average_output_tokens": statistics.mean(r["usage"]["completion_tokens"] for r in rows),
        "average_cost_usd": statistics.mean(r["usage"]["cost_usd"] for r in rows),
        "average_generation_calls": statistics.mean(r["usage"]["call_count"] for r in rows),
        "average_context_chars": statistics.mean(
            sum(len(c["snippet"]) for c in r.get("selected_context", [])) for r in rows
        ),
    }


def compare(current: dict, candidate: dict) -> dict:
    a = current.get("rows", [])
    b = candidate.get("rows", [])
    if [(r["case_id"], r["question"]) for r in a] != [(r["case_id"], r["question"]) for r in b]:
        raise ValueError("case IDs, question wording and order must match")
    if (
        current.get("scope") != "starter-only-live"
        or candidate.get("scope") != "starter-only-live"
    ):
        raise ValueError(
            "this comparator accepts STARTER-only live diagnostics, not full-stack reports"
        )
    before = metrics(current)
    after = metrics(candidate)
    increases = {
        key: (after[key] / before[key] - 1) * 100
        for key in ("p95_latency_ms", "average_input_tokens")
        if before[key] > 0
    }
    breaches = [
        key
        for key, limit in (("p95_latency_ms", 15), ("average_input_tokens", 20))
        if key not in increases or increases[key] > limit
    ]
    return {
        "scope": "starter-only-performance-comparison",
        "baseline_eligible": False,
        "current": before,
        "candidate": after,
        "increase_percent": increases,
        "review_required": breaches,
        "release_status": "review_required" if breaches else "within_candidate_review_limits",
        "limitation": "Single diagnostic comparison; not calibrated p95 or proof of answer correctness. Judge tokens/cost excluded.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("current", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite performance evidence")
    result = compare(json.loads(args.current.read_text()), json.loads(args.candidate.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(result["release_status"])
    return 1 if result["review_required"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
