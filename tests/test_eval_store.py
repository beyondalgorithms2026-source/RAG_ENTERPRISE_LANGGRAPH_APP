from __future__ import annotations

from rag_enterprise_langgraph.config import Settings
from rag_enterprise_langgraph.eval_store import EvalStore, build_eval_run_summary, compute_metrics


SAMPLE_REPORT = {
    "xlsx_path": "/Users/example/somewhere/eval-questions.xlsx",
    "total": 4,
    "passed": 3,
    "failed": 0,
    "manual_review": 1,
    "status": "fail",
    "rows": [
        {"question": "Q1?", "eval_status": "pass", "grounding_status": "verified", "latency_ms": 100},
        {"question": "Q2?", "eval_status": "pass", "grounding_status": "recovered", "latency_ms": 300},
        {"question": "Q3?", "eval_status": "pass", "grounding_status": "grounded", "latency_ms": None},
        {"question": "Q4?", "eval_status": "manual_review", "grounding_status": "needs_review", "latency_ms": None},
    ],
}


def _settings() -> Settings:
    return Settings(
        input_token_cost_per_1m=2.0,
        output_token_cost_per_1m=10.0,
        default_estimated_tokens_per_query=1000,
    )


def test_compute_metrics_accuracy_grounding_latency_and_cost():
    metrics = compute_metrics(SAMPLE_REPORT, settings=_settings())
    assert metrics["total"] == 4
    assert metrics["accuracy"] == 0.75
    assert metrics["grounding_rate"] == 0.75
    assert metrics["avg_latency_ms"] == 200.0
    # 800 input tokens at $2/1M + 200 output tokens at $10/1M.
    assert metrics["estimated_cost_per_query"] == round(800 / 1e6 * 2.0 + 200 / 1e6 * 10.0, 6)
    assert metrics["cost_basis"] == "estimated"
    assert metrics["cost_model"]["default_estimated_tokens_per_query"] == 1000


def test_compute_metrics_handles_empty_report():
    metrics = compute_metrics({"total": 0, "passed": 0, "failed": 0, "manual_review": 0, "rows": []}, settings=_settings())
    assert metrics["accuracy"] == 0.0
    assert metrics["grounding_rate"] == 0.0
    assert metrics["avg_latency_ms"] is None


def test_eval_run_summary_strips_local_paths():
    summary = build_eval_run_summary(SAMPLE_REPORT, settings=_settings())
    assert summary["source_xlsx"] == "eval-questions.xlsx"
    assert "/Users/" not in str(summary)
    assert summary["eval_run_id"].startswith("eval-")
    assert len(summary["rows"]) == 4


def test_eval_store_save_list_get_latest(tmp_path):
    store = EvalStore(tmp_path / "eval-runs")
    first = build_eval_run_summary(SAMPLE_REPORT, settings=_settings(), eval_run_id="eval-20260101-000000-aaaa")
    second = build_eval_run_summary(SAMPLE_REPORT, settings=_settings(), eval_run_id="eval-20260102-000000-bbbb")
    second["created_at"] = "2999-01-01T00:00:00+00:00"
    store.save(first)
    store.save(second)

    listing = store.list()
    assert len(listing) == 2
    assert listing[0]["eval_run_id"] == "eval-20260102-000000-bbbb"
    assert "rows" not in listing[0]

    fetched = store.get("eval-20260101-000000-aaaa")
    assert fetched is not None
    assert len(fetched["rows"]) == 4

    latest = store.latest()
    assert latest["eval_run_id"] == "eval-20260102-000000-bbbb"

    assert store.get("../escape") is None
    assert store.get("missing") is None
