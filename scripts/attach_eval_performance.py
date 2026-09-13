"""Attach sanitized STARTER cost data and APP latency metrics to an eval report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rag_enterprise_langgraph.eval_performance import (
    PerformanceReportError,
    build_performance_summary,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("usage", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        usage = json.loads(args.usage.read_text(encoding="utf-8"))
        report["performance"] = build_performance_summary(report, usage)
    except (OSError, json.JSONDecodeError, PerformanceReportError) as exc:
        print(f"error: cannot attach evaluation performance: {exc}")
        return 2
    if report["performance"]["status"] == "breach":
        report["status"] = "fail"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"Performance {report['performance']['status']}: "
        f"n={report['performance']['sample_size']}, "
        f"p95={report['performance']['metrics']['p95_latency_ms']:.1f}ms"
    )
    return 1 if report["performance"]["status"] == "breach" else 0


if __name__ == "__main__":
    raise SystemExit(main())
