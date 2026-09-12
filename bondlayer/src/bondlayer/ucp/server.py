"""The merchant service: one server, three merchants, one code path.

The correctness property this file exists to hold:

    An agent **with** the benefit extension and an agent **without** it both
    get a valid response from the same route, built by the same function. The
    control merchant is this server with the extension absent from its
    manifest -- not a second implementation, not a flag inside the builder.

If that stops being true, the before/after comparison proves nothing and the
headline result is worthless (assumption A2).

Runs from seeded state with no outbound network call. Venue wifi is shared by
twenty teams.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, FastAPI, Header, HTTPException, Query

from bondlayer.adapters import CsvCatalogAdapter
from bondlayer.types import Sku
from bondlayer.ucp import onboard
from bondlayer.ucp.capabilities import (
    BENEFIT_VALUE,
    CATALOG_LOOKUP,
    CATALOG_SEARCH,
    Negotiated,
    negotiate,
    parse_agent_header,
)
from bondlayer.ucp.profile import (
    DATA,
    Merchant,
    build_profile,
    load_merchants,
)
from bondlayer.ucp.records import for_sku, load_records

CATALOG = DATA / "catalog" / "electronics.csv"

router = APIRouter(tags=["ucp"])

_merchants: dict[str, Merchant] = {}
_catalog: dict[str, list[Sku]] = {}
_records: dict[str, list[dict]] = {}


def seed() -> None:
    """Load merchants, catalogues and published records once, at start-up."""
    _merchants.update(load_merchants())
    for mid in _merchants:
        _catalog[mid] = CsvCatalogAdapter(CATALOG, merchant=mid).load()
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
        "price": {"amount": str(sku.shelf_price), "currency": "AUD"},
        "attributes": {
            k: (str(v) if isinstance(v, Decimal) else v)
            for k, v in sku.attributes.items()
            if k not in {"merchant", "model_key"}
        },
    }


def _benefit_block(merchant: Merchant, sku: Sku) -> dict:
    """The extension payload: Bach's published records, for this listing.

    ``issuer`` is the merchant **domain**, which is what a record's own
    ``issuer`` field carries and what ``signing_keys[]`` is published under.
    Merchant-wide records (``sku_id: null``) attach to every listing.

    Unsigned records are served, flagged ``signed: false``, and never filtered
    out here. Deciding what an unsigned claim is worth is the valuation
    library's job, not the wire's -- and the demo needs the unsigned claim to
    arrive so it can visibly earn nothing.
    """
    return {
        "sku_id": sku.sku_id,
        "issuer": merchant.domain,
        "records": for_sku(_records.get(merchant.id, []), sku.sku_id),
    }


def _respond(merchant: Merchant, skus: list[Sku], negotiated: Negotiated) -> dict:
    """The single response builder. There is no second one.

    Note what is *not* here: any test of the merchant's role, name or
    manifest. The extension block appears when the extension survived
    negotiation, and for no other reason. That is what makes graceful
    degradation structural rather than conditional.
    """
    body: dict = {
        "business": {"id": merchant.id, "name": merchant.display_name},
        # Echo the active set so the agent knows what is live rather than
        # inferring it from what is missing.
        "active_capabilities": negotiated.active,
        "products": [_product(s) for s in skus],
    }
    if BENEFIT_VALUE in negotiated:
        body["extensions"] = {
            BENEFIT_VALUE: [_benefit_block(merchant, s) for s in skus]
        }
    return body


@router.get("/{merchant_id}/.well-known/ucp")
def profile(merchant_id: str) -> dict:
    return build_profile(_merchant(merchant_id))


@router.get("/{merchant_id}/ucp/catalog/search")
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

    skus = _catalog[merchant_id]
    if category:
        skus = [s for s in skus if s.category == category.lower()]
    if max_price is not None:
        skus = [s for s in skus if s.shelf_price <= Decimal(str(max_price))]
    if q:
        # Deliberately shallow: real matching is Hieu's interpreter, over
        # attributes and embeddings. This is transport, not intelligence.
        needle = q.lower()
        skus = [s for s in skus if needle in s.title.lower()]
    return _respond(merchant, skus[:limit], negotiated)


@router.get("/{merchant_id}/ucp/catalog/lookup")
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

    matches = [s for s in _catalog[merchant_id] if s.sku_id == sku_id]
    if not matches:
        raise HTTPException(404, f"unknown sku {sku_id!r}")
    return _respond(merchant, matches, negotiated)


def create_app() -> FastAPI:
    app = FastAPI(title="BondLayer merchant service")
    app.include_router(router)
    app.include_router(onboard.router)
    seed()
    onboard.seed()
    return app


app = create_app()
