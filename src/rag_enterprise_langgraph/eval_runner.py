from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import subprocess
import time
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from rag_enterprise_langgraph.demo_proof import redact_for_sharing
from rag_enterprise_langgraph.evidence import evaluate_expected_answer, load_rules
from rag_enterprise_langgraph.orchestrator import EnterpriseRagOrchestrator
from rag_enterprise_langgraph.prompt_registry import prompt_metadata

NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


@dataclass(frozen=True)
class EvalFact:
    fact_id: str
    any_of: tuple[str, ...]
    evidence_required: bool = True


@dataclass(frozen=True)
class EvalCase:
    question: str
    expected_answer: str
    file_name: str | None = None
    post_url: str | None = None
    # True for questions the corpus deliberately cannot answer. These pass only
    # if the system declines to answer - inventing a plausible answer is the
    # failure they exist to catch.
    expect_refusal: bool = False
    case_id: str | None = None
    schema_version: str = "1.0"
    expectation: str = "answer"
    expected_documents: tuple[str, ...] = ()
    document_match_policy: str = "any"
    required_facts: tuple[EvalFact, ...] = ()
    forbidden_facts: tuple[str, ...] = ()
    ordered_fact_ids: tuple[str, ...] = ()
    question_type: str | None = None
    difficulty: str | None = None
    rationale: str | None = None
    source_sections: tuple[str, ...] = ()


class EvalSetError(ValueError):
    """The checked-in evaluation set is malformed or internally contradictory."""


def _git_commit(path: Path) -> str | None:
    try:
        return subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _external_prompt_metadata(repo: Path) -> dict[str, dict[str, str]]:
    root = repo / "backend/app/llm/prompt_assets"
    registry = json.loads((root / "registry.json").read_text(encoding="utf-8"))
    output: dict[str, dict[str, str]] = {}
    for prompt_id, entry in registry.get("prompts", {}).items():
        content = (root / entry["file"]).read_text(encoding="utf-8").rstrip("\n")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if digest != entry.get("sha256"):
            raise EvalSetError(f"STARTER prompt hash mismatch: {prompt_id}")
        output[prompt_id] = {"version": entry["version"], "sha256": digest}
    return output


def build_eval_configuration(*, max_recovery_steps: int = 3) -> dict[str, Any]:
    repo_paths = {
        name: Path(value)
        for name, value in {
            "app": os.environ.get("RAG_EVAL_APP_REPO"),
            "mcp": os.environ.get("RAG_EVAL_MCP_REPO"),
            "starter": os.environ.get("RAG_EVAL_STARTER_REPO"),
        }.items()
        if value
    }
    configuration: dict[str, Any] = {
        "repositories": {name: _git_commit(path) for name, path in repo_paths.items()},
        "llm": {
            "provider": os.environ.get("LLM_PROVIDER"),
            "model": os.environ.get("LLM_MODEL"),
        },
        "embedding": {
            "provider": os.environ.get("EMBEDDING_PROVIDER"),
            "model": os.environ.get("EMBEDDING_MODEL"),
            "dimensions": os.environ.get("EMBEDDING_DIMENSIONS"),
        },
        "chunking": {
            "policy": os.environ.get("CHUNK_POLICY"),
            "target_words": os.environ.get("CHUNK_TARGET_WORDS"),
            "overlap_words": os.environ.get("CHUNK_OVERLAP_WORDS"),
        },
        "retrieval": {
            "mode": os.environ.get("RETRIEVAL_MODE"),
            "rerank_enabled": os.environ.get("RERANK_ENABLED"),
        },
        "orchestration": {
            "max_recovery_steps": max_recovery_steps,
            "expected_fact_scope": "generated_answer",
        },
    }
    starter = repo_paths.get("starter")
    if starter:
        configuration["starter_prompts"] = _external_prompt_metadata(starter)
    upload_dir = os.environ.get("UPLOAD_DIR")
    manifest = Path(upload_dir, "corpus-manifest.json") if upload_dir else None
    if manifest and manifest.exists():
        configuration["corpus_manifest_sha256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()
    return configuration


def _column_index(cell_ref: str) -> int:
    letters = re.sub(r"[^A-Z]", "", cell_ref.upper())
    index = 0
    for letter in letters:
        index = (index * 26) + (ord(letter) - ord("A") + 1)
    return index - 1


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    strings: list[str] = []
    for item in root.findall("main:si", NS):
        parts = [node.text or "" for node in item.findall(".//main:t", NS)]
        strings.append("".join(parts))
    return strings


def _cell_value(cell: ET.Element, shared_strings: Sequence[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//main:t", NS))
    value = cell.find("main:v", NS)
    if value is None or value.text is None:
        return ""
    if cell_type == "s":
        index = int(value.text)
        return shared_strings[index] if 0 <= index < len(shared_strings) else ""
    return value.text


def read_eval_json(path: str | Path) -> list[EvalCase]:
    """Read an eval set from JSON.

    Preferred over .xlsx: the question set is then plain text in the repository,
    so a reader can see exactly what was asked and what was expected.
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") not in {"1.0", "1.1"}:
        raise EvalSetError("eval set schema_version must be '1.0' or '1.1'")
    schema_version = payload["schema_version"]
    questions = payload.get("questions")
    if not isinstance(questions, list) or not questions:
        raise EvalSetError("eval set questions must be a non-empty list")
    if payload.get("eval_set") == "northwind-public-demo" and len(questions) != 25:
        raise EvalSetError("northwind-public-demo must contain exactly 25 questions")
    if payload.get("eval_set") == "northwind-operations-manual-v3.2" and len(questions) != 65:
        raise EvalSetError("northwind-operations-manual-v3.2 must contain exactly 65 questions")
    cases: list[EvalCase] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(questions, start=1):
        if not isinstance(item, dict):
            raise EvalSetError(f"question {index} must be an object")
        case_id = str(item.get("case_id") or "").strip()
        if not case_id:
            raise EvalSetError(f"question {index} is missing case_id")
        if case_id in seen_ids:
            raise EvalSetError(f"duplicate case_id: {case_id}")
        seen_ids.add(case_id)
        question = str(item.get("question") or "").strip()
        if not question:
            raise EvalSetError(f"{case_id} has an empty question")
        if schema_version == "1.0":
            if not isinstance(item.get("expect_refusal"), bool):
                raise EvalSetError(f"{case_id} must declare boolean expect_refusal")
            expects_refusal = item["expect_refusal"]
            expectation = "refuse" if expects_refusal else "answer"
            expected_document = item.get("expected_document")
            expected_fact = item.get("expected_fact")
            if expects_refusal:
                if expected_document is not None or expected_fact is not None:
                    raise EvalSetError(f"{case_id} refusal must have null expectations")
            elif not str(expected_document or "").strip() or not str(expected_fact or "").strip():
                raise EvalSetError(f"{case_id} answerable case needs document and fact")
            expected_documents = (
                (str(expected_document).strip(),) if expected_document is not None else ()
            )
            required_facts: tuple[EvalFact, ...] = ()
            forbidden_facts: tuple[str, ...] = ()
            ordered_fact_ids: tuple[str, ...] = ()
            document_match_policy = "any"
        else:
            expectation = str(item.get("expectation") or "").strip()
            if expectation not in {"answer", "refuse", "safe_boundary"}:
                raise EvalSetError(f"{case_id} has invalid expectation")
            expects_refusal = expectation == "refuse"
            raw_documents = item.get("expected_documents")
            if not isinstance(raw_documents, list) or any(
                not isinstance(value, str) or not value.strip() for value in raw_documents
            ):
                raise EvalSetError(f"{case_id} expected_documents must be a string list")
            expected_documents = tuple(value.strip() for value in raw_documents)
            if len(set(expected_documents)) != len(expected_documents):
                raise EvalSetError(f"{case_id} has duplicate expected_documents")
            document_match_policy = str(item.get("document_match_policy") or "any").strip()
            if document_match_policy not in {"any", "all"}:
                raise EvalSetError(f"{case_id} has invalid document_match_policy")
            raw_facts = item.get("required_facts")
            if not isinstance(raw_facts, list):
                raise EvalSetError(f"{case_id} required_facts must be a list")
            parsed_facts: list[EvalFact] = []
            seen_fact_ids: set[str] = set()
            for fact in raw_facts:
                if not isinstance(fact, dict):
                    raise EvalSetError(f"{case_id} contains a malformed required fact")
                fact_id = str(fact.get("id") or "").strip()
                aliases = fact.get("any_of")
                if (
                    not fact_id
                    or fact_id in seen_fact_ids
                    or not isinstance(aliases, list)
                    or not aliases
                    or any(not isinstance(alias, str) or not alias.strip() for alias in aliases)
                ):
                    raise EvalSetError(f"{case_id} contains an invalid required fact")
                seen_fact_ids.add(fact_id)
                evidence_required = fact.get("evidence_required", True)
                if not isinstance(evidence_required, bool):
                    raise EvalSetError(
                        f"{case_id} fact {fact_id} evidence_required must be boolean"
                    )
                parsed_facts.append(
                    EvalFact(
                        fact_id=fact_id,
                        any_of=tuple(alias.strip() for alias in aliases),
                        evidence_required=evidence_required,
                    )
                )
            required_facts = tuple(parsed_facts)
            raw_forbidden = item.get("forbidden_facts", [])
            if not isinstance(raw_forbidden, list) or any(
                not isinstance(value, str) or not value.strip() for value in raw_forbidden
            ):
                raise EvalSetError(f"{case_id} forbidden_facts must be a string list")
            forbidden_facts = tuple(value.strip() for value in raw_forbidden)
            raw_order = item.get("ordered_fact_ids", [])
            if not isinstance(raw_order, list) or any(
                not isinstance(value, str) or not value.strip() for value in raw_order
            ):
                raise EvalSetError(f"{case_id} ordered_fact_ids must be a string list")
            ordered_fact_ids = tuple(value.strip() for value in raw_order)
            if len(set(ordered_fact_ids)) != len(ordered_fact_ids) or not set(
                ordered_fact_ids
            ).issubset(seen_fact_ids):
                raise EvalSetError(f"{case_id} ordered_fact_ids must reference unique facts")
            aliases_normalized = {
                _normalized_fact_text(alias) for fact in required_facts for alias in fact.any_of
            }
            if aliases_normalized.intersection(
                _normalized_fact_text(value) for value in forbidden_facts
            ):
                raise EvalSetError(f"{case_id} has contradictory required and forbidden facts")
            if expectation == "refuse":
                if expected_documents or required_facts or ordered_fact_ids:
                    raise EvalSetError(f"{case_id} refusal cannot require documents or facts")
            elif not expected_documents or not required_facts:
                raise EvalSetError(f"{case_id} {expectation} needs documents and required facts")
            for field in ("question_type", "difficulty", "rationale"):
                if not str(item.get(field) or "").strip():
                    raise EvalSetError(f"{case_id} is missing {field}")
            raw_sections = item.get("source_sections", [])
            if not isinstance(raw_sections, list) or any(
                not isinstance(value, str) or not value.strip() for value in raw_sections
            ):
                raise EvalSetError(f"{case_id} source_sections must be a string list")
            expected_document = expected_documents[0] if expected_documents else None
            expected_fact = "; ".join(fact.any_of[0] for fact in required_facts)
        cases.append(
            EvalCase(
                question=question,
                expected_answer=str(expected_fact or "").strip(),
                file_name=str(expected_document).strip()
                if expected_document is not None
                else None,
                expect_refusal=expects_refusal,
                case_id=case_id,
                schema_version=schema_version,
                expectation=expectation,
                expected_documents=expected_documents,
                document_match_policy=document_match_policy,
                required_facts=required_facts,
                forbidden_facts=forbidden_facts,
                ordered_fact_ids=ordered_fact_ids,
                question_type=str(item.get("question_type") or "").strip() or None,
                difficulty=str(item.get("difficulty") or "").strip() or None,
                rationale=str(item.get("rationale") or "").strip() or None,
                source_sections=tuple(
                    str(value).strip() for value in item.get("source_sections", [])
                ),
            )
        )
    if payload.get("eval_set") == "northwind-public-demo":
        refusal_count = sum(case.expect_refusal for case in cases)
        if refusal_count != 5:
            raise EvalSetError(
                "northwind-public-demo must contain 20 answerable and 5 refusal cases"
            )
    return cases


def read_eval_cases(path: str | Path) -> list[EvalCase]:
    """Dispatch on file type so both eval-set formats work."""
    return read_eval_json(path) if str(path).endswith(".json") else read_eval_xlsx(path)


def read_eval_xlsx(path: str | Path) -> list[EvalCase]:
    xlsx_path = Path(path)
    with zipfile.ZipFile(xlsx_path) as archive:
        shared_strings = _shared_strings(archive)
        worksheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))

    rows: list[list[str]] = []
    for row in worksheet.findall(".//main:row", NS):
        values: dict[int, str] = {}
        max_index = -1
        for cell in row.findall("main:c", NS):
            index = _column_index(cell.attrib.get("r", "A1"))
            values[index] = _cell_value(cell, shared_strings)
            max_index = max(max_index, index)
        rows.append([values.get(index, "") for index in range(max_index + 1)])

    if not rows:
        return []
    headers = [str(value).strip() for value in rows[0]]
    cases: list[EvalCase] = []
    for row_index, row in enumerate(rows[1:], start=1):
        record = {
            headers[index]: row[index] if index < len(row) else "" for index in range(len(headers))
        }
        question = str(record.get("question") or "").strip()
        expected = str(record.get("human_answer") or "").strip()
        if not question or not expected:
            continue
        cases.append(
            EvalCase(
                question=question,
                expected_answer=expected,
                file_name=str(record.get("file_name") or "").strip() or None,
                post_url=str(record.get("post_url") or "").strip() or None,
                case_id=f"XLSX-{row_index:03d}",
            )
        )
    return cases


# Every status in which the system declined to produce a grounded answer.
# "not_found" belongs here for the same reason "not_grounded" does: the system
# said it could not answer. Omitting it scored a correct refusal as a failure.
# A must-refuse case passes only when the orchestrator emits one of its two
# terminal no-answer states. ``needs_review`` is deliberately excluded: that
# path may contain a synthesized answer from rejected evidence and therefore is
# not a refusal.
REFUSAL_STATUSES = {"not_grounded", "not_found"}
INFRASTRUCTURE_STATUSES = {"backend_auth_failed", "backend_timeout", "tool_error"}
BOUNDARY_MARKERS = (
    "not in",
    "not provided",
    "not available",
    "cannot provide",
    "separate",
    "refer to",
    "controlled document",
    "restricted",
)


def _normalized_fact_text(value: Any) -> str:
    text = str(value or "").casefold().replace("€", " eur ")
    text = re.sub(r"(?<=\d)[,.](?=\d)", "", text)
    return " ".join(re.findall(r"[a-z0-9]+", text))


def _alias_position(text: str, aliases: Sequence[str]) -> int | None:
    normalized = _normalized_fact_text(text)
    positions = [normalized.find(_normalized_fact_text(alias)) for alias in aliases]
    found = [position for position in positions if position >= 0]
    return min(found) if found else None


def _fact_results(
    *, answer: str, evidence: Sequence[dict[str, Any]], case: EvalCase
) -> list[dict[str, Any]]:
    evidence_text = " ".join(
        str(item.get("snippet") or item.get("text") or item.get("content") or "")
        for item in evidence
        if isinstance(item, dict)
    )
    return [
        {
            "fact_id": fact.fact_id,
            "answer_matched": _alias_position(answer, fact.any_of) is not None,
            "evidence_required": fact.evidence_required,
            "evidence_matched": (
                _alias_position(evidence_text, fact.any_of) is not None
                if fact.evidence_required
                else None
            ),
        }
        for fact in case.required_facts
    ]


def _forbidden_matches(answer: str, forbidden_facts: Sequence[str]) -> list[str]:
    return [value for value in forbidden_facts if _alias_position(answer, (value,)) is not None]


def _facts_in_required_order(answer: str, case: EvalCase) -> bool:
    if not case.ordered_fact_ids:
        return True
    by_id = {fact.fact_id: fact for fact in case.required_facts}
    positions = [
        _alias_position(answer, by_id[fact_id].any_of) for fact_id in case.ordered_fact_ids
    ]
    return all(position is not None for position in positions) and positions == sorted(positions)


def _normalized_document(value: Any) -> str:
    text = str(value or "").strip().lower().replace("\\", "/").rsplit("/", 1)[-1]
    return re.sub(r"\.(md|txt|pdf|docx|html?)$", "", text)


def _expected_document_matched(
    run: dict[str, Any], expected_documents: Sequence[str], match_policy: str = "any"
) -> bool | None:
    if not expected_documents:
        return None
    expected = {_normalized_document(value) for value in expected_documents}
    candidates: list[Any] = []
    for key in ("citations", "evidence", "source_evidence"):
        value = run.get(key) or []
        if isinstance(value, list):
            candidates.extend(value)
    found: set[str] = set()
    for item in candidates:
        if isinstance(item, dict):
            for key in ("file_name", "source", "document", "document_name"):
                normalized = _normalized_document(item.get(key))
                if normalized in expected:
                    found.add(normalized)
    return found == expected if match_policy == "all" else bool(found)


def _eval_status(
    run: dict[str, Any],
    expected_eval: dict[str, Any],
    case: EvalCase | None = None,
    *,
    expected_document_matched: bool | None = None,
) -> str:
    grounding = run.get("grounding_status")

    if case is not None and case.expect_refusal:
        # The corpus cannot answer this. Declining is correct; producing a
        # confident grounded answer is the failure.
        return "pass" if grounding in REFUSAL_STATUSES else "fail"

    if case is not None and case.schema_version == "1.1":
        fact_results = expected_eval.get("required_facts") or []
        facts_pass = bool(fact_results) and all(
            item.get("answer_matched")
            and (item.get("evidence_matched") if item.get("evidence_required", True) else True)
            for item in fact_results
        )
        no_forbidden_facts = not expected_eval.get("forbidden_fact_matches")
        order_pass = expected_eval.get("ordered_facts_matched") is not False
        if case.expectation == "safe_boundary":
            boundary_present = expected_eval.get("boundary_present") is True
            if (
                grounding in {"verified", "grounded", "recovered"}
                and facts_pass
                and no_forbidden_facts
                and order_pass
                and boundary_present
                and expected_document_matched is True
            ):
                return "pass"
        elif (
            grounding in {"verified", "grounded", "recovered"}
            and facts_pass
            and no_forbidden_facts
            and order_pass
            and expected_document_matched is True
        ):
            return "pass"
        if grounding in {"partial", "needs_review"}:
            return "manual_review"
        return "fail"

    if (
        grounding in {"verified", "grounded", "recovered"}
        and expected_eval.get("status") == "pass"
    ):
        return "pass"
    if grounding in {"partial", "needs_review"}:
        return "manual_review"
    return "fail"


def _backend_request_ids(run: dict[str, Any]) -> list[str]:
    """Collect sanitized STARTER retrieval IDs from MCP tool responses.

    One APP case can make more than one backend request during recovery.  The
    isolated full-stack workflow uses these opaque IDs to join the case report
    to STARTER's generation-usage table without exporting questions, prompts,
    users, or raw traces.
    """
    request_ids: list[str] = []
    seen: set[str] = set()
    for output in run.get("tool_outputs") or []:
        if not isinstance(output, dict):
            continue
        content = output.get("content")
        if not isinstance(content, dict):
            continue
        debug_info = content.get("debug_info")
        if not isinstance(debug_info, dict):
            continue
        retrieval_trace = debug_info.get("retrieval_trace")
        if not isinstance(retrieval_trace, dict):
            continue
        request_id = str(retrieval_trace.get("request_id") or "").strip()
        if request_id and request_id not in seen:
            seen.add(request_id)
            request_ids.append(request_id)
    return request_ids


async def run_eval(
    *,
    xlsx_path: str | Path | None = None,
    eval_path: str | Path | None = None,
    orchestrator: EnterpriseRagOrchestrator | None = None,
    rules_path: str | Path | None = None,
    journal_path: str | Path | None = None,
    max_recovery_steps: int = 3,
    configuration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_path = eval_path or xlsx_path
    if source_path is None:
        raise EvalSetError("eval_path is required")
    rules = load_rules(rules_path)
    cases = read_eval_cases(source_path)
    runtime_orchestrator = orchestrator or EnterpriseRagOrchestrator(
        rules_path=str(rules_path) if rules_path else None,
        journal_path=str(journal_path) if journal_path else None,
    )
    rows: list[dict[str, Any]] = []
    for case in cases:
        started = time.perf_counter()
        result = await runtime_orchestrator.run(
            case.question,
            max_recovery_steps=max_recovery_steps,
            expected_answer=case.expected_answer,
            journal_path=str(journal_path) if journal_path else None,
        )
        end_to_end_latency_ms = round((time.perf_counter() - started) * 1000, 3)
        run = result.to_dict()
        answer = str(run.get("answer") or "")
        evidence = run.get("evidence") or []
        if case.schema_version == "1.1":
            expected_eval = {
                "status": "mechanical",
                "required_facts": _fact_results(answer=answer, evidence=evidence, case=case),
                "forbidden_fact_matches": _forbidden_matches(answer, case.forbidden_facts),
                "ordered_facts_matched": _facts_in_required_order(answer, case),
                "boundary_present": (
                    any(marker in answer.casefold() for marker in BOUNDARY_MARKERS)
                    if case.expectation == "safe_boundary"
                    else None
                ),
            }
        else:
            expected_eval = evaluate_expected_answer(
                answer=answer,
                evidence=evidence,
                expected_answer=case.expected_answer,
                question=case.question,
                rules=rules,
            )
        expected_document_matched = _expected_document_matched(
            run,
            case.expected_documents or ((case.file_name,) if case.file_name else ()),
            case.document_match_policy,
        )
        eval_status = _eval_status(
            run,
            expected_eval,
            case,
            expected_document_matched=expected_document_matched,
        )
        failure_class = (
            "infrastructure"
            if run.get("grounding_status") in INFRASTRUCTURE_STATUSES
            else ("quality" if eval_status != "pass" else None)
        )
        rows.append(
            {
                "case_id": case.case_id,
                "question": case.question,
                "expected_answer": case.expected_answer,
                "generated_answer": run.get("answer"),
                "grounding_status": run.get("grounding_status"),
                "evidence_verdict": run.get("evidence_verdict"),
                "tools_used": run.get("tools_used") or [],
                "eval_status": eval_status,
                "expect_refusal": case.expect_refusal,
                "expectation": case.expectation,
                "refusal_passed": eval_status == "pass" if case.expect_refusal else None,
                "expected_document_matched": expected_document_matched,
                "expected_documents": list(case.expected_documents),
                "document_match_policy": case.document_match_policy,
                "question_type": case.question_type,
                "difficulty": case.difficulty,
                "source_sections": list(case.source_sections),
                "expected_eval": expected_eval,
                "failure_class": failure_class,
                "failure_reason": run.get("failure_reason"),
                "error": run.get("error"),
                "file_name": case.file_name,
                "post_url": case.post_url,
                "latency_ms": run.get("latency_ms"),
                "end_to_end_latency_ms": end_to_end_latency_ms,
                "recovery_attempted": bool(run.get("recovery_attempted")),
                "recovery_successful": bool(run.get("recovery_successful")),
                "attempt_count": len(run.get("attempts") or []),
                "backend_request_ids": _backend_request_ids(run),
                "run_id": run.get("run_id"),
            }
        )
    passed = sum(1 for row in rows if row["eval_status"] == "pass")
    failed = sum(1 for row in rows if row["eval_status"] == "fail")
    manual = sum(1 for row in rows if row["eval_status"] == "manual_review")
    refusal_total = sum(1 for row in rows if row["expect_refusal"])
    refusal_passed = sum(1 for row in rows if row["refusal_passed"] is True)
    infrastructure_failures = sum(1 for row in rows if row["failure_class"] == "infrastructure")
    return {
        "schema_version": cases[0].schema_version if cases else "1.0",
        "eval_set": str(source_path),
        "total": len(rows),
        "passed": passed,
        "failed": failed,
        "manual_review": manual,
        "refusal_total": refusal_total,
        "refusal_passed": refusal_passed,
        "safe_boundary_total": sum(1 for row in rows if row["expectation"] == "safe_boundary"),
        "safe_boundary_passed": sum(
            1
            for row in rows
            if row["expectation"] == "safe_boundary" and row["eval_status"] == "pass"
        ),
        "infrastructure_failures": infrastructure_failures,
        "configuration": {
            "app_prompts": prompt_metadata(),
            **(configuration or {}),
        },
        "status": "pass" if rows and failed == 0 and manual == 0 else "fail",
        "rows": rows,
    }


def render_eval_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# RAG Evaluation Report",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Total | {report.get('total', 0)} |",
        f"| Passed | {report.get('passed', 0)} |",
        f"| Failed | {report.get('failed', 0)} |",
        f"| Manual review | {report.get('manual_review', 0)} |",
        "",
        "## Results",
        "",
        "| # | Status | Question | Expected | Generated | Grounding | Tools | Evidence Verdict |",
        "| ---: | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for index, row in enumerate(report.get("rows", []), start=1):
        verdict = row.get("evidence_verdict") or {}
        tools = ", ".join(f"`{tool}`" for tool in row.get("tools_used") or []) or "-"
        values = [
            str(index),
            str(row.get("eval_status") or "-"),
            _table_text(row.get("question")),
            _table_text(row.get("expected_answer"), 180),
            _table_text(row.get("generated_answer"), 220),
            _table_text(row.get("grounding_status")),
            tools,
            _table_text(
                verdict.get("reason") or row.get("failure_reason") or row.get("error") or "-"
            ),
        ]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines).rstrip() + "\n"


def _table_text(value: Any, limit: int = 140) -> str:
    text = " ".join(str(value or "-").replace("|", "\\|").split())
    if len(text) > limit:
        return text[: limit - 3].rstrip() + "..."
    return text


def write_eval_outputs(
    report: dict[str, Any],
    *,
    markdown_path: str | Path | None = None,
    json_path: str | Path | None = None,
) -> dict[str, str]:
    safe_report = redact_for_sharing(report)
    written: dict[str, str] = {}
    if markdown_path:
        path = Path(markdown_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_eval_markdown(safe_report), encoding="utf-8")
        written["markdown"] = str(path)
    if json_path:
        path = Path(json_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(safe_report, indent=2, sort_keys=True), encoding="utf-8")
        written["json"] = str(path)
    return written


def run_eval_sync(**kwargs: Any) -> dict[str, Any]:
    return asyncio.run(run_eval(**kwargs))
