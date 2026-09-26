"""Indicative discovery value: verified records, shopper caps, Decimal arithmetic.

No model call anywhere in this file. Effective cost is arithmetic over records
that verified, and it returns its working -- the ``CreditedBenefit`` breakdown
is what the console renders and the agent cites, so every line carries the
reason it credited what it did, including when it credited nothing.

Four gates stand between a published record and a dollar off the shelf price,
and a record has to pass all four:

1. **Verification.** An unsigned or tampered record credits $0. It is still
   returned in the breakdown, because a claim that earns nothing has to be
   visible earning nothing.
2. **Applicability.** A record binds to the listing it names, or -- when it
   names none -- to the merchant that published it. A merchant-wide record on
   a listing whose merchant we cannot establish binds to nothing.
3. **Eligibility conditions.** An eligibility condition is withheld value, not
   free value: nothing is credited until the caller explicitly attests it, so a
   $49/year membership cannot quietly price itself at zero. ``conditions``
   carries two kinds of string and only one of them gates -- see
   :func:`_gating`.
4. **The shopper's own budget.** ``credited = min(merchant_ceiling, what the
   shopper says the benefit is worth)``, and that budget is per benefit type
   across the whole listing -- so splitting one benefit into five records
   credits it once, and inflating a ceiling cannot buy rank.
"""

import re
from decimal import Decimal

from bondlayer.types import (
    BenefitRecord,
    BenefitType,
    CreditedBenefit,
    EffectiveCost,
    ShopperPolicy,
    SignedRecord,
    Signer,
    Sku,
)


ZERO = Decimal("0")

#: An eligibility condition is a machine-checkable predicate: one lowercase
#: token, no spaces, the shape a caller can actually attest -- ``member``,
#: ``paid_member``, ``trade_in_device``. Everything else in ``conditions`` is a
#: term of use written for a human -- "Keep proof of purchase", "Item in
#: resaleable condition". Terms are published, displayed and never used to
#: withhold value, because no caller can attest a sentence and a merchant
#: should not be able to withhold a benefit by wording its terms at length.
_ELIGIBILITY_TOKEN = re.compile(r"^[a-z0-9][a-z0-9_.:-]*$")


def _gating(conditions: list[str]) -> list[str]:
    """The eligibility predicates in ``conditions``; terms of use are dropped."""
    return [c for c in conditions if _ELIGIBILITY_TOKEN.match(c)]


def _money(value: Decimal) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise ValueError("money must be a finite nonnegative Decimal")
    return value


def _scope_of(record: BenefitRecord) -> frozenset[str] | None:
    """Catalogue categories a record covers, or ``None`` when it covers all.

    ``fact["scope"]`` is prose a converter lifted out of policy text -- "laptop,
    phone", or "opened audio" -- so an entry is matched on its words rather than
    whole. Voltway's 24-month appliance cover and its 12-month laptop cover are
    two records of the same benefit type; without this both would attach to a
    laptop and the warranty would be credited against the wrong term.
    """
    scope = record.fact.get("scope")
    if scope is None:
        return None
    words = {
        word.strip().lower()
        for entry in str(scope).split(",")
        for word in entry.split()
        if word.strip()
    }
    return frozenset(words) or None


class DeterministicValuation:
    """Implements ValuationLibrary; verification is injected, never fetched.

    ``merchant_domains`` maps a catalogue merchant id to the domain its records
    are issued under. It is the caller's trust map: an issuer that is not in it
    is not this listing's merchant, whatever it signed.

    ``satisfied_conditions`` is what the caller attests about this shopper --
    membership of a free loyalty programme, a device to trade in, an order over
    a delivery threshold. Anything not in it is withheld.
    """

    def __init__(
        self, verifier: Signer, *, merchant_domains: dict[str, str] | None = None,
        satisfied_conditions: list[str] | tuple[str, ...] = (),
    ) -> None:
        self.verifier = verifier
        self.merchant_domains = dict(merchant_domains or {})
        self.satisfied_conditions = frozenset(satisfied_conditions)

    def _binds(self, record: BenefitRecord, sku: Sku) -> str | None:
        """``None`` when the record binds to this listing, else why it does not."""
        merchant = sku.attributes.get("merchant") if isinstance(sku.attributes, dict) else None

        if record.sku_id is not None:
            if record.sku_id != sku.sku_id:
                return "Record applies to another SKU; credited $0"
        elif merchant is None:
            return "Merchant-wide record on a listing that names no merchant; credited $0"

        # A listing that names its merchant must be matched by the issuer, for
        # SKU-scoped records too: a signature proves who wrote a claim, not that
        # the claim is about this shop's shelf.
        if merchant is not None and self.merchant_domains.get(str(merchant)) != record.issuer:
            return f"Issuer {record.issuer} is not this listing's merchant; credited $0"

        scope = _scope_of(record)
        if scope is not None and sku.category.lower() not in scope:
            return (
                f"Record scope {record.fact['scope']!r} does not cover "
                f"category {sku.category!r}; credited $0"
            )
        return None

    def effective_cost(
        self, sku: Sku, records: list[SignedRecord], policy: ShopperPolicy,
    ) -> EffectiveCost:
        shelf_price = _money(sku.shelf_price)
        for value in policy.values_aud.values():
            _money(value)
        credited = []
        seen = set()
        spent: dict[BenefitType, Decimal] = {}
        for signed in records:
            record = signed.record
            shopper_value = policy.values_aud.get(record.benefit_type, ZERO)
            ceiling = record.value_ceiling_aud
            valid_ceiling = ceiling is None or (
                isinstance(ceiling, Decimal) and ceiling.is_finite() and ceiling >= 0
            )
            merchant_value = ceiling if ceiling is not None and valid_ceiling else ZERO
            amount = ZERO
            identity = (record.issuer, record.record_id)
            unmet = [
                c for c in _gating(record.conditions)
                if c not in self.satisfied_conditions
            ]
            if not self.verifier.verify(signed):
                reason = "Unverified record; not citable; credited $0"
            elif not valid_ceiling:
                reason = "Invalid merchant ceiling; credited $0"
            elif (binding := self._binds(record, sku)) is not None:
                reason = binding
            elif identity in seen:
                reason = "Duplicate record; already considered; credited $0"
            else:
                seen.add(identity)
                if ceiling is None:
                    reason = "Verified and citable; no monetary ceiling; credited $0"
                elif unmet:
                    reason = (
                        "Verified and citable, but conditions not attested "
                        f"({', '.join(unmet)}); value withheld; credited $0"
                    )
                else:
                    budget = shopper_value - spent.get(record.benefit_type, ZERO)
                    remaining = budget if budget > ZERO else ZERO
                    amount = min(ceiling, remaining)
                    spent[record.benefit_type] = spent.get(record.benefit_type, ZERO) + amount
                    reason = (
                        f"Verified; min(merchant ${ceiling}, shopper ${remaining}) = ${amount}; "
                        "indicative, subject to conditions at checkout"
                    )
                    if remaining < shopper_value:
                        reason += (
                            f"; the shopper's ${shopper_value} "
                            f"{record.benefit_type.value} budget is already partly spent"
                        )
            credited.append(CreditedBenefit(
                record.record_id, record.benefit_type, merchant_value,
                shopper_value, amount, reason,
            ))
        total = sum((item.credited_aud for item in credited), ZERO)
        return EffectiveCost(
            sku.sku_id, shelf_price, credited, shelf_price - total, total_credited=total,
        )
