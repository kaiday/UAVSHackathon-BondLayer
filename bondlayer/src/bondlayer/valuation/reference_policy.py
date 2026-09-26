"""The shopper the demo and the evaluation run are valued against.

A ``ShopperPolicy`` lives on the agent side and is never sent to a merchant, so
a real agent supplies its own. This one exists so that every number in the
pitch is reproducible from the repository: run the evaluation, get these
figures, and the arithmetic can be checked by anyone who disagrees with it.

**The values below are deliberately modest.** They are the cap on what any
merchant can earn, so setting them high would flatter us. A free 60-day returns
window is worth $40 to this shopper and not a dollar more, whatever a merchant's
ceiling says.

Trade-in is valued at **$0**: this shopper has no device to trade. That single
zero neutralises the largest ceiling either merchant publishes -- Voltway's
$700 laptop trade-in -- and it is the clearest demonstration of what the
shopper-side cap is for. A merchant cannot earn a credit for a benefit the
shopper will not use.
"""

from decimal import Decimal

from bondlayer.types import BenefitType, ShopperPolicy

#: Merchant id in the catalogue -> the domain its records are issued under.
#: A record signed by anyone else is not this listing's merchant, whatever it
#: signed. The control merchant is present and publishes nothing, which is the
#: point of it.
MERCHANT_DOMAINS = {
    "voltway": "voltway.example",
    "citycircuit": "citycircuit.example",
    "northgear": "northgear.example",
}

#: What the agent attests about this shopper. Eligibility conditions outside
#: this set are withheld, and the console shows them as withheld value.
#:
#: ``member`` is attested because joining Voltway Circle is free and joining
#: CityCircuit Rewards is free. ``paid_member`` is **not**: NorthGear Plus costs
#: $49 a year, and an agent comparing merchants at discovery time cannot credit
#: a benefit the shopper would have to buy first. NorthGear's own terms make the
#: same point -- "the $49 fee has to be earned back before Plus membership is
#: worth anything". Attesting it would be crediting NorthGear for money the
#: shopper has not spent.
ATTESTED_CONDITIONS = (
    "member",
    "resaleable",
    "order_over_75",
    "order_over_99",
)

#: Tokens above that a shopper has to *be* something to earn. The rest are
#: properties of the basket or of the returned item -- true of any shopper,
#: identified or not.
MEMBERSHIP_TOKENS = frozenset({"member", "paid_member"})

#: The attested tokens that owe nothing to identity. Derived rather than
#: restated, so extending ``ATTESTED_CONDITIONS`` cannot leave this behind.
SHOPPER_INDEPENDENT = tuple(
    c for c in ATTESTED_CONDITIONS if c not in MEMBERSHIP_TOKENS
)

#: Statuses that actually make someone a member. A merchant can know a shopper
#: without the shopper having joined anything -- ``prospect`` is a real answer
#: and it earns nothing. Being *recognised* and being a *member* are different
#: facts, and conflating them would hand every browsing shopper the member
#: price.
MEMBER_STATUSES = frozenset({"member", "paid_member"})


def attested_conditions(identity: dict) -> tuple[str, ...]:
    """What a merchant's answer about this shopper actually earns.

    ``identity`` is the ``shopper`` block a merchant returned
    (``ucp.membership.resolve_shopper``). Call this only when a merchant
    actually answered; with no identity in play the caller keeps using
    :data:`ATTESTED_CONDITIONS` unchanged, so an unidentified run is byte for
    byte the run it always was.

    Once an identity *is* in play, ``member`` stops being free. A shopper the
    merchant does not know earns no membership token, which is what makes a
    ``member_price`` record credit zero for a stranger -- the valuation's
    existing condition gate does the withholding, and this only decides what
    that gate is told.

    ``paid_member`` is the interesting one, and it is the honest resolution of
    the caveat written out above. The static tuple omits it because an agent
    comparing merchants cannot credit a benefit the shopper would have to buy
    first. A shopper who has **already** bought it is a different shopper, and
    the merchant is the only party who knows which one is asking. NorthGear's
    $49 Plus benefits stay withheld for everyone else.
    """
    status = identity.get("status") if identity.get("linked") else None
    if status not in MEMBER_STATUSES:
        return SHOPPER_INDEPENDENT
    earned = ["member"]
    if status == "paid_member":
        earned.append("paid_member")
    tier = identity.get("tier")
    if tier:
        earned.append(f"{tier}_tier")
    return SHOPPER_INDEPENDENT + tuple(earned)

#: What this shopper says each benefit is worth. Values claims are absent by
#: construction: they carry no ceiling and credit $0 however they are valued.
REFERENCE_SHOPPER_POLICY = ShopperPolicy(
    values_aud={
        BenefitType.FREE_RETURNS: Decimal("40.00"),
        BenefitType.WARRANTY: Decimal("60.00"),
        BenefitType.POINTS_EARN: Decimal("45.00"),
        BenefitType.MEMBER_PRICE: Decimal("55.00"),
        BenefitType.DELIVERY: Decimal("10.00"),
        BenefitType.TRADE_IN_CREDIT: Decimal("0.00"),
    },
    max_premium_over_cheapest_aud=Decimal("150.00"),
)
