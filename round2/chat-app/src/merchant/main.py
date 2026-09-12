"""The merchant service: one server, three merchants, one code path.

The correctness property this file exists to hold:

    An agent **with** the benefit extension and an agent **without** it both
    get a valid response from the same route, built by the same function. The
    control merchant is this server with the extension absent from its
    manifest -- not a second implementation, and not a flag inside the builder.

If that stops being true, the before/after comparison proves nothing and the
headline result is worthless.

Run it::

    python -m uvicorn src.merchant.main:app --host 127.0.0.1 --port 8000 --reload
"""

from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .capabilities import (
    BENEFIT_VALUE,
    BENEFIT_VALUE_EXTENDS,
    CATALOG_LOOKUP,
    CATALOG_SEARCH,
    IDENTITY_LINKING,
    PROTOCOL_VERSION,
    Negotiated,
    negotiate,
    parse_agent_header,
)
from .seed import Merchant, Sku, load_catalog, load_merchants, load_records, signing_keys

app = FastAPI(
    title="BondLayer UCP merchant service",
    description="Three merchants, one code path, real capability negotiation.",
    version="0.2.0",
)

# The UI reaches these routes through the Vite proxy, so this only matters for
# direct calls. Origins carry a scheme; a bare host never matches.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8001",
        "http://127.0.0.1:8001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_merchants: dict[str, Merchant] = {}
_catalog: dict[str, list[Sku]] = {}
_records: dict[str, list[dict]] = {}


@app.on_event("startup")
def seed() -> None:
    _merchants.update(load_merchants())
    _catalog.update(load_catalog())
    for mid in _merchants:
        _records[mid] = load_records(mid)


def _merchant(merchant_id: str) -> Merchant:
    if merchant_id not in _merchants:
        raise HTTPException(404, f"unknown merchant {merchant_id!r}")
    return _merchants[merchant_id]


def _negotiated(merchant: Merchant, ucp_agent: str | None) -> Negotiated:
    return negotiate(merchant.capabilities, parse_agent_header(ucp_agent))


def _product(sku: Sku) -> dict:
    """A plain UCP catalogue object. No benefit data reaches this function."""
    return {
        "id": sku.sku_id,
        "title": sku.title,
        "category": sku.category,
        "model_key": sku.model_key,
        "gtin": sku.gtin,
        "price": {"amount": f"{sku.shelf_price_aud:.2f}", "currency": "AUD"},
        "availability": "in_stock" if sku.in_stock else "out_of_stock",
        "description": sku.description,
    }


def _records_for(merchant: Merchant, sku: Sku) -> list[dict]:
    """Published records that apply to one listing.

    ``product_id`` of ``"*"`` means the record applies to the whole merchant --
    a returns window is a property of the retailer, not of one charger -- so
    those attach to every listing.

    Unsigned records are served and flagged, never filtered out here. Deciding
    what an unsigned claim is worth is the agent's job, not the wire's.
    """
    out = []
    for envelope in _records.get(merchant.id, []):
        target = envelope["record"].get("product_id")
        if target in (None, "*", sku.sku_id):
            out.append(envelope)
    return out


def _respond(merchant: Merchant, skus: list[Sku], negotiated: Negotiated) -> dict:
    """The single response builder. There is no second one.

    Note what is *not* here: any test of the merchant's role, name or manifest.
    The extension block appears when the extension survived negotiation, and for
    no other reason. That is what makes graceful degradation structural rather
    than conditional.
    """
    body: dict = {
        "business": {
            "id": merchant.id,
            "name": merchant.display_name,
            "domain": merchant.domain,
        },
        # Echo the active set so the agent knows what is live rather than
        # inferring it from what is missing.
        "active_capabilities": negotiated.active,
        "pruned_capabilities": negotiated.pruned,
        "products": [_product(s) for s in skus],
    }
    if BENEFIT_VALUE in negotiated:
        body["extensions"] = {
            BENEFIT_VALUE: [
                {
                    "sku_id": s.sku_id,
                    "issuer": merchant.domain,
                    "records": _records_for(merchant, s),
                }
                for s in skus
            ]
        }
    return body


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "merchant", "merchants": sorted(_merchants)}


@app.get("/merchants")
def merchants() -> dict:
    return {
        "merchants": [
            {"id": m.id, "name": m.display_name, "role": m.role} for m in _merchants.values()
        ]
    }


@app.get("/{merchant_id}/.well-known/ucp")
def profile(merchant_id: str) -> dict:
    """The document an agent reads before anything else.

    If ``signing_keys[]`` is not reachable and correct, every signature we
    publish is unverifiable and the pitch is an assertion rather than a
    demonstration.
    """
    merchant = _merchant(merchant_id)
    caps = []
    for cap in merchant.capabilities:
        entry: dict = {"name": cap.name, "versions": list(cap.versions)}
        if cap.is_extension:
            entry["extends"] = list(cap.extends)
            entry["spec"] = "https://bondlayer.example/spec/benefit_value"
            entry["schema"] = "https://bondlayer.example/schemas/benefit_value.json"
        caps.append(entry)

    return {
        "protocol_version": PROTOCOL_VERSION,
        "business": {
            "id": merchant.id,
            "name": merchant.display_name,
            "domain": merchant.domain,
        },
        "capabilities": caps,
        "signing_keys": signing_keys(merchant),
    }


@app.get("/{merchant_id}/ucp/catalog/search")
def catalog_search(
    merchant_id: str,
    q: str | None = Query(default=None),
    category: str | None = Query(default=None),
    max_price: float | None = Query(default=None),
    limit: int = Query(default=20, le=100),
    ucp_agent: str | None = Header(default=None, alias="UCP-Agent"),
) -> dict:
    merchant = _merchant(merchant_id)
    negotiated = _negotiated(merchant, ucp_agent)
    if CATALOG_SEARCH not in negotiated:
        raise HTTPException(406, "catalog.search was not negotiated")

    skus = _catalog.get(merchant_id, [])
    if category:
        skus = [s for s in skus if s.category == category.lower()]
    if max_price is not None:
        skus = [s for s in skus if s.shelf_price_aud <= max_price]
    if q:
        # Deliberately shallow: this is transport, not intelligence. Real
        # semantic matching is the interpreter's job.
        needles = [w for w in q.lower().split() if len(w) > 2]
        skus = [
            s
            for s in skus
            if not needles
            or any(n in f"{s.title} {s.description} {s.category}".lower() for n in needles)
        ]
    return _respond(merchant, skus[:limit], negotiated)


@app.get("/{merchant_id}/ucp/catalog/lookup")
def catalog_lookup(
    merchant_id: str,
    sku_id: str = Query(...),
    ucp_agent: str | None = Header(default=None, alias="UCP-Agent"),
) -> dict:
    """The call an agent already makes while comparing merchants -- which is
    exactly why the benefit extension rides it."""
    merchant = _merchant(merchant_id)
    negotiated = _negotiated(merchant, ucp_agent)
    if CATALOG_LOOKUP not in negotiated:
        raise HTTPException(406, "catalog.lookup was not negotiated")

    matches = [s for s in _catalog.get(merchant_id, []) if s.sku_id == sku_id]
    if not matches:
        raise HTTPException(404, f"unknown sku {sku_id!r}")
    return _respond(merchant, matches, negotiated)


class IdentityLink(BaseModel):
    shopper_id: str
    consent: bool = False


@app.post("/{merchant_id}/ucp/identity/link")
def identity_link(
    merchant_id: str,
    body: IdentityLink,
    ucp_agent: str | None = Header(default=None, alias="UCP-Agent"),
) -> dict:
    """Consent-gated shopper identity.

    Without consent this returns nothing about the shopper and says so. The
    gate is a feature of the demo, not a formality to click past.
    """
    merchant = _merchant(merchant_id)
    negotiated = _negotiated(merchant, ucp_agent)
    if IDENTITY_LINKING not in negotiated:
        raise HTTPException(406, "identity_linking was not negotiated")
    if not body.consent:
        return {
            "linked": False,
            "reason": "consent_not_given",
            "active_capabilities": negotiated.active,
        }
    return {
        "linked": True,
        "shopper_id": body.shopper_id,
        "merchant": merchant.id,
        "active_capabilities": negotiated.active,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.merchant.main:app", host="127.0.0.1", port=8000, reload=True)
