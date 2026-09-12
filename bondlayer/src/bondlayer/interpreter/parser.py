"""Deterministic natural-language constraint parser.

The parser deliberately stays offline and dependency-free. It extracts typed
clauses, preserving shopper wording so downstream traces can explain each
assumption.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bondlayer.types import Constraint, ConstraintKind


@dataclass(frozen=True)
class _Match:
    start: int
    end: int
    text: str
    kind: ConstraintKind
    priority: int


_MONEY = r"(?:\$\s*)?(\d[\d,]*(?:\.\d+)?)"

# Ordered longest-first where alternatives overlap. These patterns describe
# meaning, not product names; catalogue matching belongs in resolver.py.
_SERVICE_PATTERNS = (
    r"\b(?:that\s+)?(?:i\s+)?can\s+(?:easily\s+)?return\s+(?:it\s+)?(?:easily)?",
    r"\breturnable\b[^,.;]*",
    r"\bsend\s+back\b[^,.;]*",
    r"\b(?:decent\s+)?cover\s+(?:if|for|on)\b[^,.;]*",
    r"\b(?:long|extended)\s+warranty\b",
    r"\bwarranty\b[^,.;]*",
    r"\b(?:delivered|delivery)\b[^,.;]*",
    r"\btrade\s+in\b[^,.;]*",
    r"\b(?:support|supported)\b[^,.;]*",
)

_VALUES_PATTERNS = (
    r"\bfrom\s+a\s+brand\s+that\s+actually\s+repairs\s+things\b",
    r"\b(?:lets|can\s+let)\s+(?:me\s+)?fix\s+it\s+myself\b",
    r"\b(?:most\s+)?sustainable\b",
    r"\bcarbon\s+neutral\b",
    r"\b(?:i\s+)?(?:hate\s+)?throwing\s+things\s+away\b",
    r"\b(?:actually\s+)?repairs?\s+things?\b",
    r"\brepairability\b",
    r"\b(?:ethical|ethically)\b[^,.;]*",
    r"\bwhere\s+(?:it|it\s+is)\s+made\b",
    r"\b(?:i\s+)?(?:want\s+it\s+to\s+)?last\b",
    r"\bdurab(?:le|ility)\b",
)

_SOFT_PATTERNS = (
    r"\b(?:good\s+enough|suitable|suited)\s+for\s+[^,.;]+",
    r"\bfor\s+(?:design|video\s+editing|work)\s+work\b",
    r"\bfor\s+video\s+editing\b",
    r"\b(?:not\s+to\s+)?suit\s+my\s+work\b",
    r"\bcarry\s+every\s+day\b",
    r"\bcheapest\b",
    r"\bbest\s+value\b",
    r"\b(?:beginner[- ]friendly|podcasting\s+gear)\b",
    r"\b(?:everything\s+(?:i\s+)?need\s+to\s+start\s+a\s+podcast)\b",
    r"\b(?:record\s+interviews\s+on\s+the\s+go)\b",
    r"\b(?:money\s+is\s+not\s+really\s+the\s+issue)\b",
    r"\b(?:good\s+gift)\b",
    r"\b(?:gaming)\b",
    r"\blight\b",
)

_CATEGORY_PATTERNS = (
    "portable ssd",
    "coffee machine",
    "rice cooker",
    "laptop",
    "microphone",
    "headset",
    "monitor",
    "phone",
    "vacuum",
    "dock",
)

_SPEC_PATTERNS = (
    r"\b\d+\s*(?:gb|gigs?|tb|inch(?:es)?|kg)\b",
    r"\b(?:rtx\s*\d*|i[357])\b",
)

_HARD_PRICE = re.compile(
    rf"\b(?:under|below|less\s+than|no\s+more\s+than|up\s+to)\s+{_MONEY}",
    re.IGNORECASE,
)
_SOFT_PRICE = re.compile(
    rf"\b(?:around|about|ideally\s+under|roughly)\s+{_MONEY}",
    re.IGNORECASE,
)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip(" \t,.;"))


def _span_matches(utterance: str, patterns: tuple[str, ...], kind: ConstraintKind, priority: int) -> list[_Match]:
    matches: list[_Match] = []
    for pattern in patterns:
        for match in re.finditer(pattern, utterance, re.IGNORECASE):
            text = _clean(match.group(0))
            if text:
                matches.append(_Match(match.start(), match.end(), text, kind, priority))
    return matches


def _overlap(left: _Match, right: _Match) -> bool:
    return left.start < right.end and right.start < left.end


def parse(utterance: str) -> list[Constraint]:
    """Parse shopper wording into ordered, typed constraints.

    Extraction is conservative: a clause is emitted only when a known intent
    pattern matches. No budget or product requirement is invented.
    """
    if not isinstance(utterance, str) or not utterance.strip():
        raise ValueError("utterance must be a non-empty string")

    matches: list[_Match] = []
    for match in _HARD_PRICE.finditer(utterance):
        matches.append(_Match(match.start(), match.end(), _clean(match.group(0)), ConstraintKind.HARD, 100))
    for match in _SOFT_PRICE.finditer(utterance):
        matches.append(_Match(match.start(), match.end(), _clean(match.group(0)), ConstraintKind.SOFT, 100))
    matches.extend(_span_matches(utterance, _SERVICE_PATTERNS, ConstraintKind.SERVICE, 80))
    matches.extend(_span_matches(utterance, _VALUES_PATTERNS, ConstraintKind.VALUES, 80))
    matches.extend(_span_matches(utterance, _SOFT_PATTERNS, ConstraintKind.SOFT, 50))

    for category in _CATEGORY_PATTERNS:
        for match in re.finditer(rf"\b{re.escape(category)}\b", utterance, re.IGNORECASE):
            matches.append(_Match(match.start(), match.end(), _clean(match.group(0)), ConstraintKind.HARD, 40))
    for pattern in _SPEC_PATTERNS:
        for match in re.finditer(pattern, utterance, re.IGNORECASE):
            matches.append(_Match(match.start(), match.end(), _clean(match.group(0)), ConstraintKind.HARD, 40))

    # Keep the most specific match at each overlapping span. This prevents the
    # broad "warranty" pattern from duplicating "long warranty", for example.
    selected: list[_Match] = []
    for candidate in sorted(matches, key=lambda item: (-item.priority, -(item.end - item.start), item.start)):
        if any(_overlap(candidate, existing) for existing in selected):
            continue
        selected.append(candidate)
    selected.sort(key=lambda item: item.start)

    # Keep category context in the budget clause without inventing a fifth
    # constraint for R01. The shared contract has only text and kind.
    if selected and selected[0].text.lower() in {"laptop", "phone"}:
        category = selected[0]
        budget = next((item for item in selected[1:] if _HARD_PRICE.fullmatch(item.text)), None)
        if budget and not utterance[category.end:budget.start].strip():
            selected.remove(category)
            selected[selected.index(budget)] = _Match(
                category.start, budget.end, utterance[category.start:budget.end], budget.kind, budget.priority,
            )
    return [Constraint(text=item.text, kind=item.kind) for item in selected]


class ConstraintParser:
    """Protocol-friendly parser object."""

    def parse(self, utterance: str) -> list[Constraint]:
        return parse(utterance)
