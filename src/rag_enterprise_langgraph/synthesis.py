from __future__ import annotations

import re
from typing import Any, Sequence

from rag_enterprise_langgraph.answer_quality import classify_question, review_answer


SYNTHESIS_SYSTEM_PROMPT = (
    "You rewrite retrieved source text into a short, direct answer.\n"
    "Hard rules:\n"
    "- Use ONLY facts stated in the SOURCE text below. Add nothing.\n"
    "- Do not introduce any number, percentage, name, date, or claim that is not in the SOURCE.\n"
    "- Do not use outside knowledge. Do not speculate.\n"
    "- If the SOURCE does not answer the question, reply exactly: NOT_ANSWERABLE\n"
    "- Answer in 1-2 plain sentences. No preamble, no citations, no quotes."
)

_REFUSAL_MARKERS = ("not_answerable", "does not answer", "cannot answer", "no information", "not stated in", "not mentioned")

_STOP_ENTITIES = {
    "The", "This", "That", "These", "Those", "Based", "Source", "Their", "There",
    "When", "Where", "What", "Which", "While", "About", "According",
}


def _evidence_text(evidence: Sequence[dict[str, Any]]) -> str:
    return " ".join(str(item.get("snippet") or item.get("excerpt") or "") for item in evidence).strip()


def _numeric_tokens(text: str) -> list[str]:
    # Percentages, decimals, and integers (with optional commas), normalized.
    tokens = re.findall(r"\d+(?:[.,]\d+)?\s*%|\d[\d,]*(?:\.\d+)?", text)
    return [re.sub(r"\s+", "", token) for token in tokens]


def _capitalized_entities(text: str) -> list[str]:
    words = re.findall(r"\b[A-Z][A-Za-z0-9][A-Za-z0-9'\-]+\b", text)
    return [word for word in words if word not in _STOP_ENTITIES]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).lower()


def verify_against_evidence(answer: str, evidence: Sequence[dict[str, Any]], *, question: str = "") -> dict[str, Any]:
    """Return {'verified': bool, 'reason': str}. Conservative: any unproven fact fails."""
    answer_text = str(answer or "").strip()
    if not answer_text:
        return {"verified": False, "reason": "empty_answer"}
    lowered = answer_text.lower()
    if any(marker in lowered for marker in _REFUSAL_MARKERS):
        return {"verified": False, "reason": "model_declined"}

    evidence_text = _evidence_text(evidence)
    evidence_norm = _normalize(evidence_text)
    evidence_numeric = set(_numeric_tokens(evidence_text))

    for token in _numeric_tokens(answer_text):
        if token in evidence_numeric:
            continue
        # Allow a bare number that appears inside a percent in the source (e.g. "2" within "2%") and vice versa.
        bare = token.rstrip("%")
        if any(bare == existing.rstrip("%") for existing in evidence_numeric):
            continue
        return {"verified": False, "reason": f"unsupported_number:{token}"}

    for entity in _capitalized_entities(answer_text):
        if entity.lower() not in evidence_norm:
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

        model = build_chat_model(settings)

    prompt = (
        f"QUESTION: {question}\n\n"
        f"SOURCE:\n\"\"\"\n{evidence_text[:4000]}\n\"\"\"\n\n"
        "Write the answer now."
    )
    try:
        response = await model.ainvoke(
            [
                {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
        )
    except Exception as exc:  # noqa: BLE001 - any model failure falls back to verbatim
        return {"answer": None, "verified": False, "reason": f"model_error:{exc.__class__.__name__}"}

    content = getattr(response, "content", response)
    answer = content if isinstance(content, str) else str(content)
    answer = re.sub(r"\s+", " ", answer).strip().strip('"')

    verdict = verify_against_evidence(answer, evidence, question=question)
    if not verdict["verified"]:
        return {"answer": answer, "verified": False, "reason": verdict["reason"]}

    # Second gate: the shared answer reviewer must not find unsupported items.
    profile = question_profile or classify_question(question)
    review = review_answer(question=question, answer=answer, evidence=list(evidence), question_profile=profile)
    if review.unsupported_items:
        return {"answer": answer, "verified": False, "reason": "reviewer_unsupported_items"}

    return {"answer": answer, "verified": True, "reason": "verified"}
