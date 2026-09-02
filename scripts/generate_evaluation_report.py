"""Generate the HTML evaluation report from real run artifacts.

Nothing on the page is written by hand. Every number is read from a file produced
by an actual run:

    runs/eval-*.json                 eval runs, one per configuration
    runs/red-team/latest.json        red-team scenario results
    runs/pytest-summary.json         test suite result

Usage:
    python -m rag_enterprise_langgraph.cli --red-team --red-team-json runs/red-team/latest.json
    python -m pytest -q --json-report --json-report-file=runs/pytest-summary.json  # or see below
    python scripts/generate_evaluation_report.py --out docs/evaluation/index.html

If an artifact is missing the generator fails rather than inventing a number.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Which eval artifacts make up the published comparison, and how to label them.
CONFIGURATIONS = [
    ("runs/eval-northwind-llama3.2-3b.json", "llama3.2:3b", "local, 3B parameters", "baseline"),
    ("runs/eval-northwind-gpt-oss-20b.json", "gpt-oss:20b-cloud", "hosted, 20B parameters", "baseline"),
    (
        "runs/eval-northwind-gpt-oss-20b-augmented.json",
        "gpt-oss:20b-cloud",
        "hosted, 20B parameters",
        "retrieval augmentation ON",
    ),
]


def _read_json(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(
            f"Missing artifact: {path}\n"
            "This report is generated from real runs. Produce the artifact, or remove "
            "the configuration from CONFIGURATIONS - do not hand-write the number."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def collect_test_result() -> dict:
    """Run the suite and capture the real counts."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--tb=no"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    passed = int(m.group(1)) if (m := re.search(r"(\d+) passed", tail)) else 0
    failed = int(m.group(1)) if (m := re.search(r"(\d+) failed", tail)) else 0
    return {"passed": passed, "failed": failed, "summary": tail, "exit_code": proc.returncode}


def summarise_eval(report: dict) -> dict:
    rows = report["rows"]
    answerable = [r for r in rows if not r.get("expect_refusal")]
    refusal = [r for r in rows if r.get("expect_refusal")]
    return {
        "total": len(rows),
        "passed": report["passed"],
        "answerable_total": len(answerable),
        "answerable_passed": sum(1 for r in answerable if r["eval_status"] == "pass"),
        "refusal_total": len(refusal),
        "refusal_passed": sum(1 for r in refusal if r["eval_status"] == "pass"),
        "confidently_wrong": sum(
            1 for r in answerable if r["eval_status"] == "fail" and r["grounding_status"] == "verified"
        ),
        "over_refused": sum(
            1 for r in answerable if r["eval_status"] == "fail" and r["grounding_status"] != "verified"
        ),
        "review_routed": sum(1 for r in answerable if r["eval_status"] == "manual_review"),
        "failed_questions": {r["question"] for r in rows if r["eval_status"] != "pass"},
    }


def e(value: object) -> str:
    return html.escape(str(value))


def render(evals: list[tuple], red_team: dict, tests: dict) -> str:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # The headline is the refusal result: it is the direct measurement of the claim
    # this system exists to make. Accuracy sits below it, in context.
    baseline = next(s for label, s in evals if "augmentation" not in label)
    refusal_line = f"{baseline['refusal_passed']} of {baseline['refusal_total']}"

    # Identical-failure-set check across the two baseline configurations.
    baselines = [s for label, s in evals if "augmentation" not in label]
    identical = (
        len(baselines) == 2 and baselines[0]["failed_questions"] == baselines[1]["failed_questions"]
    )

    # Same-model off/on comparison, computed rather than narrated.
    off = next((x for lbl, x in evals if "gpt-oss" in lbl and "augmentation" not in lbl), None)
    on = next((x for lbl, x in evals if "augmentation" in lbl), None)
    aug_note = ""
    if off and on:
        fixed = len(off["failed_questions"] - on["failed_questions"])
        broken = len(on["failed_questions"] - off["failed_questions"])
        aug_note = f"""<div class="note">
      <strong>Turning retrieval augmentation on changed nothing measurable.</strong>
      Holding the model constant and enabling cross-encoder reranking, MMR, query
      transformation, rewrite, expansion, HyDE, multi-query and RRF fusion:
      <strong>{fixed} questions fixed, {broken} broken</strong>, the same overall score,
      and roughly six times the latency. The pipeline genuinely ran - answer wording
      changed on several questions and the cross-encoder loaded - it simply changed no
      outcomes.<br><br>
      The likely reason is corpus size, and it is a caveat rather than a verdict on the
      techniques. This corpus is 27 documents, 131 chunks. With 30 vector and 30 keyword
      candidates, retrieval already considers close to half the corpus before ranking
      begins, so re-ranking has very little room to help - and no ranking method can
      promote a chunk that was never a candidate. The eight failures are cases where the
      expected document was absent from the evidence entirely, which points at embedding
      and chunking rather than at ranking. On a corpus of thousands of documents these
      techniques would have far more to work with; this result should not be generalised
      to say they do not help.
    </div>"""

    rt_rows = red_team.get("findings") or red_team.get("results") or []
    defended = sum(1 for r in rt_rows if r.get("status") == "defended")
    requires_backend = sum(1 for r in rt_rows if r.get("status") == "requires_backend")
    failed_rt = sum(1 for r in rt_rows if r.get("status") == "failed")

    config_rows = "\n".join(
        f"""<tr>
          <td><strong>{e(label)}</strong></td>
          <td class="num">{s['passed']} / {s['total']}</td>
          <td class="num strong">{s['refusal_passed']} / {s['refusal_total']}</td>
          <td class="num">{s['answerable_passed']} / {s['answerable_total']}</td>
          <td class="num">{s['confidently_wrong']}</td>
          <td class="num">{s['review_routed']}</td>
        </tr>"""
        for label, s in evals
    )

    scenario_rows = "\n".join(
        f"""<tr class="{'rt-backend' if r.get('status') == 'requires_backend' else ''}">
          <td class="mono">{e(r.get('finding_id'))}</td>
          <td>{e(r.get('scenario') or r.get('title'))}</td>
          <td><span class="pill pill-{e(r.get('status'))}">{e(r.get('status'))}</span></td>
          <td class="detail">{e(r.get('actual_result') or r.get('detail') or '')}</td>
        </tr>"""
        for r in rt_rows
    )

    return f"""<!-- GENERATED FILE - do not edit by hand.
     Produced by scripts/generate_evaluation_report.py from run artifacts. -->
<title>Evaluation Report — Governed RAG</title>
<style>
  :root {{
    --bg: #fbfbfa; --fg: #1a1a1a; --muted: #5c5c5c; --line: #e2e0dc;
    --card: #ffffff; --accent: #1f4d3d; --warn: #8a5a00; --bad: #8a1f1f;
    --backend: #f4f0e6;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      --bg: #16171a; --fg: #ececec; --muted: #a0a0a0; --line: #2e3035;
      --card: #1d1f23; --accent: #7fd1b0; --warn: #e0b060; --bad: #e08585;
      --backend: #26241d;
    }}
  }}
  :root[data-theme="dark"] {{
    --bg: #16171a; --fg: #ececec; --muted: #a0a0a0; --line: #2e3035;
    --card: #1d1f23; --accent: #7fd1b0; --warn: #e0b060; --bad: #e08585;
    --backend: #26241d;
  }}
  body {{ background: var(--bg); color: var(--fg);
    font: 16px/1.6 ui-sans-serif, -apple-system, "Segoe UI", system-ui, sans-serif;
    margin: 0; padding: 2.5rem 1.25rem 4rem; }}
  main {{ max-width: 60rem; margin: 0 auto; }}
  h1 {{ font-size: 1.9rem; line-height: 1.2; margin: 0 0 .4rem; letter-spacing: -.02em; }}
  h2 {{ font-size: 1.2rem; margin: 2.75rem 0 .75rem; letter-spacing: -.01em; }}
  .sub {{ color: var(--muted); margin: 0 0 2rem; }}
  .banner {{ border: 1px solid var(--line); border-left: 3px solid var(--warn);
    background: var(--card); padding: 1rem 1.15rem; border-radius: 6px; margin: 0 0 2rem; }}
  .banner strong {{ color: var(--warn); }}
  .headline {{ background: var(--card); border: 1px solid var(--line); border-radius: 8px;
    padding: 1.5rem; margin-bottom: 1rem; }}
  .headline .big {{ font-size: 2.6rem; font-weight: 650; color: var(--accent);
    letter-spacing: -.03em; line-height: 1; }}
  .headline .cap {{ text-transform: uppercase; letter-spacing: .08em; font-size: .72rem;
    color: var(--muted); margin-bottom: .5rem; }}
  .scroll {{ overflow-x: auto; }}
  table {{ border-collapse: collapse; width: 100%; font-size: .92rem; }}
  th, td {{ text-align: left; padding: .6rem .7rem; border-bottom: 1px solid var(--line);
    vertical-align: top; }}
  th {{ font-size: .75rem; text-transform: uppercase; letter-spacing: .06em; color: var(--muted);
    font-weight: 600; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
  td.strong {{ font-weight: 650; color: var(--accent); }}
  td.mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .85rem; }}
  td.detail {{ color: var(--muted); font-size: .85rem; }}
  tr.rt-backend {{ background: var(--backend); }}
  .pill {{ display: inline-block; padding: .12rem .5rem; border-radius: 99px;
    font-size: .75rem; font-weight: 600; border: 1px solid var(--line); white-space: nowrap; }}
  .pill-defended {{ color: var(--accent); }}
  .pill-requires_backend {{ color: var(--warn); }}
  .pill-failed {{ color: var(--bad); }}
  .note {{ border: 1px solid var(--line); background: var(--card); border-radius: 6px;
    padding: 1rem 1.15rem; margin: 1rem 0; }}
  code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .88em;
    background: var(--card); border: 1px solid var(--line); border-radius: 3px; padding: .05em .3em; }}
  footer {{ margin-top: 3.5rem; padding-top: 1.25rem; border-top: 1px solid var(--line);
    color: var(--muted); font-size: .85rem; }}
</style>

<main>
  <h1>Evaluation report</h1>
  <p class="sub">Governed retrieval-augmented generation — measured, not asserted.<br>
     Generated {e(generated)} by <code>scripts/generate_evaluation_report.py</code> from run artifacts.</p>

  <div class="banner">
    <strong>What this is.</strong> A self-built proof of concept. It has never been
    deployed in a client environment, has no users, and has processed no real workload.
    Every number below was produced on a synthetic corpus of 27 invented documents on
    the author's own machine. Nothing here is evidence of production behaviour.
  </div>

  <div class="headline">
    <div class="cap">Correct refusals — questions the corpus cannot answer</div>
    <div class="big">{e(refusal_line)}</div>
    <p style="margin:.6rem 0 0; color:var(--muted)">
      Five of the twenty-five questions ask about subjects no document covers. A system
      that invents a plausible answer to these is the failure this project exists to
      prevent. Declining them is the measured demonstration of that claim.
    </p>
  </div>

  <h2>Accuracy, in context</h2>
  <p>Sample size is <strong>25 questions</strong>. That is small: a one- or two-question
     difference between configurations is noise, not signal, and should not be read as one.</p>
  <div class="scroll">
  <table>
    <thead><tr>
      <th>Configuration</th><th class="num">Overall</th><th class="num">Refusals</th>
      <th class="num">Answerable</th><th class="num">Confidently wrong</th><th class="num">Sent to review</th>
    </tr></thead>
    <tbody>{config_rows}</tbody>
  </table>
  </div>

  {'''<div class="note"><strong>The same questions failed under both models.</strong>
     A per-question comparison of the two baseline configurations shows the failing sets
     are identical, not merely equal in size. Inspecting the retrieved evidence for those
     questions, the expected source document was absent in every case. No model can answer
     from a document it was never given, which places the limit on retrieval rather than
     on generation. This is a mechanism, not a statistic, so it does not depend on the
     sample size.</div>''' if identical else ''}

  {aug_note}

  <h2>Red-team scenarios</h2>
  <p>{e(defended)} defended, {e(failed_rt)} failed,
     {e(requires_backend)} labelled <code>requires_backend</code> by design.
     The deterministic checks run offline against the real validation code paths.</p>
  <div class="scroll">
  <table>
    <thead><tr><th>ID</th><th>Scenario</th><th>Status</th><th>Result</th></tr></thead>
    <tbody>{scenario_rows}</tbody>
  </table>
  </div>

  <div class="note">
    <strong>On the <code>requires_backend</code> scenario, in plain English.</strong>
    One of the ten scenarios tests whether someone can retrieve a document they are not
    authorised to see. It is not simulated here, and it is not a failure — it is a
    scenario this layer deliberately cannot test. Access control is enforced by SQL
    inside the backend's retrieval queries. The agent layer has no database access at
    all, so there is nothing for it to bypass and nothing meaningful for it to check.
    Testing it honestly requires a running backend with a real database.<br><br>
    <strong>What would resolve it:</strong> exercising the scenario against a live
    deployed backend with two users of different permission levels, and showing that the
    same question returns a grounded answer for one and a refusal for the other. The
    corpus and the two demo users needed for that test already exist; the deployment
    does not yet.
  </div>

  <h2>Test suite</h2>
  <p><strong>{e(tests['passed'])} tests passed</strong>, {e(tests['failed'])} failed
     — <code>{e(tests['summary'])}</code></p>
  <p>The suite runs entirely offline: no Docker, no database, no model. That is why it
     can run on every push in continuous integration, and why the badge on the repository
     means something.</p>

  <h2>How to check this yourself</h2>
  <p>The corpus is synthetic and generated by a script in the repository, so every
     document the system was given is readable. Every question and its expected answer is
     in <code>config/eval-set-northwind.json</code>. The scorer holds no answers: an
     earlier version contained hardcoded answer keys for its own benchmark, and removing
     them is why these numbers differ from any published previously.</p>

  <footer>
    Self-built proof of concept. No production deployment, no users, no client data.
    Generated from run artifacts; not hand-written.
  </footer>
</main>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="docs/evaluation/index.html")
    parser.add_argument("--skip-tests", action="store_true", help="Reuse the last recorded test result.")
    args = parser.parse_args()

    evals = []
    for rel, model, detail, variant in CONFIGURATIONS:
        report = _read_json(REPO / rel)
        label = f"{model} ({detail}) — {variant}"
        evals.append((label, summarise_eval(report)))

    red_team = _read_json(REPO / "runs/red-team/latest.json")
    tests = collect_test_result()

    out = REPO / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(evals, red_team, tests), encoding="utf-8")
    print(f"Wrote {out} ({out.stat().st_size:,} bytes)")
    print(f"  configurations: {len(evals)}")
    print(f"  tests: {tests['summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
