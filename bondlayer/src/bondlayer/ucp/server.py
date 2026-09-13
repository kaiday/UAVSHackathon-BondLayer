"""The merchant service: uploaded merchants, one shared protocol implementation.

The correctness property this file exists to hold:

    An agent **with** the benefit extension and an agent **without** it both
    get a valid response from the same route, built by the same function. The
    control merchant is this server with the extension absent from its
    manifest -- not a second implementation, not a flag inside the builder.

If that stops being true, the before/after comparison proves nothing and the
headline result is worthless (assumption A2).

Starts empty and restores uploaded catalogues without outbound network calls.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, FastAPI, Header, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from bondlayer.adapters import CsvCatalogAdapter
from bondlayer.types import Sku
from bondlayer.ucp import checkout, intent, onboard
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
from bondlayer.ucp.records import bundles_for, for_sku, load_records
from bondlayer.ucp.storage import UPLOADS, load_uploads, test_data_enabled

CATALOG = DATA / "catalog" / "electronics.csv"

router = APIRouter(tags=["ucp"])

_merchants: dict[str, Merchant] = {}
_catalog: dict[str, list[Sku]] = {}
_records: dict[str, list[dict]] = {}


def seed() -> None:
    """Restore only user uploads; the empty registry is a valid first start."""
    _merchants.clear()
    _catalog.clear()
    _records.clear()
    onboard._reports.clear()
    if test_data_enabled():
        for mid, merchant in load_merchants().items():
            report = CsvCatalogAdapter(CATALOG, merchant=mid).analyse()
            _merchants[mid], _catalog[mid] = merchant, report.skus
            _records[mid] = load_records(mid)
            onboard._reports[mid] = report
    else:
        for merchant, report in load_uploads(UPLOADS):
            _merchants[merchant.id], _catalog[merchant.id] = merchant, report.skus
            _records[merchant.id] = []
            onboard._reports[merchant.id] = report


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


def _bundles_block(skus: list[Sku], query: str | None,
                   max_price: float | None) -> dict | None:
    """The merchant's pitched sets, as one trailing block on the extension.

    Additive in the only sense that matters here: it rides the benefit
    extension, so it is gated by exactly the same negotiation as every record.
    An agent that did not declare ``org.bondlayer.benefit_value`` never reaches
    this function, and the control merchant -- which does not publish the
    extension at all -- cannot serve it.

    It is appended *after* the per-SKU blocks and carries ``sku_id: None``,
    because it is a property of the result set rather than of any one listing.
    Consumers that index the list positionally or map it by ``sku_id`` are
    unaffected; ``kind`` is there so a reader never has to infer the shape.
    """
    bundles = bundles_for(skus, query, max_price)
    if not bundles:
        return None
    return {"sku_id": None, "kind": "bundles", "bundles": bundles}


def _respond(merchant: Merchant, skus: list[Sku], negotiated: Negotiated,
             *, query: str | None = None, max_price: float | None = None,
             bundles: bool = False) -> dict:
    """The single response builder. There is no second one.

    Note what is *not* here: any test of the merchant's role, name or
    manifest. The extension block appears when the extension survived
    negotiation, and for no other reason. That is what makes graceful
    degradation structural rather than conditional.

    ``bundles`` is set by ``catalog.search`` and not by ``catalog.lookup``: a
    lookup is one listing, and a set of one adds nothing to it.
    """
    body: dict = {
        "business": {"id": merchant.id, "name": merchant.display_name},
        # Echo the active set so the agent knows what is live rather than
        # inferring it from what is missing.
        "active_capabilities": negotiated.active,
        "products": [_product(s) for s in skus],
    }
    if BENEFIT_VALUE in negotiated:
        blocks = [_benefit_block(merchant, s) for s in skus]
        if bundles:
            block = _bundles_block(skus, query, max_price)
            if block is not None:
                blocks.append(block)
        body["extensions"] = {BENEFIT_VALUE: blocks}
    return body


@router.get("/{merchant_id}/.well-known/ucp")
def profile(merchant_id: str) -> dict:
    return build_profile(_merchant(merchant_id))


@router.get("/{merchant_id}/ucp/catalog/search")
def catalog_search(
    merchant_id: str,
    q: str | None = Query(default=None),
    category: str | None = Query(default=None),
    max_price: float | None = Query(default=None, ge=0, allow_inf_nan=False),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
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
    # `category` is the typed plan the agent sent; `q` is a product name the
    # shopper actually said. Either names the intent well enough to compose
    # against, and neither carries a SERVICE or VALUES clause -- those are
    # withheld agent-side so no merchant can price against them.
    response = _respond(merchant, skus[offset:offset + limit], negotiated,
                        query=" ".join(p for p in (category, q) if p),
                        max_price=max_price, bundles=True)
    response["next_offset"] = offset + limit if offset + limit < len(skus) else None
    return response


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


DASHBOARD = Path(__file__).resolve().parents[3] / "app" / "dashboard"
CONSOLE = Path(__file__).resolve().parents[3] / "app" / "out"


class ConsoleFiles(StaticFiles):
    """Resolve Next's page-segment requests against its nested static export."""

    async def get_response(self, path: str, scope):
        if Path(path).name.startswith("__next.") and path.endswith(".__PAGE__.txt"):
            try:
                response = await super().get_response(path.removesuffix(".__PAGE__.txt") + "/__PAGE__.txt", scope)
                if response.status_code != 404:
                    return response
            except StarletteHTTPException as exc:
                if exc.status_code != 404:
                    raise
        return await super().get_response(path, scope)


def create_app() -> FastAPI:
    app = FastAPI(title="BondLayer merchant service")
    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "service": "merchant", "merchants": len(_merchants)}

    @app.get("/dashboard/", include_in_schema=False)
    def legacy_dashboard():
        return RedirectResponse("/console/")
    app.include_router(router)
    app.include_router(onboard.router)
    app.include_router(intent.router)
    app.include_router(checkout.router)
    if test_data_enabled() and DASHBOARD.is_dir():
        # React is vendored under app/dashboard/vendor and served from here.
        # No CDN: a script tag pointing at the internet is a live fetch at demo
        # time, on venue wifi shared by twenty teams.
        app.mount(
            "/dashboard",
            StaticFiles(directory=DASHBOARD, html=True),
            name="dashboard",
        )
    if CONSOLE.is_dir():
        # The Next.js console, exported to static files (bondlayer/app/out).
        # Built once with npm and committed, so the venue needs no Node.
        app.mount("/console", ConsoleFiles(directory=CONSOLE, html=True), name="console")
    seed()
    onboard.seed()
    return app


app = create_app()
