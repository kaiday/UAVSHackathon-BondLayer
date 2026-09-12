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
    source_span: str
    key_id: str | None
    signed: bool
    verified: bool
    state: str  # verified_monetary | verified_fact | unverified
    reason: str


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


def _verify(envelope: dict, keys: dict[str, VerificationKey], merchant: str) -> VerifiedRecord:
    """Check one record's signature against the merchant's published key.

    Three outcomes, and the log has to keep them distinct:

    - **verified_monetary**  signature checks out, and the benefit is an amount of
      money the shopper does not pay -> the agent can treat it as cash
    - **verified_fact**      signature checks out, the benefit is a fact with no
      honest dollar figure -> true, citable, and the agent decides what it is worth
    - **unverified**         no signature, or one that does not check out ->
      displayed, never cited, and it must not move the ranking

    Note what is deliberately *not* here: any conversion of a fact into a price.
    A 24-month warranty is not $18. Turning it into $18 and subtracting it from
    the shelf price invents a number the merchant never offered.
    """
    body = envelope.get("record", {})
    signature = envelope.get("signature")
    key_id = envelope.get("key_id")
    cash = float(body.get("value_aud", 0.0)) or None
    common = {
        "merchant": merchant,
        "issuer": body.get("merchant_id", merchant),
        "benefit_type": body.get("benefit_type", "unknown"),
        "terms": body.get("terms", {}),
        "cash_value_aud": cash,
        "source_span": body.get("source_span", ""),
        "key_id": key_id,
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

    if cash is not None:
        return VerifiedRecord(
            **common, signed=True, verified=True, state="verified_monetary",
            reason="verified against published JWK — a fee the shopper does not pay",
        )

    return VerifiedRecord(
        **common, signed=True, verified=True, state="verified_fact",
        reason="verified against published JWK — a fact, not a price; "
        "the agent decides what it is worth",
    )


def fan_out(query: str, bondlayer_enabled: bool) -> tuple[list[Offer], list[MerchantExchange]]:
    """Query every merchant, identically, over real UCP.

    The fan-out is the same in both switch states: same merchants, same order,
    same query. Only the declared header differs. That is what kills the
    objection that the baseline lost because the agent called fewer merchants.
    """
    header = agent_header(bondlayer_enabled)
    offers: list[Offer] = []
    exchanges: list[MerchantExchange] = []

    with httpx.Client() as client:
        for merchant in MERCHANTS:
            url = f"{MERCHANT_BASE_URL}/{merchant}/ucp/catalog/search"
            try:
                response = client.get(
                    url, params={"q": query}, headers={"UCP-Agent": header}, timeout=10
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

            record_total = 0
            for product in body.get("products", []):
                block = by_sku.get(product["id"], {})
                verified = [_verify(e, keys, merchant) for e in block.get("records", [])]
                record_total += len(verified)
                offers.append(
                    Offer(
                        merchant=merchant,
                        sku_id=product["id"],
                        title=product["title"],
                        category=product["category"],
                        model_key=product.get("model_key", ""),
                        shelf_price_aud=float(product["price"]["amount"]),
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
