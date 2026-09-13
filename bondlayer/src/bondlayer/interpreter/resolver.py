"""Constraint resolution over the catalogue's typed attributes and the verified records.

``resolve(constraints, skus, records) -> list[Proposal]`` is the seam named in
``bondlayer.types.ConstraintInterpreter``. What comes back is not a list of
SKUs but a justification: for every listing that survives, one
``ResolvedConstraint`` per clause the shopper said, each carrying a
one-sentence note and, where a record answered it, the record's id.

The four kinds behave differently, and that difference is the product:

- **HARD** filters. It is applied to the adapter's typed attributes (category,
  ``shelf_price``, ``ram_gb``, ``storage_gb``, ``screen_in``, ``weight_kg``,
  ``gpu``, ``cpu``), never by substring over the title. A listing that lacks the
  attribute a HARD clause needs is excluded, and the reason kept is "attribute
  absent", not "failed". A derived attribute (``gpu_source == "title"``) is
  accepted and the note says it was derived. Product names ("ThinkBook 14 G3")
  are matched over the listing's normalised token bag (see ``similarity.py``).
- **SOFT** never filters. It contributes an ordering signal built from named
  attributes, and the note says which attributes were inferred. A SOFT clause
  with no heuristic stays in the justification as unsatisfied, with the marker.
- **SERVICE** and **VALUES** resolve to a verified record of the matching
  ``BenefitType`` that applies to the listing (``sku_id`` match, or ``None`` =
  the issuing merchant's whole shelf, narrowed by ``fact["scope"]``). The
  record is cited by id. The resolver cites only records it is handed; the
  caller hands it verified records only.
- Any SERVICE or VALUES clause with no such record resolves
  ``satisfied=False`` with the exact marker note ``← no catalogue attribute
  answers this`` and is appended to ``Proposal.unsatisfied``.

Proposal order: HARD pass, then the SOFT signal, then the count of satisfied
SERVICE+VALUES clauses, then shelf price ascending. Valuation reorders by
effective cost afterwards; that is the composition root's job.

No network, no model call. Everything here is a lookup or a comparison.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable

from bondlayer.types import (
    BenefitType,
    Constraint,
    ConstraintKind,
    Proposal,
    ResolvedConstraint,
    SignedRecord,
    Sku,
)
from bondlayer.valuation.reference_policy import MERCHANT_DOMAINS

from .parser import parse
from .similarity import TfidfIndex, tokens

#: Rendered verbatim by the console for an unanswered clause. Do not paraphrase.
UNANSWERED = "← no catalogue attribute answers this"

# --- HARD: what a clause means in catalogue terms ---------------------------

#: A budget ceiling. Shoppers (and the live decode) say "under $1,500" but also
#: "within a budget of 3000", "max 3000" and "$3000 or less"; an unread budget
#: used to fall through to a product-name spec and exclude every listing.
_CEILING_WORDS = (
    r"under|below|less\s+than|no\s+more\s+than|not\s+(?:more\s+than|over)|up\s+to|at\s+most"
    r"|max(?:imum)?(?:\s+of)?|within(?:\s+(?:a|my|the|your))?\s+budget(?:\s+of)?"
    r"|budget(?:\s+(?:is|of))?(?:\s+(?:about|of))?\s*:?"
)
_AMOUNT = r"(?:aud\s*)?\$?\s*(\d[\d,]*(?:\.\d+)?)(?![\d.,]*\s*(?:kg|gb|tb|mb|inch))"
_MONEY_MAX = re.compile(rf"\b(?:{_CEILING_WORDS})\s*{_AMOUNT}", re.IGNORECASE)
_MONEY_MAX_TRAILING = re.compile(
    r"\$?\s*\b(\d[\d,]*(?:\.\d+)?)\s*(?:aud\s*)?(?:or\s+(?:less|under|below)|max(?:imum)?|budget)\b",
    re.IGNORECASE,
)
_WEIGHT_MAX = re.compile(
    r"\b(?:under|below|less\s+than|no\s+more\s+than|up\s+to|max(?:imum)?)\s+(\d+(?:\.\d+)?)\s*kg\b",
    re.IGNORECASE,
)
_GB = re.compile(r"\b(\d+)\s*(?:gb|gigs?)\b", re.IGNORECASE)
_TB = re.compile(r"\b(\d+)\s*tb\b", re.IGNORECASE)
_INCH = re.compile(r"\b(\d+(?:\.\d+)?)\s*(?:inch(?:es)?|in)\b", re.IGNORECASE)
_GPU = re.compile(r"\b(rtx|gtx)\s*(\d{4})?\b", re.IGNORECASE)
_CPU = re.compile(r"\b(i[3579])\b", re.IGNORECASE)
_AT_LEAST_BEFORE = re.compile(
    r"(?:\b(?:at\s+least|minimum(?:\s+of)?|min\.?|no\s+less\s+than|over|more\s+than)|>=?)\s*$", re.IGNORECASE)
_AT_LEAST_AFTER = re.compile(
    r"^\s*(?:\+|(?:ram\s+|memory\s+|storage\s+)?(?:or\s+(?:more|above|higher|bigger|larger|greater)"
    r"|minimum|min\b|and\s+up|plus\b))", re.IGNORECASE)
_AT_MOST_BEFORE = re.compile(
    r"(?:\b(?:at\s+most|maximum(?:\s+of)?|max\.?|no\s+more\s+than|up\s+to|under|below|less\s+than)|<=?)\s*$",
    re.IGNORECASE)
_AT_MOST_AFTER = re.compile(
    r"^\s*(?:(?:ram\s+|memory\s+|storage\s+)?(?:or\s+(?:less|smaller|below|under|lower)|maximum|max\b))",
    re.IGNORECASE)

#: Words that say how to order a shelf, never what is on it. A HARD clause made
#: only of these ("cheapest", "best value") must not become a product-name
#: filter: no listing's tokens contain "cheapest", so every offer was excluded.
_ORDERING_WORDS = {
    "cheapest", "cheap", "cheaper", "lowest", "low", "price", "priced", "best", "value",
    "affordable", "inexpensive", "budget", "good", "great", "top", "find", "me", "want",
    "need", "buy", "get", "looking", "you", "have", "any", "some", "that", "is", "at",
    "least", "most", "within", "ram", "memory", "storage", "aud", "dollars",
    "new", "something", "beginner", "friendly", "gear", "equipment", "kit", "stuff", "setup",
}

#: Product nouns the shopper uses -> the category the catalogue files them
#: under, plus an optional typed attribute the noun implies.
#:
#: The category is the *filter*; the implied attribute is not. The catalogue
#: has one `category` column and no finer product type -- a monitor, a dock and
#: a sleeve are all `accessory` -- so narrowing "monitor" to listings that
#: publish `screen_in` would exclude products the shopper asked for. The frozen
#: gold sets label these clauses at category level (R11's gold is all 23
#: accessories, not the two monitors), and rule 4 says the eval wins. So the
#: noun becomes an ordering hint over the token bag instead: listings whose
#: tokens name it sort first, nothing is excluded, and the note says which.
_CATEGORY_WORDS: dict[str, tuple[str, str | None]] = {
    "laptop": ("laptop", None),
    "laptops": ("laptop", None),
    "notebook": ("laptop", None),
    "phone": ("phone", None),
    "phones": ("phone", None),
    "smartphone": ("phone", None),
    "vacuum": ("appliance", None),
    "coffee machine": ("appliance", None),
    "rice cooker": ("appliance", None),
    "kettle": ("appliance", None),
    "toaster": ("appliance", None),
    "microwave": ("appliance", None),
    "appliance": ("appliance", None),
    "monitor": ("accessory", "screen_in"),
    "portable ssd": ("accessory", "storage_gb"),
    "ssd": ("accessory", "storage_gb"),
    "power bank": ("accessory", None),
    "sleeve": ("accessory", None),
    "hub": ("accessory", None),
    "dock": ("accessory", None),
    "keyboard": ("accessory", None),
    "mouse": ("accessory", None),
    "charger": ("accessory", None),
    # Every podcasting listing is filed under audio (R06/R07 gold is the whole
    # audio shelf), so a live decode that marks "podcasting gear" HARD must
    # land on that category rather than on a product-name match nothing has.
    "podcasting gear": ("audio", None),
    "podcast gear": ("audio", None),
    "podcasting": ("audio", None),
    "podcast": ("audio", None),
    "recording gear": ("audio", None),
    "audio": ("audio", None),
    "microphone": ("audio", None),
    "mic": ("audio", None),
    "headset": ("audio", None),
    "headphones": ("audio", None),
    "speaker": ("audio", None),
    "cover": ("warranty", None),
    "warranty": ("warranty", None),
    "protection": ("warranty", None),
}
#: Categories that are a service sold as a product, not a physical good.
_SERVICE_CATEGORIES = {"warranty"}


@dataclass(frozen=True)
class HardSpec:
    """One HARD clause, decoded into a catalogue predicate."""

    kind: str  # price | weight | category | ram | storage | screen | gpu | cpu | product | unknown
    value: object = None
    attribute: str | None = None
    narrow: str | None = None  # a typed attribute that must be present (category refinement)
    op: str = "eq"  # eq | min | max, for ram, storage and screen bounds


def interpret_hard(text: str) -> list[HardSpec]:
    """Everything a HARD clause asserts, as typed predicates.

    One clause can carry two facts ("laptop under $1,500" is a category and a
    price ceiling), so this returns a list. A clause nothing here understands
    comes back as a single ``product`` spec for the token matcher, or
    ``unknown`` when it has no matchable tokens at all.
    """
    specs: list[HardSpec] = []
    lowered = text.lower()
    consumed = text

    if m := _WEIGHT_MAX.search(text):
        specs.append(HardSpec("weight", float(m.group(1)), "weight_kg"))
        consumed = consumed.replace(m.group(0), " ")
    if m := (_MONEY_MAX.search(consumed) or _MONEY_MAX_TRAILING.search(consumed)):
        specs.append(HardSpec("price", Decimal(m.group(1).replace(",", "")), "shelf_price"))
        consumed = consumed.replace(m.group(0), " ")
    if m := _TB.search(consumed):
        specs.append(HardSpec("storage", int(m.group(1)) * 1024, "storage_gb", op=_bound_op(consumed, m)))
        consumed = consumed.replace(m.group(0), " ")
    if m := _GB.search(consumed):
        gb = int(m.group(1))
        # Memory tops out well under 128GB in this catalogue; anything larger
        # spelled in GB is storage.
        op = _bound_op(consumed, m)
        if gb <= 64:
            specs.append(HardSpec("ram", gb, "ram_gb", op=op))
        else:
            specs.append(HardSpec("storage", gb, "storage_gb", op=op))
        consumed = consumed.replace(m.group(0), " ")
    if m := _INCH.search(consumed):
        specs.append(HardSpec("screen", float(m.group(1)), "screen_in", op=_bound_op(consumed, m)))
        consumed = consumed.replace(m.group(0), " ")
    if m := _GPU.search(consumed):
        family = m.group(1).upper() + (m.group(2) or "")
        specs.append(HardSpec("gpu", family, "gpu"))
        consumed = consumed.replace(m.group(0), " ")
    if m := _CPU.search(consumed):
        specs.append(HardSpec("cpu", m.group(1).lower(), "cpu"))
        consumed = consumed.replace(m.group(0), " ")

    for word, (category, narrow) in sorted(_CATEGORY_WORDS.items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"\b{re.escape(word)}\b", consumed, re.IGNORECASE):
            specs.append(HardSpec("category", category, "category", narrow))
            consumed = re.sub(rf"\b{re.escape(word)}\b", " ", consumed, flags=re.IGNORECASE)
            break

    if not specs:
        leftover = [t for t in tokens(consumed) if t not in _STOPWORDS and t not in _ORDERING_WORDS]
        if leftover:
            specs.append(HardSpec("product", " ".join(leftover), "title/brand/model_key tokens"))
        else:
            specs.append(HardSpec("unknown", lowered))
    return specs


_STOPWORDS = {"a", "an", "the", "with", "and", "or", "for", "of", "to", "i", "my", "one", "own", "already"}


def _bound_op(text: str, m: re.Match[str]) -> str:
    """Whether a spec is a floor ("at least 16GB"), a ceiling ("up to 1TB") or exact."""
    before, after = text[:m.start()], text[m.end():]
    if _AT_LEAST_BEFORE.search(before) or _AT_LEAST_AFTER.search(after):
        return "min"
    if _AT_MOST_BEFORE.search(before) or _AT_MOST_AFTER.search(after):
        return "max"
    return "eq"


def _fmt_money(value: Decimal) -> str:
    return f"${value:,.2f}"


def _check_hard(spec: HardSpec, sku: Sku, index: TfidfIndex | None, categories: set[str] | None):
    """Evaluate one predicate on one listing.

    Returns ``(passed, attribute, note)``. A failed check's note is the
    exclusion reason kept for the trace.
    """
    attrs = sku.attributes
    if spec.kind == "price":
        ok = sku.shelf_price <= spec.value
        return ok, "shelf_price", (
            f"Shelf price {_fmt_money(sku.shelf_price)} is within the {_fmt_money(spec.value)} ceiling."
            if ok else
            f"Shelf price {_fmt_money(sku.shelf_price)} exceeds the {_fmt_money(spec.value)} ceiling."
        )
    if spec.kind == "weight":
        weight = attrs.get("weight_kg")
        if not isinstance(weight, (int, float)):
            return False, "weight_kg", "Attribute absent: the listing publishes no weight_kg, so the weight bound cannot be checked."
        ok = weight <= spec.value
        return ok, "weight_kg", (
            f"weight_kg {weight} is at or under the {spec.value}kg bound."
            if ok else f"weight_kg {weight} is over the {spec.value}kg bound."
        )
    if spec.kind in ("ram", "storage", "screen"):
        attribute = spec.attribute
        value = attrs.get(attribute)
        if not isinstance(value, (int, float)):
            return False, attribute, f"Attribute absent: the listing publishes no {attribute}, so this spec cannot be checked."
        unit = "GB" if spec.kind != "screen" else "in"
        if spec.op == "min":
            ok, wanted = float(value) >= float(spec.value), f"at least {spec.value:g}{unit}"
        elif spec.op == "max":
            ok, wanted = float(value) <= float(spec.value), f"at most {spec.value:g}{unit}"
        else:
            ok, wanted = float(value) == float(spec.value), f"{spec.value:g}{unit}"
        return ok, attribute, (
            f"{attribute} {value:g}{unit} meets the requested {wanted} (typed attribute, not title text)."
            if ok else f"{attribute} {value:g}{unit} does not meet the requested {wanted}."
        )
    if spec.kind == "gpu":
        gpu = attrs.get("gpu")
        if not gpu:
            return False, "gpu", "Attribute absent: the listing publishes no discrete GPU, so the GPU requirement cannot be checked."
        ok = str(gpu).upper().startswith(str(spec.value).upper())
        derived = " (derived by the adapter from the title, not a published column)" if attrs.get("gpu_source") == "title" else ""
        return ok, "gpu", (
            f"gpu {gpu} satisfies the {spec.value} requirement{derived}."
            if ok else f"gpu {gpu} is not an {spec.value} part{derived}."
        )
    if spec.kind == "cpu":
        cpu = attrs.get("cpu")
        if not cpu:
            return False, "cpu", "Attribute absent: the listing publishes no cpu, so the processor family cannot be checked."
        ok = spec.value in tokens(str(cpu))
        return ok, "cpu", (
            f"cpu {cpu} is in the {spec.value} family." if ok else f"cpu {cpu} is not in the {spec.value} family."
        )
    if spec.kind == "category":
        wanted = categories or {spec.value}
        if sku.category not in wanted:
            return False, "category", f"Category {sku.category!r} is not {sorted(wanted)!r}."
        # The category is the filter; the noun's implied attribute only ranks.
        # Excluding on it would drop listings the shopper asked for, because
        # the catalogue files every accessory under one category.
        if spec.narrow:
            has = spec.narrow in attrs
            implied = (
                f", and it publishes the {spec.narrow} the product noun implies"
                if has else
                f", though it publishes no {spec.narrow}, so the product noun only orders it and never excludes it"
            )
            return True, "category", f"Filed under category {sku.category!r}{implied}."
        return True, "category", (
            f"Filed under category {sku.category!r}; the catalogue has no finer "
            "product type, so every listing in the category passes."
        )
    if spec.kind == "product":
        if index is None:
            return False, spec.attribute, "No catalogue index to match a product name against."
        match = index.covered(str(spec.value)).get(sku.sku_id)
        if match is None:
            return False, spec.attribute, f"Listing tokens do not cover the product name {spec.value!r}."
        return True, spec.attribute, (
            f"Listing tokens cover every token of {spec.value!r} (similarity {match.score:.2f}); "
            "matched over normalised title, brand and model_key tokens, not by substring."
        )
    return None, None, f"Clause {spec.value!r} could not be read as a catalogue filter and was not applied."


# --- SOFT: ordering signals ---------------------------------------------------


@dataclass(frozen=True)
class SoftSignal:
    inferred: str  # human phrase for the note, e.g. "weight_kg ascending"
    key: Callable[[Sku], tuple]  # lower sorts first


def _absent_last(value, *, negate: bool = False) -> tuple:
    if not isinstance(value, (int, float, Decimal)):
        return (1, 0.0)
    return (0, -float(value) if negate else float(value))


def _soft_price_target(amount: Decimal) -> SoftSignal:
    return SoftSignal(
        f"shelf_price closest to {_fmt_money(amount)}",
        lambda s: (0, abs(float(s.shelf_price - amount))),
    )


_SOFT_RULES: tuple[tuple[re.Pattern[str], Callable[[re.Match[str]], SoftSignal]], ...] = (
    (re.compile(r"\b(?:around|about|roughly|ideally\s+under)\s+\$?\s*(\d[\d,]*(?:\.\d+)?)", re.I),
     lambda m: _soft_price_target(Decimal(m.group(1).replace(",", "")))),
    (re.compile(r"\b(?:light|lightweight|carry\s+every\s+day|portable|travel)\b", re.I),
     lambda m: SoftSignal("weight_kg ascending (listings without a weight sort last)",
                          lambda s: _absent_last(s.attributes.get("weight_kg")))),
    (re.compile(r"\b(?:video\s+editing|design\s+work|gaming|rendering|photo\s+editing|creative)\b", re.I),
     lambda m: SoftSignal("ram_gb descending, then a discrete gpu present",
                          lambda s: (0, -float(s.attributes.get("ram_gb") or 0), 0 if s.attributes.get("gpu") else 1))),
    (re.compile(r"\b(?:cheapest|cheap|tight\s+budget|best\s+value|beginner|budget)\b", re.I),
     lambda m: SoftSignal("shelf_price ascending", lambda s: (0, float(s.shelf_price)))),
    (re.compile(r"\b(?:podcast\w*|record\s+interviews|headset\s+for\s+calls|streaming|recording)\b", re.I),
     lambda m: SoftSignal("category audio first", lambda s: (0 if s.category == "audio" else 1, 0.0))),
    (re.compile(r"\b(?:suit\s+my\s+work|for\s+work|work\s+laptop|office|business)\b", re.I),
     lambda m: SoftSignal("ram_gb of at least 16 first, then weight_kg ascending",
                          lambda s: (0 if (s.attributes.get("ram_gb") or 0) >= 16 else 1,
                                     _absent_last(s.attributes.get("weight_kg"))))),
)


def interpret_soft(text: str) -> SoftSignal | None:
    for pattern, build in _SOFT_RULES:
        m = pattern.search(text)
        if m:
            return build(m)
    return None


# --- SERVICE and VALUES: which record answers the clause ----------------------


@dataclass(frozen=True)
class RecordNeed:
    benefit_type: BenefitType
    predicate: Callable[[dict], bool] | None = None  # over record.fact
    predicate_text: str | None = None


_RECORD_RULES: tuple[tuple[re.Pattern[str], RecordNeed], ...] = (
    (re.compile(r"\breturn|\bsend\s+back", re.I), RecordNeed(BenefitType.FREE_RETURNS)),
    (re.compile(r"\btrade[- ]?in\b", re.I), RecordNeed(BenefitType.TRADE_IN_CREDIT)),
    (re.compile(r"\bwarranty|\bcover\b|\bbreaks?\b", re.I), RecordNeed(BenefitType.WARRANTY)),
    (re.compile(r"\bdeliver\w*\s+free|\bfree\s+deliver", re.I),
     RecordNeed(BenefitType.DELIVERY, lambda f: "free_over_aud" in f, "a free-delivery threshold")),
    (re.compile(r"\bdeliver", re.I), RecordNeed(BenefitType.DELIVERY)),
    (re.compile(r"\bcarbon\s+neutral\b", re.I),
     RecordNeed(BenefitType.SUSTAINABILITY, lambda f: bool(f.get("carbon_neutral")), "a carbon_neutral fact")),
    (re.compile(r"\bsustainab", re.I), RecordNeed(BenefitType.SUSTAINABILITY)),
    (re.compile(r"\brepair|\bfix\s+it\b", re.I), RecordNeed(BenefitType.REPAIRABILITY)),
    (re.compile(r"\bethic|\bwhere\s+(?:it|it's|it\s+is|they|they're|they\s+are)\s+made\b", re.I),
     RecordNeed(BenefitType.ETHICAL_SOURCING)),
    (re.compile(r"\blast\b|\bdurab|\bthrowing\s+things\s+away\b", re.I), RecordNeed(BenefitType.DURABILITY)),
)


def interpret_record_need(text: str) -> RecordNeed | None:
    for pattern, need in _RECORD_RULES:
        if pattern.search(text):
            return need
    return None


def _scope_words(record) -> frozenset[str] | None:
    scope = record.fact.get("scope")
    if scope is None:
        return None
    words = {w.strip().lower() for entry in str(scope).split(",") for w in entry.split() if w.strip()}
    return frozenset(words) or None


def _applies(signed: SignedRecord, sku: Sku, merchant_domains: dict[str, str]) -> bool:
    record = signed.record
    if record.sku_id is not None:
        if record.sku_id != sku.sku_id:
            return False
    merchant = sku.attributes.get("merchant")
    if merchant is None or merchant_domains.get(str(merchant)) != record.issuer:
        return False
    scope = _scope_words(record)
    return scope is None or sku.category.lower() in scope


def _fact_summary(record) -> str:
    parts = [f"{k}={v}" for k, v in sorted(record.fact.items()) if k != "scope"]
    return ", ".join(parts) if parts else "no further detail"


def _record_note(signed: SignedRecord, kind: ConstraintKind) -> str:
    record = signed.record
    scope = f" for {record.fact['scope']}" if "scope" in record.fact else ""
    gating = [c for c in record.conditions if re.match(r"^[a-z0-9][a-z0-9_.:-]*$", c)]
    conditions = f"; subject to {', '.join(gating)}" if gating else ""
    tail = ("; validated, never priced" if kind is ConstraintKind.VALUES
            else "; priced by the valuation, not here")
    return (
        f"Answered by verified record {record.record_id} from {record.issuer}: "
        f"{record.benefit_type.value}{scope} ({_fact_summary(record)}){conditions}{tail}."
    )


# --- the resolution -----------------------------------------------------------


@dataclass(frozen=True)
class Exclusion:
    sku_id: str
    constraint: Constraint
    attribute: str | None
    reason: str


@dataclass
class Resolution:
    """``resolve()``'s working, kept for the trace and the evaluation."""

    proposals: list[Proposal]
    excluded: list[Exclusion] = field(default_factory=list)
    hard_specs: dict[str, list[HardSpec]] = field(default_factory=dict)  # by constraint text
    soft_inferred: dict[str, str | None] = field(default_factory=dict)
    not_applied: list[Constraint] = field(default_factory=list)  # HARD clauses nobody could read

    @property
    def sku_ids(self) -> list[str]:
        return [p.sku.sku_id for p in self.proposals]


def _plan_categories(constraints: list[Constraint], specs: dict[str, list[HardSpec]]):
    """How the category clauses combine, and which one scopes rather than filters.

    Two product nouns ("a laptop and a dock") widen the filter: either
    category passes; the bundler composes them later. A service product with a
    physical noun ("two-year cover on a laptop") is one product: the warranty
    is the filter and the physical noun narrows the ordering, not the shelf.
    """
    category_specs = [(c, s) for c in constraints for s in specs.get(c.text, []) if s.kind == "category"]
    wanted = {s.value for _, s in category_specs}
    scoping: dict[str, str] = {}
    if wanted & _SERVICE_CATEGORIES and wanted - _SERVICE_CATEGORIES:
        for c, s in category_specs:
            if s.value not in _SERVICE_CATEGORIES:
                scoping[c.text] = s.value
        wanted &= _SERVICE_CATEGORIES
    return wanted or None, scoping


def resolve_detailed(
    constraints: list[Constraint],
    skus: list[Sku],
    records: list[SignedRecord],
    *,
    merchant_domains: dict[str, str] | None = None,
) -> Resolution:
    """``resolve`` with its working shown."""
    merchant_domains = dict(MERCHANT_DOMAINS if merchant_domains is None else merchant_domains)
    index = TfidfIndex(skus) if skus else None

    hard = [c for c in constraints if c.kind is ConstraintKind.HARD]
    soft = [c for c in constraints if c.kind is ConstraintKind.SOFT]
    evidence = [c for c in constraints if c.kind in (ConstraintKind.SERVICE, ConstraintKind.VALUES)]

    specs = {c.text: interpret_hard(c.text) for c in hard}
    wanted_categories, scoping = _plan_categories(hard, specs)
    soft_signals = {c.text: interpret_soft(c.text) for c in soft}
    needs = {c.text: interpret_record_need(c.text) for c in evidence}

    excluded: list[Exclusion] = []
    not_applied: list[Constraint] = []
    survivors: list[tuple[Sku, list[ResolvedConstraint]]] = []

    for sku in skus:
        resolved: list[ResolvedConstraint] = []
        alive = True
        for c in hard:
            notes: list[str] = []
            attribute: str | None = None
            for spec in specs[c.text]:
                if spec.kind == "category" and c.text in scoping:
                    # Scoping noun: an ordering hint, never a filter.
                    covered = index.covered(scoping[c.text]).get(sku.sku_id) if index else None
                    notes.append(
                        f"'{scoping[c.text]}' names what the cover is for, not the shelf it sits on; "
                        + ("this listing's tokens name it too." if covered else "this listing's tokens do not name it.")
                    )
                    attribute = attribute or "title/brand/model_key tokens"
                    continue
                ok, attr, note = _check_hard(spec, sku, index, wanted_categories if spec.kind == "category" else None)
                if ok is None:  # unreadable clause: never a hard failure
                    if c not in not_applied:
                        not_applied.append(c)
                    notes.append(note)
                    continue
                attribute = attribute or attr
                if not ok:
                    excluded.append(Exclusion(sku.sku_id, c, attr, note))
                    alive = False
                    break
                notes.append(note)
            if not alive:
                break
            satisfied = all(s.kind != "unknown" for s in specs[c.text])
            resolved.append(ResolvedConstraint(c, satisfied, None, attribute, " ".join(notes) or "Applied."))
        if not alive:
            continue
        survivors.append((sku, resolved))

    # SOFT ordering signal: mean normalised rank over the clauses with a
    # heuristic. Listings with an equal key share a rank, so the tie falls
    # through to the evidence count and then to shelf price, as specified.
    soft_rank: dict[str, float] = {s.sku_id: 0.0 for s, _ in survivors}
    active = [(c, sig) for c, sig in soft_signals.items() if sig is not None]
    n = max(1, len(survivors) - 1)
    for _, sig in active:
        ordered = sorted(survivors, key=lambda pair: sig.key(pair[0]))
        position = 0
        for i, (sku, _) in enumerate(ordered):
            if i and sig.key(sku) != sig.key(ordered[i - 1][0]):
                position = i
            soft_rank[sku.sku_id] += (position / n) / len(active)
    # The product noun inside a category clause ("rice cooker" is one of many
    # appliances, "monitor" one of many accessories) still orders: listings
    # whose token bag names it come first. A hint, never a filter -- the shelf
    # belongs to the category.
    hints = dict(scoping)
    for c in hard:
        for spec in specs[c.text]:
            if spec.kind == "category" and c.text not in scoping:
                noun = next((w for w in sorted(_CATEGORY_WORDS, key=len, reverse=True)
                             if re.search(rf"\b{re.escape(w)}\b", c.text, re.IGNORECASE)), None)
                if noun and noun != spec.value:
                    hints[c.text] = noun
    for text, noun in hints.items():
        if index is None:
            continue
        covered = index.covered(noun)
        if not covered:
            continue  # no listing names it; the hint carries no information
        for sku, _ in survivors:
            soft_rank[sku.sku_id] += 0.0 if sku.sku_id in covered else 1.0

    proposals: list[Proposal] = []
    for sku, resolved in survivors:
        resolved = list(resolved)
        unsatisfied: list[Constraint] = []
        cited: list[SignedRecord] = []

        for c in soft:
            sig = soft_signals[c.text]
            if sig is None:
                resolved.append(ResolvedConstraint(c, False, None, None, UNANSWERED))
                continue
            resolved.append(ResolvedConstraint(
                c, True, None, sig.inferred.split()[0],
                f"Ranked, not filtered: inferred {sig.inferred} from the clause.",
            ))

        for c in evidence:
            need = needs[c.text]
            answer: SignedRecord | None = None
            if need is not None:
                candidates = [
                    r for r in records
                    if r.record.benefit_type is need.benefit_type
                    and _applies(r, sku, merchant_domains)
                    and (need.predicate is None or need.predicate(r.record.fact))
                ]
                # A scoped record is the more specific fact; cite it first.
                candidates.sort(key=lambda r: (0 if "scope" in r.record.fact else 1, r.record.record_id))
                answer = candidates[0] if candidates else None
            if answer is None:
                resolved.append(ResolvedConstraint(c, False, None, None, UNANSWERED))
                unsatisfied.append(c)
                continue
            cited.append(answer)
            resolved.append(ResolvedConstraint(c, True, answer.record.record_id, None, _record_note(answer, c.kind)))

        for c in not_applied:
            if c not in unsatisfied:
                unsatisfied.append(c)

        proposals.append(Proposal(sku=sku, resolved=resolved, unsatisfied=unsatisfied, records=cited))

    def order(p: Proposal) -> tuple:
        answered = sum(1 for r in p.resolved if r.constraint.kind in (ConstraintKind.SERVICE, ConstraintKind.VALUES) and r.satisfied)
        return (round(soft_rank[p.sku.sku_id], 3), -answered, p.sku.shelf_price, p.sku.sku_id)

    proposals.sort(key=order)
    inferred = {t: (s.inferred if s else None) for t, s in soft_signals.items()}
    for text, noun in hints.items():
        inferred[f"[hint] {text}"] = f"listings whose token bag names {noun!r} first"
    return Resolution(
        proposals=proposals,
        excluded=excluded,
        hard_specs=specs,
        soft_inferred=inferred,
        not_applied=not_applied,
    )


def resolve(
    constraints: list[Constraint], skus: list[Sku], records: list[SignedRecord],
    *, merchant_domains: dict[str, str] | None = None,
) -> list[Proposal]:
    """The protocol seam: proposals only, ordered as described in the module docstring."""
    return resolve_detailed(constraints, skus, records, merchant_domains=merchant_domains).proposals


class ConstraintInterpreter:
    """Implements bondlayer.types.ConstraintInterpreter without changing it."""

    parse = staticmethod(parse)
    resolve = staticmethod(resolve)
    resolve_detailed = staticmethod(resolve_detailed)
