from __future__ import annotations

import pytest

from rag_enterprise_langgraph.eval_performance import (
    PerformanceReportError,
    build_performance_summary,
    nearest_rank,
)


def _report(*, latency: float = 1000, recovered: int = 1):
    return {
        "rows": [
            {
                "case_id": f"C-{index:02d}",
                "end_to_end_latency_ms": latency + index,
                "recovery_attempted": index < recovered,
                "backend_request_ids": [f"request-{index}"],
            }
            for index in range(10)
        ]
    }


def _usage(total_cost: float = 0.1):
    return {
        "total_cost_usd": total_cost,
        "generation_request_count": 10,
        "requests": [{"request_id": f"request-{index}"} for index in range(10)],
    }


def test_nearest_rank_uses_ceiling_rank():
    assert nearest_rank(list(range(1, 21)), 0.95) == 19


def test_performance_summary_calculates_latency_cost_and_recovery():
    summary = build_performance_summary(_report(), _usage())
    assert summary["sample_size"] == 10
    assert summary["metrics"]["p50_latency_ms"] == 1004
    assert summary["metrics"]["p95_latency_ms"] == 1009
    assert summary["metrics"]["average_cost_usd_per_query"] == 0.01
    assert summary["metrics"]["recovery_rate"] == 0.1
    assert summary["status"] == "pass"


def test_warning_and_breach_thresholds_are_distinct():
    warning = build_performance_summary(_report(latency=4100), _usage())
    assert warning["metric_status"]["p95_latency_ms"] == "warn"
    breach = build_performance_summary(_report(latency=5100), _usage())
    assert breach["status"] == "breach"


def test_usage_join_must_be_complete_and_exact():
    usage = _usage()
    usage["requests"].pop()
    with pytest.raises(PerformanceReportError, match="do not match"):
        build_performance_summary(_report(), usage)
