"""``POST /{merchant}/ucp/checkout`` -- the order confirmation that binds its proof.

FPT's desired outcome ends with step 5, *"closing the loop through a seamless,
API-driven transaction"*. Until this route the merchant server stopped at
``catalog.*`` and ``intent.propose``: the agent could discover, compare and be
answered, but the chosen offer never became an order. This route turns the
agent's chosen offer into an order confirmation that **binds the verified
benefit records the agent relied on**, so the transaction carries proof of
what it includes. That is the loop-closing test the stage-1 spec names --
"whose checkout matched the quote": every record the agent cited while
comparing is re-judged here, on the merchant's side, and the ones that hold
are returned inside the order, as the same signed envelopes the catalogue
served.

**What the server can and cannot sign.** The server holds *only* public keys
(``keys/*.pub.json``); the merchant's private key is never on disk, by design
-- the records were signed out of band, and the whole verification story rests
on that. So the server **cannot mint a new signed order object**. Instead the
order carries (a) the merchant's already-signed record envelopes, which the
agent can re-verify against ``signing_keys[]`` in ``/.well-known/ucp`` exactly
as it did during discovery, and (b) a deterministic content hash as
``order_id`` -- SHA-256 over the canonical JSON of ``{merchant_id, items,
honoured record ids}``, so the same order from the same agent has the same id
and either party can recompute it from the confirmation alone. Proof rides the
records; the order is the container that names which ones.

**Payment is out of scope, and the response says so.** ``payment.status`` is
``out_of_scope``; the order status is ``confirmed_awaiting_payment``; no funds
move. Payment methods are a T&C fact the profile may declare, not something
this prototype implements. Declaring the ``dev.ucp.shopping.checkout``
capability while saying plainly what it does and does not do is more honest
than leaving the loop open.

**Stateless: the confirmation IS the artefact.** There is no order store.
An identical body yields an identical ``order_id``, and the response is the
complete record of what was confirmed. A real deployment would persist the
confirmation (and probably sign it with a key it *does* hold); this prototype
returns it and keeps nothing, because the demo must run from a fresh clone
with no secrets and no database.

**What is honoured, and why each answer is given.** A cited record id is
``honoured: true`` iff *all* of:

1. the merchant publishes it (``load_records`` -- an id the merchant has never
   heard of is "not published by this merchant");
2. it is signed (an unsigned claim is displayed on the catalogue and is never
   a commitment);
3. it has not expired (``expires_at``, read against the clock the same way
   ``bondlayer.records.signing`` reads it);
4. it verifies against the merchant's *own* public key (``verified_records``
   from ``bondlayer.ucp.intent`` -- the same gate the resolver sits behind);
5. it applies to at least one line item: ``sku_id`` equal, or ``None`` for
   merchant-wide, narrowed by ``fact["scope"]`` exactly as the valuation
   library narrows it (``_scope_of`` from ``effective_cost``, imported rather
   than re-implemented so the two can never disagree).

Each ``honoured_benefits`` entry names the failing test in plain words.
Nothing the agent did not cite is added: the order honours what was relied
upon, it does not upsell.

**What the merchant receives, and what it never does.** SKU ids, quantities,
the record ids the agent cited, and an optional opaque ``agent_ref``. It still
never receives the shopper's valuation policy, benefit weights, or the
cross-merchant comparison -- the body model forbids extra fields, so a
``shopper_policy`` or ``values_aud`` key is a 422, not a silently ignored
leak. Ranking against the shopper's policy stayed agent-side; this is the
order that ranking produced.

``honoured_benefits`` and ``extensions`` are present iff
``org.bondlayer.benefit_value`` survived negotiation and absent otherwise --
the same gate as on ``catalog.search``. The control merchant never declares
the extension, so its checkout is a plain UCP order: line items, subtotal,
payment status, nothing else. Same route, same builder.

No network call, no model call, no clock in the order id.

The server module includes this router and this module needs the server's
seeded state, so the two would be circular at import time. Like ``intent``,
this module fetches the server at call time (``_server()``).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from bondlayer.records.serialise import signed_from_json
from bondlayer.types import SignedRecord, Sku
from bondlayer.ucp.capabilities import BENEFIT_VALUE, CHECKOUT
from bondlayer.ucp.intent import verified_records
from bondlayer.ucp.profile import Merchant
from bondlayer.valuation.effective_cost import _gating, _scope_of

router = APIRouter(tags=["ucp"])

CURRENCY = "AUD"
STATUS_CONFIRMED = "confirmed_awaiting_payment"
PAYMENT_NOTE = (
    "Payment methods are declared in the merchant's terms and not implemented "
    "in this prototype; no funds move."
)

#: The wording of each refusal, in one place so the tests and the README
#: quote the same sentence.
REASON_NOT_PUBLISHED = "not published by this merchant"
REASON_UNSIGNED = "unsigned claim: displayed on the catalogue, never a commitment"
REASON_UNVERIFIED = (
    "signature does not verify against this merchant's published signing key"
)


class LineItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku_id: str = Field(min_length=1)
    quantity: int = Field(ge=1)


class CheckoutRequest(BaseModel):
    """The body. ``extra="forbid"`` is the privacy boundary: a shopper's
    valuation policy has no field to arrive in, so it cannot arrive."""

    model_config = ConfigDict(extra="forbid")

    items: list[LineItemIn] = Field(min_length=1)
    cited_record_ids: list[str] = Field(default_factory=list)
    agent_ref: str | None = None


def _server():
    """The merchant server's seeded state, fetched at call time.

    ``server`` includes this router, so a top-level import here would be
    circular and which module loaded first would depend on the caller.
    """
    from bondlayer.ucp import server

    return server


# --- money -------------------------------------------------------------------


def _money(amount: Decimal) -> dict:
    return {"amount": str(amount), "currency": CURRENCY}


def _line_item(sku: Sku, quantity: int) -> dict:
    return {
        "sku_id": sku.sku_id,
        "title": sku.title,
        "quantity": quantity,
        "unit_price": _money(sku.shelf_price),
        "line_total": _money(sku.shelf_price * quantity),
    }


# --- stock ---------------------------------------------------------------------


def _available(sku: Sku) -> int | None:
    """Units on hand when the listing says so; ``None`` when it does not.

    A stock attribute that is absent or not numeric is *no information*, and
    no information never blocks an order -- the merchant that published no
    stock figure has not told us it is out.
    """
    raw = sku.attributes.get("stock") if isinstance(sku.attributes, dict) else None
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float, Decimal)):
        return int(raw)
    try:
        return int(Decimal(str(raw).strip()))
    except (ValueError, ArithmeticError):
        return None


# --- the honouring judgement --------------------------------------------------


def _applies_to(signed: SignedRecord, skus: list[Sku]) -> Sku | None:
    """The first line item this record binds to, or ``None``.

    Same two tests as the valuation library's ``_binds``: the record's own
    ``sku_id`` (``None`` = merchant-wide), then ``fact["scope"]`` against the
    listing's category, through the very same ``_scope_of``.
    """
    record = signed.record
    scope = _scope_of(record)
    for sku in skus:
        if record.sku_id is not None and record.sku_id != sku.sku_id:
            continue
        if scope is not None and sku.category.lower() not in scope:
            continue
        return sku
    return None


def _why_not_applicable(signed: SignedRecord, skus: list[Sku]) -> str:
    record = signed.record
    if record.sku_id is not None and all(record.sku_id != s.sku_id for s in skus):
        return f"record applies to sku {record.sku_id!r}, which is not a line item of this order"
    categories = sorted({s.category for s in skus})
    covered = ", ".join(f"{c!r}" for c in categories)
    return f"record scope {record.fact.get('scope')!r} does not cover category {covered}"


def judge(
    cited_record_ids: list[str],
    skus: list[Sku],
    *,
    published: list[dict],
    parsed: list[SignedRecord],
    verified_ids: frozenset[str],
    now: datetime | None = None,
) -> list[dict]:
    """One verdict per distinct cited id, in the order the agent cited them.

    Pure: everything it judges against is handed in, so a test can pin the
    "expired" branch by passing a ``now`` after the record's window without
    a record that has actually expired in ``data/``. ``now`` defaults to the
    clock exactly as ``bondlayer.records.signing.ES256Signer.verify`` reads it.
    """
    current = now if now is not None else datetime.now(timezone.utc)
    envelopes = {e["record"]["record_id"]: e for e in published}
    typed = {r.record.record_id: r for r in parsed}

    verdicts: list[dict] = []
    seen: set[str] = set()
    for record_id in cited_record_ids:
        if record_id in seen:
            continue
        seen.add(record_id)
        verdict = {"record_id": record_id, "honoured": False, "reason": "", "sku_id": None}
        envelope = envelopes.get(record_id)
        signed = typed.get(record_id)
        if envelope is None or signed is None:
            verdict["reason"] = REASON_NOT_PUBLISHED
        elif not envelope["signed"]:
            verdict["reason"] = REASON_UNSIGNED
        elif signed.record.expires_at is not None and signed.record.expires_at <= current:
            verdict["reason"] = (
                f"expired: the record's window closed at "
                f"{signed.record.expires_at.isoformat()}"
            )
        elif record_id not in verified_ids:
            verdict["reason"] = REASON_UNVERIFIED
        elif (sku := _applies_to(signed, skus)) is None:
            verdict["reason"] = _why_not_applicable(signed, skus)
        else:
            verdict["honoured"] = True
            verdict["sku_id"] = sku.sku_id
            how = (
                "merchant-wide record" if signed.record.sku_id is None
                else "record names this sku"
            )
            reason = (
                f"verified against the merchant's published signing key and "
                f"applies to {sku.sku_id} ({how})"
            )
            gating = _gating(list(signed.record.conditions))
            if gating:
                reason += f"; subject to conditions: {', '.join(gating)}"
            verdict["reason"] = reason
        verdicts.append(verdict)
    return verdicts


# --- the order id --------------------------------------------------------------


def order_id(merchant_id: str, items: list[LineItemIn], honoured_ids: list[str]) -> str:
    """SHA-256 (first 16 hex) over canonical JSON of what the order binds.

    Items are sorted by ``(sku_id, quantity)`` and record ids are sorted, so
    two agents describing the same order in a different order agree on the
    id. No timestamp: the id names the *content*, not the moment.
    """
    canonical = {
        "merchant_id": merchant_id,
        "items": sorted(
            ({"sku_id": i.sku_id, "quantity": i.quantity} for i in items),
            key=lambda d: (d["sku_id"], d["quantity"]),
        ),
        "honoured_record_ids": sorted(honoured_ids),
    }
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# --- the route --------------------------------------------------------------------


@router.post("/{merchant_id}/ucp/checkout")
def checkout(
    merchant_id: str,
    body: CheckoutRequest,
    ucp_agent: str | None = Header(default=None, alias="UCP-Agent"),
) -> dict:
    srv = _server()
    merchant: Merchant = srv._merchant(merchant_id)
    negotiated = srv._negotiated(merchant, ucp_agent)
    if CHECKOUT not in negotiated:
        raise HTTPException(406, "checkout was not negotiated")

    by_id = {s.sku_id: s for s in srv._catalog[merchant.id]}
    lines: list[tuple[Sku, int]] = []
    for item in body.items:
        sku = by_id.get(item.sku_id)
        if sku is None:
            raise HTTPException(404, f"unknown sku {item.sku_id!r}")
        available = _available(sku)
        if available is not None and available < item.quantity:
            # A plain JSONResponse rather than HTTPException(detail=dict): the
            # agent gets `sku_id` and `available` at the top level, next to
            # `detail`, instead of nested one layer down.
            return JSONResponse(
                status_code=409,
                content={"detail": "insufficient stock", "sku_id": sku.sku_id,
                         "available": available},
            )
        lines.append((sku, item.quantity))
    skus = [sku for sku, _ in lines]

    # Judged on every call, whether or not the agent can see the result: the
    # order id binds the honoured set, so the plain-UCP agent's id is the same
    # id the extension-aware agent would get for the same body.
    verdicts = judge(
        body.cited_record_ids,
        skus,
        published=srv._records.get(merchant.id, []),
        parsed=[signed_from_json(entry) for entry in srv._records.get(merchant.id, [])],
        verified_ids=frozenset(r.record.record_id for r in verified_records(merchant)),
    )
    honoured_ids = [v["record_id"] for v in verdicts if v["honoured"]]

    subtotal = sum((sku.shelf_price * qty for sku, qty in lines), Decimal("0"))
    response: dict = {
        "business": {"id": merchant.id, "name": merchant.display_name},
        # Echo the active set so the agent knows what is live -- same as every
        # other route on this server.
        "active_capabilities": negotiated.active,
        "order": {
            "order_id": order_id(merchant.id, body.items, honoured_ids),
            "status": STATUS_CONFIRMED,
            "line_items": [_line_item(sku, qty) for sku, qty in lines],
            "subtotal": _money(subtotal),
            "payment": {"status": "out_of_scope", "note": PAYMENT_NOTE},
            "agent_ref": body.agent_ref,
        },
    }
    if BENEFIT_VALUE in negotiated:
        # Present iff the benefit extension survived negotiation; absent
        # otherwise. The envelopes are the same objects catalog.search serves,
        # re-verifiable against signing_keys[] in the profile.
        envelopes = {e["record"]["record_id"]: e for e in srv._records.get(merchant.id, [])}
        response["honoured_benefits"] = verdicts
        response["extensions"] = {
            BENEFIT_VALUE: [envelopes[rid] for rid in honoured_ids]
        }
    return response
