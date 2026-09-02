from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence


@dataclass(frozen=True)
class OrchestrationRule:
    id: str
    question_terms: list[str] = field(default_factory=list)
    required_any: list[list[str]] = field(default_factory=list)
    aliases: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceVerdict:
    status: str
    score: float
    reason: str
    anchor_hits: list[str] = field(default_factory=list)
    missing_terms: list[str] = field(default_factory=list)
    needs_neighbor_expansion: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "score": round(self.score, 4),
            "reason": self.reason,
            "anchor_hits": self.anchor_hits,
            "missing_terms": self.missing_terms,
            "needs_neighbor_expansion": self.needs_neighbor_expansion,
        }


# No rules ship in source.
#
# This list previously held eight rules whose `answer_any` fields contained the
# literal answers to eight questions in the project's own evaluation set - and
# `load_rules()` seeded them even when a custom rules path was given, so there was
# no way to opt out. `expected_terms_from_answer()` then returned those terms
# directly, which meant the function deciding whether an answer was supported had
# been told the answers in advance.
#
# Any eval number produced that way is uninterpretable. Rules are configuration
# now: supply them with --rules, and see config/orchestration-rules.example.json
# for the shape.
DEFAULT_RULES: list[OrchestrationRule] = []


def _normalize_text(value: Any) -> str:
    text = str(value or "").lower()
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip()


def _contains_any(text: str, values: Sequence[str]) -> bool:
    normalized = _normalize_text(text)
    return any(_normalize_text(value) in normalized for value in values if str(value).strip())


def _numeric_aliases(value: str) -> list[str]:
    normalized = _normalize_text(value)
    aliases = [value]
    percent_match = re.search(r"\b(\d+(?:\.\d+)?)\s*%", normalized)
    if percent_match:
        aliases.append(str(float(percent_match.group(1)) / 100).rstrip("0").rstrip("."))
    decimal_match = re.search(r"\b0\.(\d+)\b", normalized)
    if decimal_match:
        percent = float("0." + decimal_match.group(1)) * 100
        aliases.append(f"{percent:g}%")
    return aliases


def _expand_aliases(values: Sequence[str], rule: OrchestrationRule | None = None) -> list[str]:
    expanded: list[str] = []
    for value in values:
        expanded.extend(_numeric_aliases(value))
        if rule:
            expanded.extend(rule.aliases.get(value, []))
    seen: set[str] = set()
    output: list[str] = []
    for value in expanded:
        normalized = _normalize_text(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(value)
    return output


def load_rules(path: str | Path | None = None) -> list[OrchestrationRule]:
    """Load orchestration rules from a file. With no file, there are no rules.

    Nothing is seeded from source. Passing a path yields exactly the rules in
    that file - previously a custom path was appended to the built-in rules
    rather than replacing them, so the built-ins could not be escaped.
    """
    if path is None:
        return []
    rule_path = Path(path)
    if not rule_path.exists():
        return []
    payload = json.loads(rule_path.read_text(encoding="utf-8"))
    rules: list[OrchestrationRule] = []
    for item in payload.get("rules", []):
        if not isinstance(item, dict):
            continue
        rules.append(
            OrchestrationRule(
                id=str(item.get("id") or "custom_rule"),
                question_terms=[str(value) for value in item.get("question_terms", [])],
                required_any=[[str(value) for value in group] for group in item.get("required_any", []) if isinstance(group, list)],
                    aliases={str(key): [str(value) for value in values] for key, values in (item.get("aliases") or {}).items() if isinstance(values, list)},
            )
        )
    return rules


def matching_rule(question: str, rules: Sequence[OrchestrationRule]) -> OrchestrationRule | None:
    normalized = _normalize_text(question)
    matches: list[tuple[int, OrchestrationRule]] = []
    for rule in rules:
        hits = sum(1 for term in rule.question_terms if _normalize_text(term) in normalized)
        if hits and hits >= max(1, min(len(rule.question_terms), 2)):
            matches.append((hits, rule))
    if not matches:
        return None
    return sorted(matches, key=lambda item: item[0], reverse=True)[0][1]


def expected_terms_from_answer(expected_answer: str, rule: OrchestrationRule | None = None) -> list[str]:
    """Derive the terms an answer must contain, from the expected answer itself.

    A matching rule may supply aliases (so "5%" also matches "0.05"), but it can
    no longer replace the expected answer with a stored one.
    """
    terms: list[str] = []
    for percent in re.findall(r"\b\d+(?:\.\d+)?\s*%", expected_answer):
        terms.extend(_numeric_aliases(percent))
    for decimal in re.findall(r"\b0\.\d+\b", expected_answer):
        terms.extend(_numeric_aliases(decimal))
    for phrase in re.findall(r"\b[A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+){0,4}\b", expected_answer):
        if len(phrase) >= 3:
            terms.append(phrase)
    for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9._%-]*", expected_answer):
        if len(token) >= 4 and token.lower() not in {"that", "with", "from", "this", "were", "would"}:
            terms.append(token)
    return _expand_aliases(terms, rule)


def _snippet_text(evidence: Sequence[dict[str, Any]]) -> str:
    return " ".join(str(item.get("snippet") or item.get("excerpt") or "") for item in evidence)


def _is_cut_off(text: str) -> bool:
    stripped = text.strip()
    return stripped.endswith("...") or stripped.endswith("…") or bool(re.search(r"\b[a-zA-Z]{2,}$", stripped)) and not stripped.endswith((".", "?", "!", '"', "'"))


def validate_evidence(
    *,
    question: str,
    evidence: Sequence[dict[str, Any]],
    anchors: Sequence[str],
    rules: Sequence[OrchestrationRule] = (),
    expected_answer: str | None = None,
) -> EvidenceVerdict:
    text = _snippet_text(evidence)
    normalized = _normalize_text(text)
    if not normalized:
        return EvidenceVerdict("irrelevant", 0.0, "missing_evidence_text")

    rule = matching_rule(question, rules)
    expected_terms = expected_terms_from_answer(expected_answer or "", rule)
    anchor_hits = [anchor for anchor in anchors if len(anchor) >= 4 and _normalize_text(anchor) in normalized]
    meaningful_anchor_count = len([anchor for anchor in anchors if len(anchor) >= 4])
    anchor_score = min(1.0, len(anchor_hits) / max(1, min(meaningful_anchor_count, 4)))

    missing_groups: list[str] = []
    required_score = 0.0
    if rule and rule.required_any:
        passed_groups = 0
        for group in rule.required_any:
            expanded_group = _expand_aliases(group, rule)
            if _contains_any(normalized, expanded_group):
                passed_groups += 1
            else:
                missing_groups.append(" or ".join(group))
        required_score = passed_groups / len(rule.required_any)
    elif expected_terms:
        required_score = 1.0 if _contains_any(normalized, expected_terms) else 0.0
        if required_score == 0.0:
            missing_groups.append("expected answer terms")

    answer_type_score = 0.0
    lowered_question = _normalize_text(question)
    if "percentage" in lowered_question or "percent" in lowered_question or "%" in lowered_question:
        answer_type_score = 1.0 if re.search(r"\b\d+(?:\.\d+)?\s*%|\b0\.\d+\b", normalized) else 0.0
    elif "when" in lowered_question:
        answer_type_score = 1.0 if re.search(r"\b\d{4}\b", normalized) else 0.0
    elif "where" in lowered_question:
        # A location answer should contain a proper noun. Naming specific places
        # here would be the same mistake as the removed answer keys: it would
        # score one corpus's answers rather than the shape of a location answer.
        answer_type_score = 1.0 if re.search(r"\b[A-Z][a-z]{2,}", text) else 0.0
    else:
        answer_type_score = 1.0 if anchor_score > 0 else 0.0

    score = min(1.0, (anchor_score * 0.35) + (required_score * 0.45) + (answer_type_score * 0.20))
    needs_neighbor = _is_cut_off(text) and score >= 0.35

    if rule and missing_groups:
        status = "partial" if score >= 0.45 else "irrelevant"
        reason = "missing_required_terms"
    elif expected_terms and missing_groups:
        status = "partial" if score >= 0.45 else "irrelevant"
        reason = "missing_expected_answer_terms"
    elif score >= 0.65 and answer_type_score > 0:
        status = "supports"
        reason = "validated_evidence"
    elif score >= 0.40:
        status = "partial"
        reason = "relevant_but_incomplete"
    else:
        status = "irrelevant"
        reason = "evidence_found_but_irrelevant"

    return EvidenceVerdict(
        status=status,
        score=score,
        reason=reason,
        anchor_hits=anchor_hits,
        missing_terms=missing_groups,
        needs_neighbor_expansion=needs_neighbor,
    )


def evaluate_expected_answer(*, answer: str, evidence: Sequence[dict[str, Any]], expected_answer: str, question: str, rules: Sequence[OrchestrationRule]) -> dict[str, Any]:
    rule = matching_rule(question, rules)
    combined = " ".join([answer, _snippet_text(evidence)])
    terms = expected_terms_from_answer(expected_answer, rule)
    passed = _contains_any(combined, terms) if terms else False
    return {
        "status": "pass" if passed else "fail",
        "matched_terms": [term for term in terms if _contains_any(combined, [term])],
        "expected_terms": terms[:20],
        "rule_id": rule.id if rule else None,
    }
