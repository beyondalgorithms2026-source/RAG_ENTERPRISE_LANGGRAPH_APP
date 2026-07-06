from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Sequence


QUESTION_TYPES = (
    "exact_numeric",
    "percentage_or_ratio",
    "date_or_time",
    "person_or_org",
    "location",
    "list_with_count",
    "definition",
    "comparison",
    "cause_or_reason",
    "process_or_steps",
    "summary",
    "policy_or_compliance",
    "yes_no",
    "quote_or_exact_wording",
    "open_ended_analysis",
)


@dataclass(frozen=True)
class AnswerShape:
    item_count: int | None = None
    requires_numeric: bool = False
    requires_percentage: bool = False
    requires_date: bool = False
    requires_location: bool = False
    requires_named_entity: bool = False
    requires_exact_quote: bool = False
    requires_cited_support_per_item: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_count": self.item_count,
            "requires_numeric": self.requires_numeric,
            "requires_percentage": self.requires_percentage,
            "requires_date": self.requires_date,
            "requires_location": self.requires_location,
            "requires_named_entity": self.requires_named_entity,
            "requires_exact_quote": self.requires_exact_quote,
            "requires_cited_support_per_item": self.requires_cited_support_per_item,
        }


@dataclass(frozen=True)
class QuestionProfile:
    question_types: list[str]
    expected_answer_shape: AnswerShape
    answer_risk: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "question_types": self.question_types,
            "expected_answer_shape": self.expected_answer_shape.to_dict(),
            "answer_risk": self.answer_risk,
        }


@dataclass(frozen=True)
class AnswerItemSupport:
    text: str
    supported: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "supported": self.supported, "reason": self.reason}


@dataclass(frozen=True)
class AnswerReview:
    status: str
    reason: str
    question_profile: QuestionProfile
    evidence_support: str
    review_recommended: bool
    supported_items: int = 0
    required_items: int | None = None
    answer_values: list[str] = field(default_factory=list)
    citation_values: list[str] = field(default_factory=list)
    unsupported_items: list[AnswerItemSupport] = field(default_factory=list)
    supported_item_details: list[AnswerItemSupport] = field(default_factory=list)
    needs_neighbor_expansion: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "question_profile": self.question_profile.to_dict(),
            "evidence_support": self.evidence_support,
            "review_recommended": self.review_recommended,
            "supported_items": self.supported_items,
            "required_items": self.required_items,
            "answer_values": self.answer_values,
            "citation_values": self.citation_values,
            "unsupported_items": [item.to_dict() for item in self.unsupported_items],
            "supported_item_details": [item.to_dict() for item in self.supported_item_details],
            "needs_neighbor_expansion": self.needs_neighbor_expansion,
        }


_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


def _normalize(value: Any) -> str:
    text = str(value or "").lower()
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip()


def _answer_text(evidence: Sequence[dict[str, Any]]) -> str:
    return " ".join(str(item.get("snippet") or item.get("excerpt") or "") for item in evidence)


def _numbers(text: str) -> list[str]:
    return re.findall(r"\b\d+(?:\.\d+)?\b", text)


def _percentages(text: str) -> list[str]:
    values = re.findall(r"\b\d+(?:\.\d+)?\s*%", text)
    values.extend(re.findall(r"\b0\.\d+\b", text))
    return values


def _item_count(question: str) -> int | None:
    lowered = _normalize(question)
    digit = re.search(r"\b(\d+)\s+(?:\w+\s+){0,3}(?:things|items|reasons|steps|ways|factors|points|examples)\b", lowered)
    if digit:
        return int(digit.group(1))
    for word, number in _NUMBER_WORDS.items():
        if re.search(rf"\b{word}\s+(?:\w+\s+){{0,3}}(?:things|items|reasons|steps|ways|factors|points|examples)\b", lowered):
            return number
    return None


def classify_question(question: str) -> QuestionProfile:
    lowered = _normalize(question)
    types: list[str] = []
    count = _item_count(question)
    requires_numeric = any(marker in lowered for marker in ("how much", "how many", "cost", "revenue", "price", "amount"))
    material_cost_share = "cost" in lowered and "material" in lowered
    requires_percentage = any(marker in lowered for marker in ("percentage", "percent", "ratio", "%", "rent to sales")) or material_cost_share
    requires_date = any(marker in lowered for marker in ("when", "date", "year", "formed", "founded"))
    requires_location = lowered.startswith("where") or " based in" in lowered or " located" in lowered
    requires_named_entity = lowered.startswith("who") or "which" in lowered
    requires_exact_quote = any(marker in lowered for marker in ("quote", "exact", "final words", "wording"))

    if requires_numeric:
        types.append("exact_numeric")
    if requires_percentage:
        types.append("percentage_or_ratio")
    if requires_date:
        types.append("date_or_time")
    if requires_named_entity:
        types.append("person_or_org")
    if requires_location:
        types.append("location")
    if count:
        types.append("list_with_count")
    if any(marker in lowered for marker in ("what is", "define", "definition")) and not count:
        types.append("definition")
    if any(marker in lowered for marker in ("compare", "different", "unique from", "versus", " vs ", "similar")):
        types.append("comparison")
    if lowered.startswith("why") or "reason" in lowered:
        types.append("cause_or_reason")
    if lowered.startswith("how does") or "process" in lowered or "steps" in lowered:
        types.append("process_or_steps")
    if "summarize" in lowered or "summary" in lowered:
        types.append("summary")
    if any(marker in lowered for marker in ("policy", "allowed", "forbidden", "compliance", "approval")):
        types.append("policy_or_compliance")
    if re.match(r"^(does|do|did|is|are|can|should|was|were)\b", lowered):
        types.append("yes_no")
    if requires_exact_quote:
        types.append("quote_or_exact_wording")
    if not types:
        types.append("open_ended_analysis")

    shape = AnswerShape(
        item_count=count,
        requires_numeric=requires_numeric,
        requires_percentage=requires_percentage,
        requires_date=requires_date,
        requires_location=requires_location,
        requires_named_entity=requires_named_entity,
        requires_exact_quote=requires_exact_quote,
        requires_cited_support_per_item=bool(count),
    )
    risk = "high" if any(item in types for item in ("policy_or_compliance", "quote_or_exact_wording")) else "medium" if any(
        item in types for item in ("list_with_count", "percentage_or_ratio", "exact_numeric", "comparison")
    ) else "low"
    return QuestionProfile(question_types=types, expected_answer_shape=shape, answer_risk=risk)


def extract_answer_items(answer: str) -> list[str]:
    text = str(answer or "").strip()
    if not text:
        return []
    numbered = re.findall(r"(?:^|\n|\s)(?:\d+[\).\:-]\s+)(.*?)(?=(?:\n|\s)\d+[\).\:-]\s+|$)", text, flags=re.DOTALL)
    bullets = re.findall(r"(?:^|\n)\s*[-*]\s+(.*?)(?=\n\s*[-*]\s+|$)", text, flags=re.DOTALL)
    items = numbered or bullets
    if not items:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        items = [sentence for sentence in sentences if sentence.strip()]
    cleaned: list[str] = []
    for item in items:
        normalized = re.sub(r"\s+", " ", item).strip(" ;:")
        if len(normalized) >= 12:
            cleaned.append(normalized[:500])
    return cleaned[:10]


def _word_set(text: str) -> set[str]:
    stop = {
        "about",
        "against",
        "also",
        "because",
        "between",
        "could",
        "from",
        "into",
        "that",
        "their",
        "there",
        "these",
        "this",
        "those",
        "what",
        "when",
        "where",
        "which",
        "with",
        "would",
    }
    return {token for token in re.findall(r"[a-z0-9][a-z0-9%-]*", _normalize(text)) if len(token) >= 4 and token not in stop}


def _support_for_item(item: str, evidence_text: str) -> AnswerItemSupport:
    item_words = _word_set(item)
    if not item_words:
        return AnswerItemSupport(item, False, "no_meaningful_terms")
    evidence_words = _word_set(evidence_text)
    hits = sorted(item_words & evidence_words)
    coverage = len(hits) / max(1, min(len(item_words), 8))
    if coverage >= 0.45:
        return AnswerItemSupport(item, True, "citation_terms_overlap")
    return AnswerItemSupport(item, False, "item_not_supported_by_citations")


def _looks_cut_off(text: str) -> bool:
    normalized = " ".join(str(text or "").split())
    if not normalized:
        return False
    if normalized.endswith(("...", "…")):
        return True
    if re.search(r"\b(number|point|reason|thing)\s+(one|two|three|1|2|3)[,:\-]?\s", normalized, re.IGNORECASE):
        if not re.search(r"\b(number|point|reason|thing)\s+(two|three|four|2|3|4)[,:\-]?\s", normalized, re.IGNORECASE):
            return True
    return bool(re.search(r"\b[a-zA-Z]{2,}$", normalized)) and not normalized.endswith((".", "?", "!", '"', "'"))


def review_answer(
    *,
    question: str,
    answer: str,
    evidence: Sequence[dict[str, Any]],
    question_profile: QuestionProfile | None = None,
) -> AnswerReview:
    profile = question_profile or classify_question(question)
    shape = profile.expected_answer_shape
    evidence_text = _answer_text(evidence)
    answer_values = _percentages(answer) if shape.requires_percentage else _numbers(answer)
    citation_values = _percentages(evidence_text) if shape.requires_percentage else _numbers(evidence_text)
    needs_neighbor = _looks_cut_off(evidence_text)
    unsupported: list[AnswerItemSupport] = []
    supported: list[AnswerItemSupport] = []

    if shape.requires_percentage and not answer_values:
        return AnswerReview("weak", "missing_percentage_answer", profile, "missing", True, answer_values=answer_values, citation_values=citation_values, needs_neighbor_expansion=needs_neighbor)
    if shape.requires_percentage and answer_values and not any(value in citation_values for value in answer_values):
        return AnswerReview("weak", "percentage_not_supported_by_citations", profile, "partial", True, answer_values=answer_values, citation_values=citation_values, needs_neighbor_expansion=needs_neighbor)
    if shape.requires_numeric and not answer_values:
        return AnswerReview("weak", "missing_numeric_answer", profile, "missing", True, answer_values=answer_values, citation_values=citation_values, needs_neighbor_expansion=needs_neighbor)
    if shape.requires_date and not re.search(r"\b\d{4}\b", answer):
        return AnswerReview("weak", "missing_date_answer", profile, "missing", True, needs_neighbor_expansion=needs_neighbor)

    if shape.item_count:
        items = extract_answer_items(answer)
        if len(items) < shape.item_count:
            return AnswerReview("weak", "missing_requested_list_items", profile, "partial", True, supported_items=len(items), required_items=shape.item_count, needs_neighbor_expansion=needs_neighbor)
        for item in items[: shape.item_count]:
            item_support = _support_for_item(item, evidence_text)
            if item_support.supported:
                supported.append(item_support)
            else:
                unsupported.append(item_support)
        if unsupported:
            return AnswerReview(
                "weak",
                "list_items_not_supported_by_citations",
                profile,
                "partial",
                True,
                supported_items=len(supported),
                required_items=shape.item_count,
                unsupported_items=unsupported,
                supported_item_details=supported,
                needs_neighbor_expansion=needs_neighbor,
            )
        return AnswerReview(
            "verified",
            "answer_shape_and_citations_supported",
            profile,
            "complete",
            False,
            supported_items=len(supported),
            required_items=shape.item_count,
            supported_item_details=supported,
            needs_neighbor_expansion=needs_neighbor,
        )

    if needs_neighbor and profile.answer_risk != "low":
        return AnswerReview("weak", "citation_snippet_appears_cut_off", profile, "partial", True, answer_values=answer_values, citation_values=citation_values, needs_neighbor_expansion=True)
    return AnswerReview("verified", "answer_shape_and_citations_supported", profile, "complete", profile.answer_risk == "high", answer_values=answer_values, citation_values=citation_values, needs_neighbor_expansion=needs_neighbor)


def review_guidance(status: str) -> str:
    if status in {"verified", "recovered"}:
        return "Evidence appears sufficient for informational use. Human review is still recommended for high-impact decisions."
    return "Do not use this answer for decision-making without human review."


def review_note() -> str:
    return "Generated from retrieved enterprise sources. Review cited evidence before making business, legal, financial, medical, HR, security, or compliance decisions."
