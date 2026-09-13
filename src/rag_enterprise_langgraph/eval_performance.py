from __future__ import annotations

import math
from typing import Any


class PerformanceReportError(ValueError):
    """Performance inputs cannot produce a trustworthy regression result."""


DEFAULT_THRESHOLDS = {
    "p95_latency_ms": 5000.0,
    "mean_latency_ms": 3000.0,
    "average_cost_usd_per_query": 0.02,
    "recovery_rate": 0.25,
}


def nearest_rank(values: list[float], percentile: float) -> float:
    if not values:
        raise PerformanceReportError("at least one latency sample is required")
    if not 0 < percentile <= 1:
        raise PerformanceReportError("percentile must be greater than zero and at most one")
    ordered = sorted(float(value) for value in values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def _status(value: float, limit: float) -> str:
    if value > limit:
        return "breach"
    if value >= limit * 0.8:
        return "warn"
    return "pass"


def build_performance_summary(
    report: dict[str, Any],
    usage: dict[str, Any],
    *,
    thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    rows = report.get("rows")
    if not isinstance(rows, list) or not rows:
        raise PerformanceReportError("evaluation rows are required")
    latencies: list[float] = []
    request_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise PerformanceReportError("every evaluation row must be an object")
        latency = row.get("end_to_end_latency_ms")
        if not isinstance(latency, (int, float)) or latency < 0:
            raise PerformanceReportError("every evaluation row requires non-negative latency")
        latencies.append(float(latency))
        for request_id in row.get("backend_request_ids") or []:
            request_id = str(request_id).strip()
            if request_id:
                request_ids.add(request_id)

    usage_ids = {
        str(item.get("request_id"))
        for item in usage.get("requests") or []
        if isinstance(item, dict) and item.get("request_id")
    }
    if request_ids != usage_ids:
        missing = sorted(request_ids - usage_ids)
        unexpected = sorted(usage_ids - request_ids)
        raise PerformanceReportError(
            f"usage request ids do not match evaluation report; missing={missing}, "
            f"unexpected={unexpected}"
        )

    sample_size = len(rows)
    total_cost = usage.get("total_cost_usd")
    if not isinstance(total_cost, (int, float)) or total_cost < 0:
        raise PerformanceReportError("usage total_cost_usd must be non-negative")
    limits = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    metrics = {
        "mean_latency_ms": sum(latencies) / sample_size,
        "p50_latency_ms": nearest_rank(latencies, 0.50),
        "p95_latency_ms": nearest_rank(latencies, 0.95),
        "max_latency_ms": max(latencies),
        "average_cost_usd_per_query": float(total_cost) / sample_size,
        "recovery_rate": sum(bool(row.get("recovery_attempted")) for row in rows) / sample_size,
    }
    statuses = {metric: _status(metrics[metric], limit) for metric, limit in limits.items()}
    return {
        "schema_version": "1.0",
        "sample_size": sample_size,
        "backend_request_count": len(request_ids),
        "generation_request_count": int(usage.get("generation_request_count", 0)),
        "metrics": {key: round(value, 6) for key, value in metrics.items()},
        "thresholds": limits,
        "metric_status": statuses,
        "status": "breach"
        if "breach" in statuses.values()
        else ("warn" if "warn" in statuses.values() else "pass"),
    }
