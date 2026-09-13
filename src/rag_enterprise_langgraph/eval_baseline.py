from __future__ import annotations

from typing import Any


class BaselineError(ValueError):
    """An evaluation report cannot be compared safely."""


REQUIRED_CONFIGURATION_PATHS = (
    ("repositories", "app"),
    ("repositories", "mcp"),
    ("repositories", "starter"),
    ("llm", "provider"),
    ("llm", "model"),
    ("embedding", "provider"),
    ("embedding", "model"),
    ("embedding", "dimensions"),
    ("chunking", "policy"),
    ("chunking", "target_words"),
    ("chunking", "overlap_words"),
    ("retrieval", "mode"),
    ("retrieval", "rerank_enabled"),
    ("orchestration", "max_recovery_steps"),
    ("orchestration", "expected_fact_scope"),
    ("app_prompts",),
    ("starter_prompts",),
    ("corpus_manifest_sha256",),
)


def _configuration(report: dict[str, Any], label: str) -> dict[str, Any]:
    configuration = report.get("configuration")
    if not isinstance(configuration, dict) or not configuration:
        raise BaselineError(f"{label} configuration metadata is required")
    for path in REQUIRED_CONFIGURATION_PATHS:
        value: Any = configuration
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
        if value in (None, "", {}, []):
            raise BaselineError(f"{label} configuration is missing {'.'.join(path)}")
    return configuration


def _pinned_configuration(configuration: dict[str, Any]) -> dict[str, Any]:
    # Candidate commits are expected to differ from the approved baseline. All
    # answer-shaping configuration remains pinned and must match exactly.
    return {key: value for key, value in configuration.items() if key != "repositories"}


def _rows(report: dict[str, Any], label: str) -> dict[str, dict[str, Any]]:
    rows = report.get("rows")
    if not isinstance(rows, list) or not rows:
        raise BaselineError(f"{label} report has no rows")
    mapped: dict[str, dict[str, Any]] = {}
    for row in rows:
        case_id = str(row.get("case_id") or "").strip() if isinstance(row, dict) else ""
        if not case_id:
            raise BaselineError(f"{label} report contains a row without case_id")
        if case_id in mapped:
            raise BaselineError(f"{label} report contains duplicate case_id: {case_id}")
        mapped[case_id] = row
    return mapped


def _performance(report: dict[str, Any], label: str) -> dict[str, Any] | None:
    value = report.get("performance")
    if value is None and str(report.get("schema_version")) != "2.0":
        return None
    if not isinstance(value, dict):
        raise BaselineError(f"{label} performance metadata is required")
    metrics = value.get("metrics")
    thresholds = value.get("thresholds")
    if not isinstance(metrics, dict) or not isinstance(thresholds, dict):
        raise BaselineError(f"{label} performance metrics and thresholds are required")
    required = {
        "p95_latency_ms",
        "mean_latency_ms",
        "average_cost_usd_per_query",
        "recovery_rate",
    }
    if not required <= set(metrics) or not required <= set(thresholds):
        raise BaselineError(f"{label} performance metadata is incomplete")
    if int(value.get("sample_size", 0)) != int(report.get("total", 0)):
        raise BaselineError(f"{label} performance sample size does not match report total")
    return value


def compare_eval_reports(baseline: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    baseline_configuration = _configuration(baseline, "baseline")
    current_configuration = _configuration(current, "current")
    baseline_rows = _rows(baseline, "baseline")
    current_rows = _rows(current, "current")
    baseline_performance = _performance(baseline, "baseline")
    current_performance = _performance(current, "current")
    if set(baseline_rows) != set(current_rows):
        missing = sorted(set(baseline_rows) - set(current_rows))
        added = sorted(set(current_rows) - set(baseline_rows))
        raise BaselineError(f"case ids changed; missing={missing}, added={added}")

    regressions: list[dict[str, str]] = []
    if _pinned_configuration(baseline_configuration) != _pinned_configuration(
        current_configuration
    ):
        regressions.append({"case_id": "configuration", "rule": "pinned_configuration_changed"})
    current_rt06 = current.get("rt06")
    if not isinstance(current_rt06, dict) or current_rt06.get("status") != "pass":
        regressions.append({"case_id": "RT-06", "rule": "acl_boundary_failed"})
    for case_id, before in baseline_rows.items():
        after = current_rows[case_id]
        if after.get("failure_class") == "infrastructure":
            regressions.append({"case_id": case_id, "rule": "infrastructure_failure"})
        if (after.get("expect_refusal") or after.get("expectation") == "refuse") and after.get(
            "eval_status"
        ) != "pass":
            regressions.append({"case_id": case_id, "rule": "must_refuse_failed"})
        if before.get("eval_status") == "pass" and after.get("eval_status") != "pass":
            regressions.append({"case_id": case_id, "rule": "prior_pass_regressed"})
        if (
            before.get("expected_document_matched") is True
            and after.get("expected_document_matched") is not True
        ):
            regressions.append({"case_id": case_id, "rule": "expected_document_regressed"})

    for metric, direction in (
        ("passed", "minimum"),
        ("failed", "maximum"),
        ("manual_review", "maximum"),
    ):
        before_value = int(baseline.get(metric, 0))
        after_value = int(current.get(metric, 0))
        regressed = (
            after_value < before_value if direction == "minimum" else after_value > before_value
        )
        if regressed:
            regressions.append({"case_id": "aggregate", "rule": f"{metric}_{direction}"})

    if int(current.get("refusal_passed", 0)) != int(current.get("refusal_total", 0)):
        regressions.append({"case_id": "aggregate", "rule": "refusal_zero_tolerance"})
    if int(current.get("safe_boundary_passed", 0)) != int(current.get("safe_boundary_total", 0)):
        regressions.append({"case_id": "aggregate", "rule": "safe_boundary_zero_tolerance"})
    if int(current.get("infrastructure_failures", 0)):
        regressions.append({"case_id": "aggregate", "rule": "infrastructure_zero_tolerance"})
    if baseline_performance is not None:
        if current_performance is None:
            regressions.append({"case_id": "performance", "rule": "performance_missing"})
        else:
            if baseline_performance["thresholds"] != current_performance["thresholds"]:
                regressions.append(
                    {"case_id": "performance", "rule": "performance_thresholds_changed"}
                )
            if current_performance.get("status") == "breach":
                regressions.append(
                    {"case_id": "performance", "rule": "performance_threshold_breached"}
                )

    return {
        "schema_version": "1.0",
        "status": "pass" if not regressions else "fail",
        "regression_count": len(regressions),
        "regressions": regressions,
    }
