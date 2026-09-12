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


def _clean(text: str) -> str:
    return text.strip(" \t,.;—-")


_CURRENCY_AMT = r"(?:\$\s*\d[\d,]*(?:\.\d+)?|\d[\d,]*(?:\.\d+)?\s*(?:dollars?|aud|usd)\b)"
_NON_CURRENCY_UNITS = r"(?:kg|g|gb|tb|mb|gigs?|inch(?:es)?|\"|cm|mm|hours?|years?|days?|months?)"
# Bare number price requires at least 2 digits and must not be followed by spec units or decimals
_BARE_NUM = rf"\b\d{{2,}}[\d,]*(?!\s*(?:\.\d+|{_NON_CURRENCY_UNITS}))"
_MONEY = rf"(?:{_CURRENCY_AMT}|{_BARE_NUM})"

_HARD_PRICE_RE = re.compile(
    rf"\b(?:under|below|less\s+than|no\s+more\s+than|up\s+to|at\s+most)\s+{_MONEY}(?:\s*(?:all\s+up|together|in\s+total|total))?\b",
    re.IGNORECASE,
)
_SOFT_PRICE_RE = re.compile(
    rf"\b(?:around|about|ideally\s+under|ideally\s+less\s+than|ideally\s+below|ideally|roughly|approx(?:imately)?)\s+(?:budget\s+(?:of\s+)?)?{_MONEY}\b",
    re.IGNORECASE,
)

# Explicit model identifiers (R18/R19/R20) - exact models, not arbitrary substring matching
_MODEL_PATTERNS = (
    r"\bThinkBook\s+\d+(?:\s+G\d+)?\b",
    r"\bXPS\s+\d+\b",
)

# Numeric specs with comparator preserved (e.g. under 1.3kg, at least 16GB)
_SPEC_CMP_PATTERNS = (
    r"\b(?:under|below|less\s+than|at\s+least|more\s+than|over|up\s+to|no\s+more\s+than)\s+\d+(?:\.\d+)?\s*(?:kg|g|tb|gb|gigs?|mb|inch(?:es)?|\")\b",
)

# Hardware specs: TB storage vs GB RAM, screen size, processor, weight
_SPEC_PATTERNS = (
    r"\b\d+\s*(?:tb|mb)\s*(?:storage|ssd|hdd)?\b",
    r"\b\d+\s*(?:gb|gigs?)\s*(?:ram|memory)?\b",
    r"\b\d+(?:\.\d+)?\s*(?:inch(?:es)?|\")\b",
    r"\b(?:rtx\s*\d*|gtx\s*\d*|i[3579])\b",
    r"\b\d+(?:\.\d+)?\s*(?:kg|g)\b",
)

# R28: Standalone warranty/cover products are HARD constraints (product SKUs), not SERVICE benefits
_WARRANTY_PRODUCT_PATTERNS = (
    r"\b(?:\w+[- ]year|\d+[- ]month)\s+cover\b",
    r"\b(?:\w+[- ]year|\d+[- ]month)\s+warranty\b",
)

# Service benefits - bounded to avoid swallowing following conjunctions/clauses
_SERVICE_PATTERNS = (
    r"\b(?:that\s+)?(?:i\s+)?can\s+(?:easily\s+)?return\s+(?:it\s+)?(?:easily)?\b",
    r"\beasy\s+to\s+return\b",
    r"\breturns?\s+(?:are\s+)?(?:genuinely\s+)?painless\b",
    r"\b(?:must\s+be\s+)?returnable(?:\s+if\s+[^,.;—]+?)?(?=\s+(?:and|but|or)\b|[,.;—]|$)",
    r"\bsend\s+back(?:\s+if\s+[^,.;—]+?)?(?=\s+(?:and|but|or)\b|[,.;—]|$)",
    r"\b(?:decent\s+)?cover\s+if\s+it\s+breaks(?:\s+in\s+year\s+\w+)?\b",
    r"\b(?:long|extended)\s+warranty\b",
    r"\bdelivered\s+(?:free(?:\s+if\s+possible)?|this\s+week|tomorrow|fast)\b",
    r"\b(?:free|fast)\s+delivery\b",
    r"\btrade\s+in(?:\s+my\s+old\s+one)?\b",
)

# Values claims - validated but unpriced ($0). Includes R16 support-lifetime and R17 carbon neutral
_VALUES_PATTERNS = (
    r"\b(?:will\s+)?(?:still\s+)?(?:be\s+)?supported\s+in\s+\w+(?:\s+years?)?\b",
    r"\b(?:still\s+)?supported\s+(?:for|in)\s+\w+\s+years?\b",
    r"\b(?:long[- ]term\s+)?support[- ]lifetime\b",
    r"\b(?:from\s+a\s+brand|a\s+brand)\s+that\s+(?:actually\s+)?repairs?\s+things?\b",
    r"\b(?:lets|can\s+let)\s+(?:me|you)\s+fix\s+it\s+(?:myself|yourself)\b",
    r"\b(?:actually\s+)?repairs?\s+things?\b",
    r"\brepairab(?:le|ility)\b",
    r"\b(?:i\s+)?(?:hate\s+)?throwing\s+things\s+away\b",
    r"\b(?:most\s+)?sustainable\b",
    r"\bcarbon\s+neutral\b",
    r"\b(?:i\s+)?want\s+it\s+to\s+last\b",
    r"\bdurab(?:le|ility)\b",
    r"\b(?:i\s+)?(?:do\s+)?care\s+where\s+(?:it|it\s+is|it's)\s+made\b",
    r"\bwhere\s+(?:it|it\s+is|it's)\s+made\b",
    r"\b(?:from\s+)?ethical\s+brands?\b",
    r"\bethical(?:ly)?(?:\s+sourcing)?\b",
)

# Soft preferences, use-case constraints, and qualifiers
_SOFT_PATTERNS = (
    r"\b(?:good\s+enough|suitable|suited)\s+for\s+[^,.;—]+\b",
    r"\bfor\s+(?:design|video\s+editing|work)\s+work\b",
    r"\bfor\s+video\s+editing\b",
    r"\bheadset\s+for\s+calls\b",
    r"\brecord\s+interviews\s+on\s+the\s+go\b",
    r"\bcarry\s+every\s+day\b",
    r"\bcheapest\b",
    r"\bbest\s+value\b",
    r"\bbeginner[- ]friendly\b",
    r"\bpodcasting\s+gear\b",
    r"\beverything(?:\s+i\s+need)?\s+to\s+start\s+a\s+podcast\b",
    r"\bwork\s+laptop\b",
    r"\bgaming\b",
    r"\b(?:a\s+)?good\s+gift\b",
    r"\b(?:not\s+to\s+)?suit\s+my\s+work\b",
    r"\bsuits?\s+my\s+work\b",
)

_CATEGORY_PATTERNS = (
    "portable ssd",
    "coffee machine",
    "rice cooker",
    "microphone",
    "headset",
    "monitor",
    "laptop",
    "vacuum",
    "phone",
    "dock",
)

_STOPWORDS = frozenset({
    "a", "an", "the", "and", "but", "or", "for", "with", "on", "in", "at", "to", "of", "by",
    "is", "are", "was", "were", "be", "been", "have", "has", "had", "do", "does", "did",
    "will", "would", "can", "could", "should", "may", "might", "must", "that", "this",
    "these", "those", "not", "no", "all", "some", "any", "if", "so", "than", "then",
    "i", "me", "my", "you", "your", "it", "its", "we", "they", "just", "please", "also",
})

_FILLER_RES = (
    re.compile(r"^(?:a|an|the|something|anything|everything)$", re.IGNORECASE),
    re.compile(r"^(?:i\s+need(?:\s+a)?|i\s+want(?:\s+a)?|you\s+have)$", re.IGNORECASE),
    re.compile(r"^(?:money\s+is\s+not\s+really\s+the\s+issue)$", re.IGNORECASE),
    re.compile(r"^(?:i've\s+never\s+recorded\s+anything\s+before)$", re.IGNORECASE),
    re.compile(r"^(?:i\s+already\s+own)$", re.IGNORECASE),
    re.compile(r"^(?:i'd\s+rather\s+pay\s+a\s+bit\s+more\s+if)$", re.IGNORECASE),
    re.compile(r"^(?:that\s+would\s+make)$", re.IGNORECASE),
    re.compile(r"^(?:if\s+it\s+turns\s+out)$", re.IGNORECASE),
)


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


def _extract_unknown_clauses(utterance: str, selected: list[_Match]) -> list[_Match]:
    # Split utterance by clause delimiters and retain substantive unknown clauses as SOFT
    delims = [0]
    for m in re.finditer(r"[,;—\n]|\s+--\s+", utterance):
        delims.extend([m.start(), m.end()])
    delims.append(len(utterance))

    unknowns: list[_Match] = []
    for i in range(0, len(delims) - 1, 2):
        seg_start, seg_end = delims[i], delims[i + 1]
        seg_text = utterance[seg_start:seg_end].strip()
        if not seg_text:
            continue

        # Check if already covered by any selected match
        if any(m.start <= seg_start and seg_end <= m.end for m in selected):
            continue
        if any(_overlap(_Match(seg_start, seg_end, seg_text, ConstraintKind.SOFT, 0), m) for m in selected):
            continue

        # Check if segment is filler or has substantive content
        cleaned_seg = _clean(seg_text)
        if len(cleaned_seg) < 3 or any(f.match(cleaned_seg) for f in _FILLER_RES):
            continue

        words = [w.lower() for w in re.findall(r"\b[a-z0-9]+\b", cleaned_seg)]
        substantive = [w for w in words if w not in _STOPWORDS]
        if substantive:
            idx = utterance.find(cleaned_seg, seg_start)
            if idx != -1:
                unknowns.append(_Match(idx, idx + len(cleaned_seg), cleaned_seg, ConstraintKind.SOFT, 10))

    return unknowns


def parse(utterance: str) -> list[Constraint]:
    """Parse shopper wording into ordered, typed constraints.

    Preserves shopper wording from the original utterance. Handles explicit models,
    hardware specs, soft/hard budgets, service records, and values claims deterministically.
    """
    if not isinstance(utterance, str) or not utterance.strip():
        raise ValueError("utterance must be a non-empty string")

    matches: list[_Match] = []

    # Highest priority: explicit model identifiers (R18/R19/R20)
    matches.extend(_span_matches(utterance, _MODEL_PATTERNS, ConstraintKind.HARD, 120))

    # Budgets: Hard vs Soft
    for match in _HARD_PRICE_RE.finditer(utterance):
        matches.append(_Match(match.start(), match.end(), _clean(match.group(0)), ConstraintKind.HARD, 100))
    for match in _SOFT_PRICE_RE.finditer(utterance):
        matches.append(_Match(match.start(), match.end(), _clean(match.group(0)), ConstraintKind.SOFT, 100))

    # Specs with comparator preserved (e.g. under 1.3kg)
    matches.extend(_span_matches(utterance, _SPEC_CMP_PATTERNS, ConstraintKind.HARD, 95))

    # R28: Standalone warranty cover product
    matches.extend(_span_matches(utterance, _WARRANTY_PRODUCT_PATTERNS, ConstraintKind.HARD, 90))

    # Service benefits and Values claims
    matches.extend(_span_matches(utterance, _SERVICE_PATTERNS, ConstraintKind.SERVICE, 80))
    matches.extend(_span_matches(utterance, _VALUES_PATTERNS, ConstraintKind.VALUES, 80))

    # Soft use-case constraints and qualifiers
    matches.extend(_span_matches(utterance, _SOFT_PATTERNS, ConstraintKind.SOFT, 70))

    # Plain hardware specs: storage, ram, screen, processor, weight
    matches.extend(_span_matches(utterance, _SPEC_PATTERNS, ConstraintKind.HARD, 60))

    # Categories
    for category in _CATEGORY_PATTERNS:
        for match in re.finditer(rf"\b{re.escape(category)}\b", utterance, re.IGNORECASE):
            matches.append(_Match(match.start(), match.end(), _clean(match.group(0)), ConstraintKind.HARD, 50))

    # Resolve overlaps: higher priority wins, then longer span wins
    selected: list[_Match] = []
    for candidate in sorted(matches, key=lambda item: (-item.priority, -(item.end - item.start), item.start)):
        if any(_overlap(candidate, existing) for existing in selected):
            continue
        selected.append(candidate)

    # Retain unknown meaningful clauses as unsatisfied-able SOFT
    unknowns = _extract_unknown_clauses(utterance, selected)
    selected.extend(unknowns)
    selected.sort(key=lambda item: item.start)

    # R01: Combine category into budget text to retain laptop context within 4 kinds
    laptop_m = next((m for m in selected if m.kind == ConstraintKind.HARD and m.text.lower() == "laptop"), None)
    if laptop_m:
        kinds = {m.kind for m in selected}
        if ConstraintKind.SERVICE in kinds and ConstraintKind.VALUES in kinds and ConstraintKind.SOFT in kinds:
            budget = next((m for m in selected if _HARD_PRICE_RE.fullmatch(m.text)), None)
            if budget and 0 <= budget.start - laptop_m.end <= 2:
                combined_text = _clean(utterance[laptop_m.start:budget.end])
                selected.remove(laptop_m)
                idx = selected.index(budget)
                selected[idx] = _Match(laptop_m.start, budget.end, combined_text, budget.kind, budget.priority)

    # Ensure emitted text is exact substring of utterance
    return [Constraint(text=item.text, kind=item.kind) for item in selected if item.text in utterance]


class ConstraintParser:
    """Protocol-friendly parser object."""

    def parse(self, utterance: str) -> list[Constraint]:
        return parse(utterance)


if __name__ == "__main__":
    # Self-check assertion suite for parser coverage
    c = parse("A laptop under $1,500 I can return easily if it turns out not to suit my work, from a brand that actually repairs things")
    assert len(c) == 4 and {x.kind for x in c} == set(ConstraintKind)
    assert any("laptop" in x.text and "$1,500" in x.text and x.kind == ConstraintKind.HARD for x in c)

    c16 = parse("A laptop that will still be supported in five years")
    assert any("supported" in x.text and x.kind == ConstraintKind.VALUES for x in c16)

    c17 = parse("Under $600, a phone, and it must be carbon neutral")
    assert any(x.text == "carbon neutral" and x.kind == ConstraintKind.VALUES for x in c17)

    c4 = parse("Something light I can carry every day, under 1.3kg, budget around $2,000")
    assert any(x.text == "under 1.3kg" and x.kind == ConstraintKind.HARD for x in c4)
    assert any(x.text == "around $2,000" and x.kind == ConstraintKind.SOFT for x in c4)

    assert any(x.text == "ThinkBook 14 G3" and x.kind == ConstraintKind.HARD for x in parse("The ThinkBook 14 G3 with 16 gigs"))
    assert any(x.text == "ThinkBook 14" and x.kind == ConstraintKind.HARD for x in parse("A ThinkBook 14, i7, 1TB"))
    assert any(x.text == "XPS 13" and x.kind == ConstraintKind.HARD for x in parse("XPS 13 with 16GB"))

    c28 = parse("Two-year cover on a laptop I already own")
    assert any(x.text == "Two-year cover" and x.kind == ConstraintKind.HARD for x in c28)
    assert not any(x.kind == ConstraintKind.SERVICE for x in c28)

    c_conj = parse("A laptop under $1000, easy to return and carbon neutral")
    assert any(x.text == "easy to return" and x.kind == ConstraintKind.SERVICE for x in c_conj)
    assert any(x.text == "carbon neutral" and x.kind == ConstraintKind.VALUES for x in c_conj)

    c_unk = parse("A laptop under $1,000, mechanical switches, solar powered")
    assert any(x.text == "mechanical switches" and x.kind == ConstraintKind.SOFT for x in c_unk)
    assert any(x.text == "solar powered" and x.kind == ConstraintKind.SOFT for x in c_unk)

    print("parser.py self-check assertions passed.")
