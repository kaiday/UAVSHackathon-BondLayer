"""Deterministic, evidence-first constraint resolution.

The parser preserves a shopper's words. This module turns those words into
typed catalogue comparisons and, separately, verified benefit-record evidence.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from decimal import Decimal
from typing import TYPE_CHECKING

from bondlayer.types import (
    BenefitType, Constraint, ConstraintKind, Proposal, ResolvedConstraint,
    SignedRecord, Sku,
)

from .parser import parse

if TYPE_CHECKING:
    from bondlayer.types import Signer


_CATEGORY_ONTOLOGY = {
    "laptop": "laptop", "phone": "phone", "portable ssd": "accessory",
    "monitor": "accessory", "dock": "accessory", "microphone": "audio",
    "headset": "audio", "coffee machine": "appliance", "rice cooker": "appliance",
    "vacuum": "appliance",
}
_SERVICE_ONTOLOGY = (
    (("return", "send back", "painless"), BenefitType.FREE_RETURNS),
    (("cover", "warranty", "breaks"), BenefitType.WARRANTY),
    (("trade in",), BenefitType.TRADE_IN_CREDIT),
    (("deliver", "delivery"), BenefitType.DELIVERY),
)
_VALUES_ONTOLOGY = (
    (("repair", "fix it", "throwing things away"), BenefitType.REPAIRABILITY),
    (("sustainable", "carbon neutral"), BenefitType.SUSTAINABILITY),
    (("last", "durab"), BenefitType.DURABILITY),
    (("where it", "ethical"), BenefitType.ETHICAL_SOURCING),
)


def _normal(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()


def _number(text: str) -> float | None:
    match = re.search(r"\d[\d,]*(?:\.\d+)?", text)
    return float(match.group(0).replace(",", "")) if match else None


def _has_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def _numeric_comparison(text: str, actual: float, expected: float) -> bool:
    if _has_any(text, ("under", "below", "less than", "up to", "no more than")):
        return actual <= expected
    if _has_any(text, ("at least", "more than", "over")):
        return actual >= expected
    return actual >= expected  # bare capacities mean "at least"


def _attribute_number(sku: Sku, name: str) -> float | None:
    value = sku.attributes.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


#: Units that mean a numeric clause is NOT about money. "under 1.3kg" and
#: "under $200" are the same English comparator over different quantities.
_NON_CURRENCY_UNIT = re.compile(
    r'\b\d+(?:\.\d+)?\s*(?:kg|g|gb|tb|mb|gigs?|inch(?:es)?|in)\b|\d\s*"'
)


def _is_money_clause(text: str) -> bool:
    if _has_any(text, ("$", "aud", "usd", "budget", "price", "spend")):
        return True
    if _NON_CURRENCY_UNIT.search(text):
        return False
    return _has_any(text, ("under ", "below ", "no more than ", "up to ", "less than "))


def _category_phrase(text: str) -> tuple[str, str] | None:
    """Longest whole-word ontology phrase in the clause, or None.

    Substring matching is what this whole project argues against, and it bites
    here: "phone" is inside "microphone", so a microphone resolved as a phone
    and the request returned nothing. Match on word boundaries, and prefer the
    longest phrase so "coffee machine" beats any shorter fragment.
    """
    best: tuple[str, str] | None = None
    for phrase, category in _CATEGORY_ONTOLOGY.items():
        if re.search(rf"\b{re.escape(phrase)}\b", text) and (
            best is None or len(phrase) > len(best[0])
        ):
            best = (phrase, category)
    return best


#: Explicit model families the parser emits (R18/R19/R20), mapped to the
#: model_key prefix the adapter publishes as a typed attribute.
_MODEL_FAMILY = (
    ("thinkbook", "tb"),
    ("xps", "xps"),
)


def _model_match(text: str, sku: Sku) -> tuple[bool, str] | None:
    """Match an explicit model reference against the typed model_key.

    Returns None when the clause names no known model family, so the caller
    falls through instead of scanning titles. Matching on title substrings
    is forbidden: the adapter already lifted the model identity into the
    model_key attribute, and that is what we compare.
    """
    words = re.sub(r"[^a-z0-9]+", " ", text).strip().split()
    family = next((code for name, code in _MODEL_FAMILY if name in words), None)
    if family is None:
        return None
    key = str(sku.attributes.get("model_key", ""))
    if not key:
        return False, "No typed model_key is published for this listing."
    wanted = [dict(_MODEL_FAMILY).get(word, word) for word in words]
    normalised = re.sub(r"[^a-z0-9]+", "", key.lower())
    missing = [word for word in wanted if word not in normalised]
    if not missing:
        return True, f"Typed model_key {key} matches the requested model."
    return False, f"Typed model_key {key} is not the requested model."


#: Contract marker for an unanswered SERVICE/VALUES clause (DAY2-PLAN WS-A).
#: Rendered verbatim by WS-E; do not paraphrase.
_UNANSWERED_MARKER = "← no catalogue attribute answers this"


def _hard_resolution(constraint: Constraint, sku: Sku) -> tuple[bool, str | None, str]:
    """Resolve a catalogue-only hard clause without generic keyword matching."""
    text = _normal(constraint.text)
    if "cover" in text and ("year" in text or "month" in text):
        ok = sku.category == "warranty"
        return ok, "category", ("Matches the standalone warranty-cover product category."
                                if ok else "This is not a standalone warranty-cover product.")
    # Here laptop scopes a warranty SKU, rather than naming the SKU's category.
    # Coverage is read from the typed model_key (wty-lap-24), never the title.
    if text == "laptop" and sku.category == "warranty":
        key = re.sub(r"[^a-z0-9]+", "", str(sku.attributes.get("model_key", "")).lower())
        ok = "lap" in key
        return ok, "model_key", ("Warranty product explicitly covers laptops."
                              if ok else "Warranty product does not state laptop coverage.")
    matched = _category_phrase(text)
    if matched is not None:
        phrase, category = matched
        category_ok = sku.category == category
        # R01 deliberately combines its product and budget wording into a
        # single HARD constraint.  Both predicates still have to pass.
        if any(token in text for token in ("$", "aud", "usd", "under ", "below ", "no more than ")):
            amount = _number(text)
            if amount is not None:
                price_ok = _numeric_comparison(text, float(sku.shelf_price), amount)
                ok = category_ok and price_ok
                return ok, "category,shelf_price", (
                    f"Category is {sku.category} and shelf price ${sku.shelf_price} satisfy the '{phrase}' and ${amount:,.0f} limits."
                    if ok else f"The combined category/budget constraint is not met (category={sku.category}, price=${sku.shelf_price})."
                )
        return category_ok, "category", (f"Category is {sku.category}, the ontology match for '{phrase}'."
                                           if category_ok else f"Category is {sku.category}, not the '{phrase}' product class.")
    # "under 1.3kg" and "under $200" both contain "under ". Only the second is
    # about money. A comparator word alone must never claim a clause that
    # carries a non-currency unit, or a weight limit is silently compared
    # against a shelf price and nothing matches.
    if _is_money_clause(text):
        amount = _number(text)
        if amount is not None:
            ok = _numeric_comparison(text, float(sku.shelf_price), amount)
            return ok, "shelf_price", (f"Shelf price ${sku.shelf_price} is within the stated ${amount:,.2f} limit."
                                         if ok else f"Shelf price ${sku.shelf_price} exceeds the stated ${amount:,.2f} limit.")
    if re.search(r"\b\d+(?:\.\d+)?\s*tb\b", text) or _has_any(text, ("storage", "ssd", "hdd")):
        amount = _number(text)
        if amount is not None:
            expected = amount * 1024 if "tb" in text else amount
            actual = _attribute_number(sku, "storage_gb")
            ok = actual is not None and _numeric_comparison(text, actual, expected)
            return ok, "storage_gb", (f"Storage is {actual:g}GB, satisfying {expected:g}GB."
                                        if ok else "No sufficient typed storage_gb value is published.")
    if re.search(r"\b\d+(?:\.\d+)?\s*(?:gb|gigs?|mb)\b", text):
        amount = _number(text)
        if amount is not None:
            expected = amount / 1024 if "mb" in text else amount
            actual = _attribute_number(sku, "ram_gb")
            ok = actual is not None and _numeric_comparison(text, actual, expected)
            return ok, "ram_gb", (f"RAM is {actual:g}GB, satisfying {expected:g}GB."
                                    if ok else "No sufficient typed ram_gb value is published.")
    if "inch" in text or '"' in constraint.text:
        amount = _number(text)
        if amount is not None:
            actual = _attribute_number(sku, "screen_in")
            compared = _numeric_comparison(text, actual, amount) if actual is not None else False
            bare_size = not _has_any(text, ("under", "below", "at least", "more than", "over"))
            ok = compared and (not bare_size or abs(actual - amount) < 0.11)
            return ok, "screen_in", (f"Screen is {actual:g} inches and matches the requested size."
                                       if ok else "No matching typed screen_in value is published.")
    if re.search(r"\b\d+(?:\.\d+)?\s*(?:kg|g)\b", text):
        amount = _number(text)
        if amount is not None:
            expected = amount / 1000 if re.search(r"\b\d+(?:\.\d+)?\s*g\b", text) else amount
            actual = _attribute_number(sku, "weight_kg")
            ok = actual is not None and _numeric_comparison(text, actual, expected)
            return ok, "weight_kg", (f"Weight is {actual:g}kg, satisfying the requested limit."
                                       if ok else "No sufficient typed weight_kg value is published.")
    gpu_match = re.search(r"\b(?:rtx|gtx)(?:\s*\d{3,4})?\b", text)
    if gpu_match:
        wanted = re.sub(r"\s+", "", gpu_match.group(0)).upper()
        actual = str(sku.attributes.get("gpu", "")).replace(" ", "").upper()
        ok = bool(actual) and actual.startswith(wanted)
        return ok, "gpu", (f"Typed GPU is {sku.attributes.get('gpu')} ({sku.attributes.get('gpu_source')} provenance)."
                            if ok else "No matching typed GPU attribute is published.")
    cpu_match = re.search(r"\b(?:i[3579]|ryzen\s*[3579]|m[1234])\b", text)
    if cpu_match:
        wanted = _normal(cpu_match.group(0)).replace(" ", "")
        actual = _normal(str(sku.attributes.get("cpu", ""))).replace(" ", "")
        ok = wanted in actual
        return ok, "cpu", (f"CPU is {sku.attributes.get('cpu')}, matching {cpu_match.group(0)}."
                            if ok else "No matching typed cpu value is published.")
    # Explicit model references compare the typed model_key the adapter
    # publishes, never title substrings (WS-A Forbidden).
    model_hit = _model_match(text, sku)
    if model_hit is not None:
        ok, note = model_hit
        return ok, "model_key", note
    return False, None, "No ontology rule can verify this hard clause."


def _soft_resolution(constraint: Constraint, sku: Sku) -> tuple[bool, str | None, str, float]:
    """Score an inferred use case. A miss never filters a SKU."""
    text = _normal(constraint.text)
    ram, screen, weight = (_attribute_number(sku, name) for name in ("ram_gb", "screen_in", "weight_kg"))
    cpu = _normal(str(sku.attributes.get("cpu", "")))
    if _has_any(text, ("design work", "design")):
        points = int((ram or 0) >= 16) + int((screen or 0) >= 14) + int(any(x in cpu for x in ("i7", "i9", "ryzen 7", "ryzen 9", "m2", "m3", "m4")))
        return points >= 2, "ram_gb,cpu,screen_in", (f"Design-work inference: {ram or 0:g}GB RAM, {sku.attributes.get('cpu', 'unknown')} CPU, {screen or 0:g}-inch screen ({points}/3 signals)."), float(points)
    if "video editing" in text:
        points = int((ram or 0) >= 32) + int((screen or 0) >= 14) + int(bool(sku.attributes.get("gpu"))) + int(any(x in cpu for x in ("i7", "i9", "ryzen 7", "ryzen 9", "m2", "m3", "m4")))
        return points >= 2, "ram_gb,cpu,screen_in,gpu", f"Video-editing inference uses RAM, CPU class, screen and GPU ({points}/4 signals).", float(points)
    if "carry every day" in text:
        ok = weight is not None and weight <= 1.5
        return ok, "weight_kg", (f"Daily-carry inference: typed weight is {weight:g}kg." if weight is not None else "No typed weight_kg is available for a portability inference."), 2.0 if ok else 0.0
    if "record interviews on the go" in text:
        ok = sku.category == "audio" and weight is not None and weight <= 1.5
        return ok, "category,weight_kg", "Interview-on-the-go inference uses audio category and typed portability; USB input is not published, so it is not claimed.", 2.0 if ok else 0.0
    if _has_any(text, ("podcast", "headset for calls")):
        ok = sku.category == "audio"
        return ok, "category", "Audio category is the ontology match for this recording/calls use case.", 1.0 if ok else 0.0
    if "work laptop" in text:
        ok = sku.category == "laptop"
        return ok, "category", "Laptop category is the best-supported interpretation of a work laptop.", 1.0 if ok else 0.0
    if _has_any(text, ("cheapest", "best value")):
        return True, "shelf_price", f"Ranks by shelf price; this listing is ${sku.shelf_price}.", 0.0
    if _has_any(text, ("around", "ideally", "roughly", "about")):
        amount = _number(text)
        if amount is not None:
            distance = abs(float(sku.shelf_price) - amount) / max(amount, 1)
            return True, "shelf_price", f"Soft budget target is ${amount:,.0f}; shelf price is ${sku.shelf_price}.", max(0.0, 1.0 - distance)
    if "gift" in text:
        return True, "category", f"Assumption: a broadly useful {sku.category} item can be a gift; no gift-preference attribute is published.", 0.05
    if "beginner" in text:
        ok = sku.category == "audio"
        return ok, "category", "Assumption: audio gear is the relevant beginner-podcasting class; ease-of-use is not published.", 0.25 if ok else 0.0
    return False, None, "No published ontology feature answers this soft preference.", 0.0


def _wanted_benefit(constraint: Constraint) -> BenefitType | None:
    ontology = _SERVICE_ONTOLOGY if constraint.kind is ConstraintKind.SERVICE else _VALUES_ONTOLOGY
    text = _normal(constraint.text)
    return next((kind for phrases, kind in ontology if _has_any(text, phrases)), None)


def _issuer_for(sku: Sku) -> str | None:
    """Resolve merchant domain from the published profile, never a literal."""
    merchant_id = sku.attributes.get("merchant")
    if not isinstance(merchant_id, str) or not merchant_id:
        return None
    try:
        from bondlayer.ucp.profile import load_merchants
        merchant = load_merchants().get(merchant_id)
        return merchant.domain if merchant is not None else None
    except (ImportError, OSError, ValueError, KeyError):
        return None  # profile discovery is part of trust establishment


def _verified_records(sku: Sku, records: list[SignedRecord], verify: Callable[[SignedRecord], bool] | None) -> list[SignedRecord]:
    if verify is None:
        return []
    issuer = _issuer_for(sku)
    if issuer is None:
        return []
    verified: list[SignedRecord] = []
    for signed in records:
        record = signed.record
        if record.sku_id not in (None, sku.sku_id) or record.issuer != issuer:
            continue
        try:
            if verify(signed):
                verified.append(signed)
        except Exception:
            continue  # a verifier error is not evidence
    return verified


def _record_resolution(constraint: Constraint, verified: list[SignedRecord]) -> tuple[bool, SignedRecord | None, str]:
    wanted = _wanted_benefit(constraint)
    if wanted is None:
        return False, None, _UNANSWERED_MARKER
    match = next((signed for signed in verified if signed.record.benefit_type is wanted), None)
    if match is None:
        return False, None, _UNANSWERED_MARKER
    return True, match, f"Verified {wanted.value} claim: {match.record.fact}."


def _dedupe_by_gtin(candidates: list[tuple[Proposal, float]]) -> list[Proposal]:
    """Collapse duplicate listings within one merchant, not competing offers.

    A GTIN identifies the same physical product across merchants, but those
    merchant offers may carry different verified benefits.  Keeping one offer
    per ``merchant + GTIN`` preserves that comparison while eliminating title
    spelling duplicates at a single merchant.
    """
    best: dict[str, tuple[Proposal, float]] = {}
    for proposal, score in candidates:
        gtin = proposal.sku.attributes.get("gtin")
        merchant = proposal.sku.attributes.get("merchant")
        merchant_key = str(merchant) if merchant else proposal.sku.sku_id
        key = f"{merchant_key}:gtin:{gtin}" if isinstance(gtin, str) and gtin else f"sku:{proposal.sku.sku_id}"
        current = best.get(key)
        if current is None or (-score, proposal.sku.shelf_price, proposal.sku.sku_id) < (-current[1], current[0].sku.shelf_price, current[0].sku.sku_id):
            best[key] = (proposal, score)
    return [item[0] for item in sorted(best.values(), key=lambda item: (-item[1], item[0].sku.shelf_price, item[0].sku.sku_id))]


def resolve(constraints: list[Constraint], skus: list[Sku], records: list[SignedRecord], *, signer: Signer | None = None, verify: Callable[[SignedRecord], bool] | None = None) -> list[Proposal]:
    """Resolve hard filters and ranked semantic evidence into cited proposals.

    Without an injected verifier, catalogue matches still work but record-backed
    clauses are marked unsatisfied; a non-empty signature is never enough.
    """
    verifier = verify or (signer.verify if signer is not None else None)
    candidates: list[tuple[Proposal, float]] = []
    for sku in skus:
        resolved: list[ResolvedConstraint] = []
        hard_failed, score = False, 0.0
        for constraint in constraints:
            if constraint.kind is ConstraintKind.HARD:
                satisfied, attribute, note = _hard_resolution(constraint, sku)
                resolved.append(ResolvedConstraint(constraint, satisfied, None, attribute, note))
                hard_failed = hard_failed or not satisfied
        if hard_failed:
            continue
        cited: list[SignedRecord] = []
        verified = _verified_records(sku, records, verifier)
        for constraint in constraints:
            if constraint.kind is ConstraintKind.HARD:
                continue
            if constraint.kind is ConstraintKind.SOFT:
                satisfied, attribute, note, points = _soft_resolution(constraint, sku)
                score += points
                resolved.append(ResolvedConstraint(constraint, satisfied, None, attribute, note))
                continue
            satisfied, record, note = _record_resolution(constraint, verified)
            if satisfied and record is not None:
                cited.append(record)
                score += 3.0
                resolved.append(ResolvedConstraint(constraint, True, record.record.record_id, None, note))
            else:
                resolved.append(ResolvedConstraint(constraint, False, None, None, note))
        unsatisfied = [item.constraint for item in resolved if not item.satisfied]
        unique_cited = list({record.record.record_id: record for record in cited}.values())
        candidates.append((Proposal(sku, resolved, unsatisfied, unique_cited), score))
    return _dedupe_by_gtin(candidates)


class ConstraintInterpreter:
    """Protocol-friendly interpreter with optional, fail-closed trust injection."""

    parse = staticmethod(parse)

    def __init__(self, signer: Signer | None = None, *, verify: Callable[[SignedRecord], bool] | None = None) -> None:
        self._signer = signer
        self._verify = verify

    def resolve(self, constraints: list[Constraint], skus: list[Sku], records: list[SignedRecord]) -> list[Proposal]:
        return resolve(constraints, skus, records, signer=self._signer, verify=self._verify)
