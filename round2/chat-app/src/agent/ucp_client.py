"""The agent's side of the protocol: declare, fetch, verify.

**This module is where the BondLayer switch lives, and it is the only place.**

"Off" is not a different code path, a flag in the response builder, or a second
server. It is this agent declining to declare one capability in its
``UCP-Agent`` header, after which ordinary UCP negotiation on the merchant side
prunes the extension. Same route, same builder, same fan-out, same merchants.

    on  -> "...catalog.search;v=2026-04-08, org.bondlayer.benefit_value;v=draft"
    off -> "...catalog.search;v=2026-04-08"

Everything else about the two runs is identical. That is the only reason the
comparison is admissible evidence rather than a demo trick.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import httpx

CHAT_APP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(CHAT_APP.parent))

from valuation.signing import verify_benefit_record
from valuation.types import BenefitRecord, BenefitType, VerificationKey

MERCHANT_BASE_URL = "http://127.0.0.1:8000"
MERCHANTS = ["voltway", "citycircuit", "northgear"]

PROTOCOL_VERSION = "2026-04-08"
CATALOG_SEARCH = "dev.ucp.shopping.catalog.search"
CATALOG_LOOKUP = "dev.ucp.shopping.catalog.lookup"
IDENTITY_LINKING = "dev.ucp.common.identity_linking"
BENEFIT_VALUE = "org.bondlayer.benefit_value"


def agent_header(bondlayer_enabled: bool) -> str:
    """What this agent declares it can understand.

    The switch, in full. Nothing else in the system branches on it.
    """
    declared = [
        f"{CATALOG_SEARCH};v={PROTOCOL_VERSION}",
        f"{CATALOG_LOOKUP};v={PROTOCOL_VERSION}",
        f"{IDENTITY_LINKING};v={PROTOCOL_VERSION}",
    ]
    if bondlayer_enabled:
        declared.append(f"{BENEFIT_VALUE};v=draft")
    return ", ".join(declared)


@dataclass
class VerifiedRecord:
    """One published record, after the agent has checked it itself."""

    merchant: str
    issuer: str
    benefit_type: str
    terms: dict
    #: Only set where the benefit genuinely is money the shopper does not pay.
    #: ``None`` means "not a monetary benefit", never "worthless".
    cash_value_aud: float | None
    #: Set where the benefit has a dollar figure that is **not** fungible cash --
    #: store credit, spendable at one merchant and expiring. The agent is
    #: expected to discount it and say by how much; it is never added to cash.
    ceiling_aud: float | None
    source_span: str
    key_id: str | None
    signed: bool
    verified: bool
    #: verified_monetary | verified_restricted | verified_fact
    #: | ineligible | shopper_mismatch | unverified
    state: str
    reason: str
    #: Percentage benefits sign a rate, not an amount. Kept so the evidence log
    #: can show that the dollar figure was derived from a signed rate and a
    #: price on the wire, rather than asserted by anyone.
    rate_pct: float | None = None
    form: str | None = None


@dataclass
class Offer:
    """One listing, with whatever the merchant published alongside it."""

    merchant: str
    sku_id: str
    title: str
    category: str
    model_key: str
    shelf_price_aud: float
    availability: str
    description: str
    records: list[VerifiedRecord] = field(default_factory=list)


@dataclass
class MerchantExchange:
    """The full record of one HTTP exchange, for the evidence log."""

    merchant: str
    url: str
    request_header: str
    status_code: int
    active_capabilities: dict
    pruned_capabilities: dict
    extension_served: bool
    product_count: int
    record_count: int
    #: What this merchant made of the shopper id, in its own words. Each
    #: merchant answers separately: the same shopper is a seven-order Circle
    #: member at one and a stranger at the next.
    shopper: dict = field(default_factory=dict)
    error: str | None = None


def _verification_keys(client: httpx.Client, merchant: str) -> dict[str, VerificationKey]:
    """Fetch ``signing_keys[]`` from the merchant's own profile.

    The agent resolves a record's ``key_id`` here and nowhere else. A record
    whose ``kid`` does not resolve is ``key_not_found`` and earns nothing --
    it is not quietly trusted.
    """
    try:
        response = client.get(f"{MERCHANT_BASE_URL}/{merchant}/.well-known/ucp", timeout=5)
        if response.status_code != 200:
            return {}
        keys = response.json().get("signing_keys", [])
    except httpx.HTTPError:
        return {}

    resolved: dict[str, VerificationKey] = {}
    for jwk in keys:
        kid = jwk.get("kid")
        if not kid:
            continue
        resolved[kid] = VerificationKey(
            kid=kid,
            kty=jwk.get("kty", "EC"),
            crv=jwk.get("crv", "P-256"),
            x=jwk["x"],
            y=jwk["y"],
        )
    return resolved


def _threshold_unmet(terms: dict, shelf_price_aud: float) -> str | None:
    """Whether the listing fails a condition the record itself sets out.

    A signature proves who made an offer. It says nothing about whether the
    offer applies, and the difference is the whole point of this function.
    NorthGear's "New members save 20%" verifies perfectly and then asks for a
    $150 minimum on a catalogue whose dearest item is $109.99 -- so it is worth
    exactly nothing here, and the reason has to be legible rather than a silent
    drop. This is how the "20% OFF" banner actually behaves; we neither hide it
    nor credit it.
    """
    minimum = terms.get("min_spend_aud")
    if minimum is not None and shelf_price_aud < float(minimum):
        return (
            f"min_spend_not_met: ${shelf_price_aud:.2f} is below the "
            f"${float(minimum):.2f} minimum this offer requires"
        )
    free_over = terms.get("free_over_aud")
    if free_over is not None and shelf_price_aud < float(free_over):
        return (
            f"threshold_not_met: ${shelf_price_aud:.2f} is below the "
            f"${float(free_over):.2f} this fee is waived over"
        )
    return None


def _verify(
    envelope: dict,
    keys: dict[str, VerificationKey],
    merchant: str,
    shelf_price_aud: float,
    linked_shopper_id: str | None,
) -> VerifiedRecord:
    """Check one record's signature against the merchant's published key, then
    check whether it actually applies to this listing and this shopper.

    Six outcomes, and the log has to keep them distinct:

    - **verified_monetary**    signature checks out and the benefit is cash the
      shopper does not pay -> the agent can treat it as money off
    - **verified_restricted**  signature checks out and the benefit has a dollar
      figure that is *not* fungible cash -- store credit, redeemable at one
      merchant and expiring. It gets a ceiling, never a cash value, and the agent
      must discount it and disclose the haircut
    - **verified_fact**        signature checks out, the benefit is a fact with no
      honest dollar figure -> true, citable, and the agent decides what it is worth
    - **ineligible**           signature checks out and the offer's own condition
      fails on this listing -> displayed with the arithmetic, credited nothing
    - **shopper_mismatch**     signature checks out over a *different* shopper's
      id -> a promotion cannot be lifted onto whoever is holding it
    - **unverified**           no signature, or one that does not check out ->
      displayed, never cited, and it must not move the ranking

    Note what is deliberately *not* here: any conversion of a fact into a price.
    A 24-month warranty is not $18. Turning it into $18 and subtracting it from
    the shelf price invents a number the merchant never offered.

    Percentage benefits are the one place a dollar figure is *computed*, and it
    is worth being precise about why that is not the same sin. The merchant signs
    a rate and a form; the price is on the wire in the same response. 5% of
    $109.99 is arithmetic over two things the merchant published, not a valuation
    we invented -- and ``form`` decides which column it lands in.
    """
    body = envelope.get("record", {})
    signature = envelope.get("signature")
    key_id = envelope.get("key_id")
    terms = body.get("terms", {})
    cash = float(body.get("value_aud", 0.0)) or None
    common = {
        "merchant": merchant,
        "issuer": body.get("merchant_id", merchant),
        "benefit_type": body.get("benefit_type", "unknown"),
        "terms": terms,
        "cash_value_aud": cash,
        "ceiling_aud": None,
        "source_span": body.get("source_span", ""),
        "key_id": key_id,
        "rate_pct": terms.get("rate_pct"),
        "form": terms.get("form"),
    }

    if not signature or not key_id:
        return VerifiedRecord(
            **common, signed=False, verified=False, state="unverified",
            reason="no signature — displayed, never cited",
        )

    key = keys.get(key_id)
    if key is None:
        return VerifiedRecord(
            **common, signed=True, verified=False, state="unverified",
            reason=f"key_not_found: {key_id} does not resolve in signing_keys[]",
        )

    try:
        record = BenefitRecord(
            merchant_id=body["merchant_id"],
            shopper_id=body["shopper_id"],
            product_id=body["product_id"],
            benefit_type=BenefitType(body["benefit_type"]),
            value_aud=float(body.get("value_aud", 0.0)),
            value_ceiling_aud=float(body.get("value_ceiling_aud", 0.0)),
            created_at=body["created_at"],
            source_span=body["source_span"],
            merchant_key_id=body["merchant_key_id"],
            terms=body.get("terms", {}),
            signature=signature,
            canonical_json=envelope.get("canonical_json"),
        )
    except (KeyError, ValueError) as exc:
        return VerifiedRecord(
            **common, signed=True, verified=False, state="unverified",
            reason=f"malformed record: {exc}",
        )

    if not verify_benefit_record(record, key):
        return VerifiedRecord(
            **common, signed=True, verified=False, state="unverified",
            reason="signature did not verify — displayed, never cited",
        )

    # From here the signature is good. Everything below is about whether the
    # offer applies, which a signature never establishes.

    scope = body.get("shopper_id")
    if scope not in (None, "*", linked_shopper_id):
        return VerifiedRecord(
            **common, signed=True, verified=True, state="shopper_mismatch",
            reason=f"shopper_mismatch: signed for {scope!r}, linked shopper is "
            f"{linked_shopper_id!r} — a promotion is not transferable",
        )

    unmet = _threshold_unmet(terms, shelf_price_aud)
    if unmet:
        return VerifiedRecord(
            **{**common, "cash_value_aud": None}, signed=True, verified=True,
            state="ineligible",
            reason=f"verified, and it does not apply here — {unmet}",
        )

    rate = terms.get("rate_pct")
    if rate is not None:
        amount = round(float(rate) / 100.0 * shelf_price_aud, 2)
        # Store credit is not money. It is spendable at one merchant, it expires,
        # and it is worth nothing to a shopper who does not come back. Putting it
        # in the cash column would overstate it by exactly the amount of that
        # risk, so it gets a ceiling and the agent owes a disclosed haircut.
        if terms.get("form") == "store_credit":
            return VerifiedRecord(
                **{**common, "cash_value_aud": None, "ceiling_aud": amount},
                signed=True, verified=True, state="verified_restricted",
                reason=f"verified — {rate:g}% of ${shelf_price_aud:.2f} is "
                f"${amount:.2f}, but as "
                f"{terms.get('redeemable_at', 'merchant-restricted')} credit"
                + (
                    f" expiring in {terms['expires_months']} months"
                    if terms.get("expires_months")
                    else ""
                )
                + ". A ceiling, not cash: discount it and say by how much",
            )
        return VerifiedRecord(
            **{**common, "cash_value_aud": amount, "ceiling_aud": amount},
            signed=True, verified=True, state="verified_monetary",
            reason=f"verified — {rate:g}% of ${shelf_price_aud:.2f} is "
            f"${amount:.2f} off the price, computed from a signed rate and the "
            f"merchant's own listed price",
        )

    if cash is not None:
        return VerifiedRecord(
            **{**common, "ceiling_aud": cash}, signed=True, verified=True,
            state="verified_monetary",
            reason="verified against published JWK — a fee the shopper does not pay",
        )

    return VerifiedRecord(
        **common, signed=True, verified=True, state="verified_fact",
        reason="verified against published JWK — a fact, not a price; "
        "the agent decides what it is worth",
    )


def fan_out(
    query: str,
    bondlayer_enabled: bool,
    shopper_id: str | None = None,
) -> tuple[list[Offer], list[MerchantExchange]]:
    """Query every merchant, identically, over real UCP.

    The fan-out is the same in both switch states: same merchants, same order,
    same query. Only the declared header differs. That is what kills the
    objection that the baseline lost because the agent called fewer merchants.

    ``shopper_id`` is ``None`` when the shopper withheld consent, and then it is
    simply never put on the wire. Nothing downstream needs a privacy branch: the
    merchant has no id to resolve, only ``shopper_id: "*"`` records match, and
    the shopper-specific promotions are absent from the response rather than
    filtered out of the display.
    """
    header = agent_header(bondlayer_enabled)
    offers: list[Offer] = []
    exchanges: list[MerchantExchange] = []

    with httpx.Client() as client:
        for merchant in MERCHANTS:
            url = f"{MERCHANT_BASE_URL}/{merchant}/ucp/catalog/search"
            try:
                params = {"q": query}
                if shopper_id:
                    params["shopper_id"] = shopper_id
                response = client.get(
                    url, params=params, headers={"UCP-Agent": header}, timeout=10
                )
            except httpx.HTTPError as exc:
                exchanges.append(
                    MerchantExchange(
                        merchant=merchant, url=url, request_header=header, status_code=0,
                        active_capabilities={}, pruned_capabilities={},
                        extension_served=False, product_count=0, record_count=0,
                        error=str(exc),
                    )
                )
                continue

            if response.status_code != 200:
                exchanges.append(
                    MerchantExchange(
                        merchant=merchant, url=str(response.url), request_header=header,
                        status_code=response.status_code, active_capabilities={},
                        pruned_capabilities={}, extension_served=False,
                        product_count=0, record_count=0, error=response.text[:200],
                    )
                )
                continue

            body = response.json()
            extension = body.get("extensions", {}).get(BENEFIT_VALUE, [])
            by_sku = {block["sku_id"]: block for block in extension}
            keys = _verification_keys(client, merchant) if extension else {}
            # Whether *this* merchant recognised the id. An agent-side claim of
            # membership is worth nothing; only the merchant can say.
            identity = body.get("shopper", {})
            linked = identity.get("shopper_id") if identity.get("linked") else None

            record_total = 0
            for product in body.get("products", []):
                block = by_sku.get(product["id"], {})
                price = float(product["price"]["amount"])
                verified = [
                    _verify(e, keys, merchant, price, linked)
                    for e in block.get("records", [])
                ]
                record_total += len(verified)
                offers.append(
                    Offer(
                        merchant=merchant,
                        sku_id=product["id"],
                        title=product["title"],
                        category=product["category"],
                        model_key=product.get("model_key", ""),
                        shelf_price_aud=price,
                        availability=product.get("availability", "unknown"),
                        description=product.get("description", ""),
                        records=verified,
                    )
                )

            exchanges.append(
                MerchantExchange(
                    merchant=merchant, url=str(response.url), request_header=header,
                    status_code=response.status_code,
                    active_capabilities=body.get("active_capabilities", {}),
                    pruned_capabilities=body.get("pruned_capabilities", {}),
                    extension_served=bool(extension),
                    product_count=len(body.get("products", [])),
                    record_count=record_total,
                    shopper=identity,
                )
            )

    return offers, exchanges


def link_identity(shopper_id: str, consent: bool, bondlayer_enabled: bool) -> list[dict]:
    """Consent-gated identity over UCP, per merchant."""
    header = agent_header(bondlayer_enabled)
    out = []
    with httpx.Client() as client:
        for merchant in MERCHANTS:
            url = f"{MERCHANT_BASE_URL}/{merchant}/ucp/identity/link"
            try:
                response = client.post(
                    url,
                    json={"shopper_id": shopper_id, "consent": consent},
                    headers={"UCP-Agent": header},
                    timeout=5,
                )
                out.append(
                    {"merchant": merchant, "status_code": response.status_code, **response.json()}
                )
            except (httpx.HTTPError, ValueError) as exc:
                out.append({"merchant": merchant, "status_code": 0, "error": str(exc)})
    return out
