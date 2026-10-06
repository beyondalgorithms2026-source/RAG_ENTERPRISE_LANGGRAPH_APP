from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from rag_enterprise_langgraph.answer_quality import classify_question, review_answer
from rag_enterprise_langgraph.prompt_registry import load_prompt

SYNTHESIS_SYSTEM_PROMPT = load_prompt("app_synthesis")

_REFUSAL_MARKERS = (
    "not_answerable",
    "does not answer",
    "cannot answer",
    "no information",
    "not stated in",
    "not mentioned",
)

_STOP_ENTITIES = {
    "Yes",  # yes/no answers start with it; it is not a named entity
    "SOURCE",  # the prompt's own labels; a model may echo them ("according to the SOURCE")
    "QUESTION",
    "The",
    "This",
    "That",
    "These",
    "Those",
    "Based",
    "Source",
    "Their",
    "There",
    "When",
    "Where",
    "What",
    "Which",
    "While",
    "About",
    "According",
}


def _evidence_text(evidence: Sequence[dict[str, Any]]) -> str:
    return " ".join(
        str(item.get("snippet") or item.get("excerpt") or "") for item in evidence
    ).strip()


def _numeric_tokens(text: str) -> list[str]:
    # Percentages, decimals, and integers (with optional commas), normalized.
    tokens = re.findall(r"\d+(?:[.,]\d+)?\s*%|\d[\d,]*(?:\.\d+)?", text)
    # "250,000," at the end of a clause is the number 250,000, not a different token.
    return [re.sub(r"\s+", "", token).rstrip(",") for token in tokens]


def _capitalized_entities(text: str) -> list[str]:
    words = re.findall(r"\b[A-Z][A-Za-z0-9][A-Za-z0-9'\-]+\b", text)
    return [word for word in words if word not in _STOP_ENTITIES]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).lower()


def verify_against_evidence(
    answer: str, evidence: Sequence[dict[str, Any]], *, question: str = ""
) -> dict[str, Any]:
    """Return {'verified': bool, 'reason': str}. Conservative: any unproven fact fails."""
    answer_text = str(answer or "").strip()
    if not answer_text:
        return {"verified": False, "reason": "empty_answer"}
    lowered = answer_text.lower()
    if any(marker in lowered for marker in _REFUSAL_MARKERS):
        return {"verified": False, "reason": "model_declined"}

    evidence_text = _evidence_text(evidence)
    evidence_norm = _normalize(evidence_text)
    # Values and names the question itself supplies may be restated for comparison
    # ("EUR 260,000 is above the EUR 250,000 threshold"); they are not invented facts.
    question_norm = _normalize(question)
    evidence_numeric = set(_numeric_tokens(evidence_text)) | set(_numeric_tokens(question))

    for token in _numeric_tokens(answer_text):
        if token in evidence_numeric:
            continue
        # Allow a bare number that appears inside a percent in the source (e.g. "2" within "2%") and vice versa.
        bare = token.rstrip("%")
        if any(bare == existing.rstrip("%") for existing in evidence_numeric):
            continue
        return {"verified": False, "reason": f"unsupported_number:{token}"}

    for entity in _capitalized_entities(answer_text):
        if entity.lower() not in evidence_norm and entity.lower() not in question_norm:
            return {"verified": False, "reason": f"unsupported_entity:{entity}"}

    # Require real lexical overlap with the source so the answer is grounded, not generic.
    answer_words = {word for word in re.findall(r"[a-z0-9]{4,}", lowered)}
    overlap = sum(1 for word in answer_words if word in evidence_norm)
    if answer_words and overlap / len(answer_words) < 0.5:
        return {"verified": False, "reason": "low_source_overlap"}

    return {"verified": True, "reason": "all_facts_supported"}


async def synthesize_and_verify(
    *,
    question: str,
    evidence: Sequence[dict[str, Any]],
    question_profile=None,
    model=None,
    settings=None,
) -> dict[str, Any]:
    """Compose a readable answer from evidence, then verify it against the source.

    Returns {'answer': str|None, 'verified': bool, 'reason': str}. The caller
    shows the answer only when verified; otherwise it falls back to the verbatim
    quote. `model` must expose an async ``ainvoke`` returning an object with a
    ``.content`` string; when omitted it is built from ``settings``.
    """
    evidence_text = _evidence_text(evidence)
    if not evidence_text:
        return {"answer": None, "verified": False, "reason": "no_evidence"}

    if model is None:
        if settings is None:
            return {"answer": None, "verified": False, "reason": "no_model"}
        from rag_enterprise_langgraph.graph import build_chat_model

        # A missing key or unknown provider must fall back to the verbatim answer, not fail the run.
        try:
            model = build_chat_model(settings)
        except Exception as exc:
            return {
                "answer": None,
                "verified": False,
                "reason": f"model_error:{exc.__class__.__name__}",
            }

    prompt = (
        f"QUESTION: {question}\n\n"
        f'SOURCE:\n"""\n{evidence_text[:4000]}\n"""\n\n'
        "Write the answer now."
    )
    messages = [
        {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    first = await _attempt(model, messages, question, evidence, question_profile)
    missing = _unstated_question_values(question, first["answer"]) if first["verified"] else []
    if not missing:
        return first
    # A yes/no comparison answer should state the value it compares (OM-046 kept omitting
    # "EUR 260,000"). One retry names the value; it is used only if it verifies and states it.
    retry = await _attempt(
        model,
        [
            *messages,
            {"role": "assistant", "content": first["answer"]},
            {
                "role": "user",
                "content": "Rewrite the answer so it states the value given in the QUESTION ("
                + ", ".join(missing)
                + ") when comparing it with the SOURCE rule. Keep every other rule.",
            },
        ],
        question,
        evidence,
        question_profile,
    )
    if retry["verified"] and not _unstated_question_values(question, retry["answer"]):
        return retry
    return first


_COMPARISON_OPENER = re.compile(
    r"^(is|are|does|do|did|would|will|can|could|has|have|should|must|may)\b", re.IGNORECASE
)


def _unstated_question_values(question: str, answer: str | None) -> list[str]:
    """Numbers a yes/no comparison question gives that the answer does not state."""
    sentences = re.split(r"(?<=[.?!])\s+", question.strip())
    if not any(_COMPARISON_OPENER.match(sentence) for sentence in sentences):
        return []
    given = list(dict.fromkeys(_numeric_tokens(question)))
    stated = {token.rstrip("%") for token in _numeric_tokens(answer or "")}
    if not given or any(token.rstrip("%") in stated for token in given):
        return []
    return given


async def _attempt(model, messages, question, evidence, question_profile) -> dict[str, Any]:
    try:
        response = await model.ainvoke(messages)
    except Exception as exc:
        return {
            "answer": None,
            "verified": False,
            "reason": f"model_error:{exc.__class__.__name__}",
        }

    content = getattr(response, "content", response)
    answer = content if isinstance(content, str) else str(content)
    answer = re.sub(r"\s+", " ", answer).strip()
    # Remove quotes only when they wrap the whole answer; stripping one side left a stray
    # opening quote ('as it is "financial exposure above ...') that no longer matched quotes of it.
    if len(answer) >= 2 and answer[0] == answer[-1] == '"':
        answer = answer[1:-1].strip()
    # Readers never see the prompt's labels: "according to the SOURCE" -> "according to the source".
    answer = re.sub(r"\b(SOURCE|QUESTION)\b", lambda m: m.group(1).lower(), answer)

    verdict = verify_against_evidence(answer, evidence, question=question)
    if not verdict["verified"]:
        return {"answer": answer, "verified": False, "reason": verdict["reason"]}

    # Second gate: the shared answer reviewer must not find unsupported items.
    profile = question_profile or classify_question(question)
    review = review_answer(
        question=question, answer=answer, evidence=list(evidence), question_profile=profile
    )
    if review.unsupported_items:
        return {"answer": answer, "verified": False, "reason": "reviewer_unsupported_items"}

    return {"answer": answer, "verified": True, "reason": "verified"}
