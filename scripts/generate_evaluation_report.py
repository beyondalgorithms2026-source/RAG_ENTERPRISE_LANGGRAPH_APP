"""Generate the public evaluation page and sanitized status from approved evidence.

The approved baseline is the only source for full-stack quality claims. The offline
red-team mechanisms are executed while generating the page. Missing or unapproved
evidence fails closed instead of falling back to historical local run artifacts.
"""

from __future__ import annotations

import argparse
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rag_enterprise_langgraph.red_team import run_red_team

REPO = Path(__file__).resolve().parent.parent
DEFAULT_BASELINE = REPO / "config/eval-baselines/northwind-openai-v1.json"
DEFAULT_HTML = REPO / "docs/evaluation/index.html"
DEFAULT_STATUS = REPO / "docs/evaluation/status.json"
PUBLIC_DEMO_URL = "https://rag-enterprise-governance-demo.onrender.com/app"
STATUS_SCHEMA_VERSION = "1.0"


def _read_approved_baseline(path: Path) -> dict[str, Any]:
    try:
        baseline = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot read approved baseline {path}: {exc}") from exc
    approval = baseline.get("baseline_approval")
    if not isinstance(approval, dict) or approval.get("status") != "approved":
        raise SystemExit(f"Refusing to publish unapproved baseline: {path}")
    rows = baseline.get("rows")
    if not isinstance(rows, list) or not rows:
        raise SystemExit(f"Approved baseline has no case rows: {path}")
    if baseline.get("status") != "pass":
        raise SystemExit(f"Refusing to publish a non-passing baseline: {path}")
    rt06 = baseline.get("rt06")
    if not isinstance(rt06, dict) or rt06.get("status") != "pass":
        raise SystemExit(f"Refusing to publish a baseline without passing RT-06: {path}")
    return baseline


def _safe_configuration(configuration: dict[str, Any]) -> dict[str, Any]:
    """Return only public, bounded configuration evidence."""
    return {
        "llm": configuration.get("llm"),
        "embedding": configuration.get("embedding"),
        "chunking": configuration.get("chunking"),
        "retrieval": configuration.get("retrieval"),
        "orchestration": configuration.get("orchestration"),
        "app_prompts": configuration.get("app_prompts"),
        "starter_prompts": configuration.get("starter_prompts"),
        "corpus_manifest_sha256": configuration.get("corpus_manifest_sha256"),
    }


def build_public_status(
    baseline: dict[str, Any],
    red_team: dict[str, Any],
    *,
    baseline_path: Path,
    generated_at: str | None = None,
) -> dict[str, Any]:
    rows = baseline["rows"]
    refusal_rows = [row for row in rows if row.get("expect_refusal") is True]
    approval = baseline["baseline_approval"]
    return {
        "schema_version": STATUS_SCHEMA_VERSION,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "evidence_status": "approved",
        "baseline": {
            "id": baseline_path.stem,
            "approved_at": approval.get("generated_at"),
            "calibration_run_count": approval.get("calibration_run_count"),
            "source_path": baseline_path.relative_to(REPO).as_posix(),
            "source_run_url": approval.get("source_run_url"),
        },
        "quality": {
            "total": len(rows),
            "passed": int(baseline.get("passed", 0)),
            "failed": int(baseline.get("failed", 0)),
            "manual_review": int(baseline.get("manual_review", 0)),
            "strict_refusal_total": len(refusal_rows),
            "strict_refusal_passed": sum(
                1 for row in refusal_rows if row.get("eval_status") == "pass"
            ),
        },
        "governance": {
            "rt06": baseline["rt06"].get("status"),
            "offline_red_team": {
                "total": int(red_team.get("total", 0)),
                "defended": int(red_team.get("defended", 0)),
                "failed": int(red_team.get("failed", 0)),
                "requires_backend": int(red_team.get("requires_backend", 0)),
                "status": red_team.get("overall_status"),
            },
        },
        "configuration": _safe_configuration(baseline.get("configuration") or {}),
        "limitations": [
            "Synthetic public-demo corpus; no client or private data.",
            "Approved quality evidence is a fixed full-stack calibration snapshot, not live traffic.",
            "Offline red-team checks prove deterministic governance mechanisms; RT-06 and RT-16 require live SQL authorization proof.",
        ],
    }


def _e(value: object) -> str:
    return html.escape(str(value))


def render_html(status: dict[str, Any]) -> str:
    quality = status["quality"]
    governance = status["governance"]
    baseline = status["baseline"]
    configuration = status["configuration"]
    llm = configuration.get("llm") or {}
    embedding = configuration.get("embedding") or {}
    retrieval = configuration.get("retrieval") or {}
    red_team = governance["offline_red_team"]
    return f"""<!-- GENERATED FILE - do not edit by hand.
     Produced by scripts/generate_evaluation_report.py from approved evidence. -->
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Approved Evaluation Evidence — Governed RAG</title>
<style>
  :root {{ color-scheme: light dark; --bg:#fbfbfa; --card:#fff; --fg:#17201d;
    --muted:#59635f; --line:#d9dfdc; --good:#176b45; --accent:#164d3c; }}
  @media (prefers-color-scheme:dark) {{ :root {{ --bg:#141816; --card:#1c221f;
    --fg:#eef4f0; --muted:#a7b2ac; --line:#34413b; --good:#79d5aa; --accent:#8edcba; }} }}
  * {{ box-sizing:border-box }} body {{ margin:0; padding:2.5rem 1.25rem 4rem;
    background:var(--bg); color:var(--fg); font:16px/1.55 ui-sans-serif,system-ui,sans-serif }}
  main {{ max-width:64rem; margin:auto }} h1 {{ font-size:clamp(2rem,5vw,3.5rem);
    line-height:1.05; letter-spacing:-.04em; margin:.35rem 0 1rem }} h2 {{ margin-top:2.5rem }}
  .eyebrow {{ color:var(--good); font-weight:700; letter-spacing:.08em; text-transform:uppercase }}
  .lede,.muted {{ color:var(--muted) }} .lede {{ font-size:1.12rem; max-width:48rem }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(12rem,1fr)); gap:.8rem;
    margin:2rem 0 }} .card,.note {{ background:var(--card); border:1px solid var(--line);
    border-radius:.75rem; padding:1rem }} .metric {{ font-size:2rem; font-weight:750; color:var(--good) }}
  .label {{ color:var(--muted); font-size:.82rem; text-transform:uppercase; letter-spacing:.06em }}
  table {{ width:100%; border-collapse:collapse }} th,td {{ text-align:left; padding:.7rem;
    border-bottom:1px solid var(--line) }} th {{ color:var(--muted) }} code {{ overflow-wrap:anywhere }}
  a {{ color:var(--accent) }} footer {{ border-top:1px solid var(--line); margin-top:3rem;
    padding-top:1rem; color:var(--muted); font-size:.9rem }}
</style>
</head>
<body><main>
  <p class="eyebrow">Approved full-stack evidence</p>
  <h1>Governed RAG evaluation</h1>
  <p class="lede">A reproducible APP → MCP → STARTER → PostgreSQL/pgvector quality
  gate over a deterministic synthetic corpus. This is portfolio evidence, not a claim
  about production traffic or client workloads.</p>

  <div class="grid">
    <section class="card"><div class="label">Quality cases</div>
      <div class="metric">{_e(quality["passed"])}/{_e(quality["total"])}</div>
      <div class="muted">approved baseline passes</div></section>
    <section class="card"><div class="label">Required refusals</div>
      <div class="metric">{_e(quality["strict_refusal_passed"])}/{_e(quality["strict_refusal_total"])}</div>
      <div class="muted">unsupported questions safely refused</div></section>
    <section class="card"><div class="label">SQL ACL boundary</div>
      <div class="metric">{_e(str(governance["rt06"]).upper())}</div>
      <div class="muted">live denied + authorized RT-06 control</div></section>
    <section class="card"><div class="label">Offline red team</div>
      <div class="metric">{_e(red_team["defended"])}/{_e(red_team["total"] - red_team["requires_backend"])}</div>
      <div class="muted">deterministic mechanisms defended</div></section>
  </div>

  <div class="note"><strong>Try the public demo:</strong>
    <a href="{_e(PUBLIC_DEMO_URL)}">open the governed browser flow</a>.
    Render Free may need time to wake after inactivity. Read the
    <a href="../manual/">public synthetic Operations Manual v3.2</a>.</div>

  <div class="note"><strong>Expanded suite:</strong> the 90-case v2 suite is under
    calibration and is not shown as approved evidence until its ten-run gate and review
    complete.</div>

  <h2>What was measured</h2>
  <table><tbody>
    <tr><th>Baseline</th><td><code>{_e(baseline["id"])}</code></td></tr>
    <tr><th>Calibration</th><td>{_e(baseline["calibration_run_count"])} eligible full-stack runs</td></tr>
    <tr><th>Model</th><td><code>{_e(llm.get("model"))}</code></td></tr>
    <tr><th>Embedding</th><td><code>{_e(embedding.get("model"))}</code>, {_e(embedding.get("dimensions"))} dimensions</td></tr>
    <tr><th>Retrieval</th><td>{_e(retrieval.get("mode"))}; reranking {_e(retrieval.get("rerank_enabled"))}</td></tr>
    <tr><th>Red team</th><td>{_e(red_team["total"])} defined scenarios: {_e(red_team["defended"])} deterministic defenses passed; RT-06 and RT-16 are proved separately in the live stack.</td></tr>
  </tbody></table>

  <h2>Limits</h2>
  <ul>{"".join(f"<li>{_e(item)}</li>" for item in status["limitations"])}</ul>
  <p>The checked-in <a href="status.json"><code>status.json</code></a> is the
  machine-readable form of this approved snapshot. A failed or incomplete CI run never
  replaces it automatically.</p>

  <footer>Generated {_e(status["generated_at"])} from
  <code>{_e(baseline["source_path"])}</code>. No test count, live-traffic claim, or
  historical local-model score is inferred.</footer>
</main></body></html>
"""


def write_public_report(
    *, baseline_path: Path, html_path: Path, status_path: Path, generated_at: str | None = None
) -> dict[str, Any]:
    baseline = _read_approved_baseline(baseline_path)
    red_team = run_red_team()
    if red_team.get("overall_status") != "pass":
        raise SystemExit("Refusing to publish because a deterministic red-team check failed")
    status = build_public_status(
        baseline, red_team, baseline_path=baseline_path, generated_at=generated_at
    )
    html_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(render_html(status), encoding="utf-8")
    status_path.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--out", type=Path, default=DEFAULT_HTML)
    parser.add_argument("--status-out", type=Path, default=DEFAULT_STATUS)
    args = parser.parse_args()
    status = write_public_report(
        baseline_path=args.baseline.resolve(),
        html_path=args.out.resolve(),
        status_path=args.status_out.resolve(),
    )
    print(
        f"Published approved {status['quality']['passed']}/{status['quality']['total']} "
        f"snapshot to {args.out} and {args.status_out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
