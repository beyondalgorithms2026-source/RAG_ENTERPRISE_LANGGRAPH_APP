"""Offline typed evaluation. Never imported by the visitor answer path."""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any

GRADER_VERSION = "2.0.1"
TYPES = {"concept", "identifier", "numeric", "polarity", "classification", "citation"}


class AssertionError(ValueError):
    """Invalid evaluation contract (not a failed answer)."""


def normalize(text: str) -> str:
    # Keep decimal points, negation, modals and comparators. Articles are not
    # globally removed: they may be part of a document/control identifier.
    text = text.casefold().replace("’", "'").replace("–", "-").replace("×", "x")
    return " ".join(re.findall(r"\d+(?:\.\d+)?|[a-z]+|[%<>]", text))


def decimal(value: str) -> Decimal:
    try:
        parsed = Decimal(value.replace(",", ""))
        if not parsed.is_finite():
            raise AssertionError("numeric value must be finite")
        return parsed
    except InvalidOperation as exc:
        raise AssertionError("invalid decimal") from exc


def validate(assertions: Any, references: Any) -> None:
    if not isinstance(assertions, list) or not isinstance(references, list):
        raise AssertionError("assertions and reference_evidence must be lists")
    refs = {}
    for item in references:
        if (
            not isinstance(item, dict)
            or not all(
                isinstance(item.get(key), str) and item[key].strip()
                for key in ("id", "document", "section", "text")
            )
            or item["id"] in refs
        ):
            raise AssertionError("invalid or duplicate reference evidence")
        refs[item["id"]] = item
    ids = set()
    polarities = set()
    for item in assertions:
        if not isinstance(item, dict) or item.get("type") not in TYPES:
            raise AssertionError("unknown assertion type")
        aid = item.get("id")
        if not isinstance(aid, str) or not aid.strip() or aid in ids:
            raise AssertionError("invalid or duplicate assertion id")
        ids.add(aid)
        sources = item.get("source_refs")
        if (
            not isinstance(sources, list)
            or not sources
            or any(not isinstance(s, str) or s not in refs for s in sources)
        ):
            raise AssertionError("assertion requires valid source references")
        if not isinstance(item.get("required", True), bool):
            raise AssertionError("required must be boolean")
        aliases = item.get("any_of", [])
        anchors = item.get("answer_anchors", [])
        if (
            not isinstance(anchors, list)
            or any(
                not isinstance(group, list)
                or not group
                or any(not isinstance(term, str) or not term.strip() for term in group)
                for group in anchors
            )
            or (anchors and item["type"] != "concept")
        ):
            raise AssertionError("answer anchors require nonempty concept alias groups")
        if not isinstance(aliases, list) or any(
            not isinstance(a, str) or not a.strip() for a in aliases
        ):
            raise AssertionError("aliases must be nonempty strings")
        if item["type"] in {"concept", "identifier", "classification"} and (
            not isinstance(aliases, list)
            or not aliases
            or any(not isinstance(a, str) or not a.strip() for a in aliases)
        ):
            raise AssertionError("assertion requires nonempty aliases")
        if item["type"] == "numeric":
            if item.get("unit") not in {
                "EUR",
                "percent",
                "minutes",
                "hours",
                "days",
                "weeks",
                "months",
                "years",
                "kilograms",
                "metres",
                "celsius",
                "count",
            }:
                raise AssertionError("unknown numeric unit")
            if isinstance(item.get("value"), bool) or not isinstance(
                item.get("value"), (str, int, float)
            ):
                raise AssertionError("numeric assertion requires value")
            decimal(str(item["value"]))
            if item.get("comparator", "eq") not in {"eq", "gt", "gte", "lt", "lte"}:
                raise AssertionError("unknown comparator")
        if item["type"] == "polarity":
            if item.get("value") not in {"yes", "no"}:
                raise AssertionError("polarity must be yes or no")
            if item.get("required", True):
                polarities.add(item["value"])
        if item["type"] == "citation" and (
            not isinstance(item.get("section"), str) or not item["section"].strip()
        ):
            raise AssertionError("citation assertion requires section")
        contradictions = item.get("contradictions", [])
        if not isinstance(contradictions, list) or any(
            not isinstance(value, str) or not value.strip() for value in contradictions
        ):
            raise AssertionError("contradictions must be nonempty strings")
        if any(normalize(value) in {normalize(a) for a in aliases} for value in contradictions):
            raise AssertionError("required assertion contradicts its accepted aliases")
    if len(polarities) > 1:
        raise AssertionError("contradictory required polarity")


def _span(text: str, aliases: list[str]) -> str | None:
    normalized = normalize(text)
    return next(
        (
            alias
            for alias in aliases
            if re.search(rf"(?<!\w){re.escape(normalize(alias))}(?!\w)", normalized)
        ),
        None,
    )


def _identifier_span(text: str, aliases: list[str]) -> str | None:
    def canonical(value: str) -> str:
        return " ".join(re.findall(r"\d+(?:\.\d+)*|[a-z]+", value.casefold()))

    return next(
        (
            alias
            for alias in aliases
            if re.search(rf"(?<![\w.]){re.escape(canonical(alias))}(?![\w.])", canonical(text))
        ),
        None,
    )


def _numeric(text: str, item: dict[str, Any]) -> bool:
    # Written numbers are formatting, not a different fact. Convert only small
    # standalone cardinal words, never digits/decimals or identifier fragments.
    words = [
        "zero",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "eleven",
        "twelve",
        "thirteen",
        "fourteen",
        "fifteen",
        "sixteen",
        "seventeen",
        "eighteen",
        "nineteen",
        "twenty",
    ]
    text = re.sub(
        r"\b(" + "|".join(words) + r")\b",
        lambda m: str(words.index(m[0].lower())),
        text,
        flags=re.I,
    )
    unit = item["unit"]
    number = r"(?<![\w.])[-+]?\d+(?:,\d{3})*(?:\.\d+)?(?!\w|\.\d)"
    patterns = {
        "EUR": rf"(?:(?:€|EUR\b)\s*({number})|({number})\s*(?:EUR\b|euros?\b))",
        "percent": rf"({number})\s*(?:%|percent)",
        "celsius": rf"\+?({number})\s*°?C\b",
        "count": rf"({number})",
    }
    pattern = patterns.get(
        unit,
        rf"({number})\s*(?:(?:calendar|working|consecutive)\s+)?(?:{unit}|{unit.rstrip('s')})\b",
    )
    expected = decimal(str(item["value"]))
    for match in re.finditer(pattern, text, re.I):
        value = next(v for v in match.groups() if v is not None)
        if decimal(value) != expected:
            continue
        comparator = item.get("comparator", "eq")
        if comparator == "eq":
            return True
        prefix = text[max(0, match.start() - 45) : match.start()].casefold()
        markers = {
            "gt": r"(?:above|over|more than|exceed(?:s|ing)?|greater than|>)\s*$",
            "gte": r"(?:at least|not less than|>=)\s*$",
            "lt": r"(?:below|less than|under|<)\s*$",
            "lte": r"(?:up to|at most|no more than|<=)\s*$",
        }
        if re.search(markers[comparator], prefix):
            return True
    return False


def _polarity(answer: str) -> str | None:
    first = answer.strip().casefold()
    if re.match(r"(?:yes|correct|affirmative)\b", first):
        return "yes"
    if re.match(r"(?:no|incorrect|negative)\b", first):
        return "no"
    # Nonliteral prose needs adjudication; guessing from any 'not' is unsafe.
    return None


def evaluate(
    *,
    answer: str,
    evidence: list[dict],
    citations: list[dict],
    assertions: list[dict],
    references: list[dict],
) -> dict[str, Any]:
    validate(assertions, references)
    by_ref = {r["id"]: r for r in references}
    actual_evidence = " ".join(str(e.get("snippet") or e.get("text") or "") for e in evidence)
    rows = []
    for item in assertions:
        kind = item["type"]
        state = "missing"
        matched = None
        if kind in {"concept", "identifier", "classification"}:
            matcher = _identifier_span if kind == "identifier" else _span
            matched = matcher(answer, item["any_of"])
            state = "supported" if matched else "uncertain" if kind == "concept" else "missing"
            # Curated contradictory *claims*, not forbidden single words.
            if _span(answer, item.get("contradictions", [])):
                state = "contradicted"
            if any(_span(answer, group) is None for group in item.get("answer_anchors", [])):
                state = "missing"
        elif kind == "numeric":
            state = "supported" if _numeric(answer, item) else "missing"
        elif kind == "polarity":
            observed = _polarity(answer)
            state = (
                "uncertain"
                if observed is None
                else "supported"
                if observed == item["value"]
                else "contradicted"
            )
        elif kind == "citation":
            section = str(item["section"])
            state = (
                "supported"
                if any(
                    re.search(
                        rf"(?<![\d.]){re.escape(section)}(?![\d.])",
                        str(c.get("locator") or c.get("heading") or ""),
                    )
                    and any(
                        by_ref[s]["document"] == str(c.get("file_name") or "")
                        for s in item["source_refs"]
                    )
                    for c in citations
                )
                else "missing"
            )
        evidence_match = None
        if kind in {"concept", "identifier", "classification"}:
            evidence_match = bool(matcher(actual_evidence, item["any_of"]))
        elif kind == "numeric":
            evidence_match = _numeric(actual_evidence, item)
        rows.append(
            {
                "id": item["id"],
                "type": kind,
                "required": item.get("required", True),
                "state": state,
                "answer_span": matched,
                "evidence_matched": evidence_match,
                "method": "deterministic",
                "answer_anchor_missing": any(
                    _span(answer, group) is None for group in item.get("answer_anchors", [])
                ),
            }
        )
    return {
        "grader_version": GRADER_VERSION,
        "assertions": rows,
        "hard_failure": any(
            r["required"]
            and r["state"] in {"missing", "contradicted"}
            and (r["type"] != "concept" or r["answer_anchor_missing"])
            for r in rows
        ),
    }


def _literal_span(text: str, quote: Any) -> str | None:
    """Resolve copied evidence with whitespace variation only, never paraphrases."""
    if not isinstance(quote, str) or not quote.strip():
        return None
    words = re.split(r"\s+", quote.strip())
    match = re.search(r"\s+".join(re.escape(word) for word in words), text)
    return match.group() if match else None


def factual_quotes(references: list[dict]) -> list[str]:
    """Literal factual units, excluding titles, table headers and separators."""
    quotes = set()
    for reference in references:
        lines = [line.strip() for line in reference["text"].splitlines() if line.strip()]
        for index, line in enumerate(lines):
            separator = bool(re.fullmatch(r"[|:\-\s]+", line))
            header = index + 1 < len(lines) and bool(re.fullmatch(r"[|:\-\s]+", lines[index + 1]))
            if separator or header or line.startswith("#"):
                continue
            quotes.add(line)
            if not line.startswith("|"):
                quotes.update(
                    m.group().strip() for m in re.finditer(r"\S.*?(?:[.!?;](?=\s|$)|$)", line)
                )
    return sorted(quotes)


_BLOCK_BREAK = "\n¶\n"


def _factual_text(references: list[dict]) -> str:
    """Factual lines in document order, so quotes may span a hard line wrap.

    Titles, table headers and separators break the text into blocks, and each table
    row is its own block, so no quote can join excluded or unrelated lines.
    """
    blocks: list[str] = []
    for reference in references:
        lines = [line.strip() for line in reference["text"].splitlines() if line.strip()]
        current: list[str] = []
        for index, line in enumerate(lines):
            separator = bool(re.fullmatch(r"[|:\-\s]+", line))
            header = index + 1 < len(lines) and bool(re.fullmatch(r"[|:\-\s]+", lines[index + 1]))
            if separator or header or line.startswith("#") or line.startswith("|"):
                if current:
                    blocks.append("\n".join(current))
                    current = []
                if line.startswith("|") and not (separator or header):
                    blocks.append(line)
                continue
            current.append(line)
        if current:
            blocks.append("\n".join(current))
    return _BLOCK_BREAK.join(blocks)


def apply_judgement(
    result: dict,
    judgement: Any,
    *,
    answer: str,
    references: list[dict],
    assertions: list[dict] | None = None,
) -> dict:
    """Validate grounded judge spans; never permit overriding hard checks."""
    if not isinstance(judgement, dict) or not isinstance(judgement.get("assertions"), list):
        raise AssertionError("invalid judge output")
    unresolved = {
        r["id"]: r
        for r in result["assertions"]
        if r["type"] == "concept" or (r["type"] == "polarity" and r["state"] == "uncertain")
    }
    seen = set()
    contracts = {a["id"]: a for a in assertions or []}
    updates = []
    for row in judgement["assertions"]:
        if not isinstance(row, dict) or row.get("id") not in unresolved or row["id"] in seen:
            raise AssertionError("judge returned unknown or duplicate assertion")
        seen.add(row["id"])
        if row.get("state") not in {"supported", "missing", "contradicted", "uncertain"}:
            raise AssertionError("unknown judge state")
        if not isinstance(row.get("explanation"), str) or not row["explanation"].strip():
            raise AssertionError("judge explanation required")
        answer_span = _literal_span(answer, row.get("answer_span"))
        source_ids = contracts.get(row["id"], {}).get("source_refs")
        scoped = [r for r in references if source_ids is None or r["id"] in source_ids]
        evidence_span = _literal_span(_factual_text(scoped), row.get("evidence_span"))
        if row["state"] in {"supported", "contradicted"} and (
            answer_span is None or evidence_span is None
        ):
            raise AssertionError("judge support spans must occur in answer and reference")
        original = unresolved[row["id"]]
        if original["state"] != "contradicted" and not original.get("answer_anchor_missing"):
            updates.append(
                (
                    original,
                    {
                        "state": row["state"],
                        "method": "semantic_judge",
                        "answer_span": answer_span,
                        "evidence_span": evidence_span,
                        "explanation": row["explanation"],
                    },
                )
            )
    if seen != set(unresolved):
        raise AssertionError("judge omitted concept assertions")
    # Invalid later rows must not leave earlier assertions partially overwritten.
    for original, update in updates:
        original.update(update)
    return result


def judge_payload(
    *,
    question: str,
    answer: str,
    assertions: list[dict],
    references: list[dict],
    citations: list[dict],
) -> str:
    return json.dumps(
        {
            "question": question,
            "answer": answer,
            "assertions": assertions,
            "reference_evidence": references,
            "citations": citations,
        },
        ensure_ascii=False,
    )
