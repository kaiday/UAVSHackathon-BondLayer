"""A merchant's UCP surface.

Every merchant in the demo -- BondLayer-equipped or not -- runs one of these
as its own HTTP service (D9.11). The agent speaks to them over real HTTP,
because the claim being demonstrated is that a third-party agent can read a
merchant over a protocol; in-process calls would quietly assume that away.

Implemented: catalog.search, catalog.lookup, identity_linking, and the
capability declaration. Cart, checkout, order and payments are deliberately
absent -- BondLayer never touches them (D2).
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Header, HTTPException

from ..schema import BenefitValue, MemberContext, Offer
from . import capabilities as caps


class MerchantService:
    """One merchant. `bondlayer_enabled=False` gives a plain UCP merchant."""

    def __init__(
        self,
        merchant_id: str,
        merchant_name: str,
        offers: list[Offer],
        *,
        bondlayer_enabled: bool = False,
        public_key_b64: str | None = None,
        members: dict[str, MemberContext] | None = None,
        benefits: dict[str, list[BenefitValue]] | None = None,
    ) -> None:
        self.merchant_id = merchant_id
        self.merchant_name = merchant_name
        self.offers = offers
        self.bondlayer_enabled = bondlayer_enabled
        self.public_key_b64 = public_key_b64 if bondlayer_enabled else None
        self.members = members or {}
        # product_id -> benefit records
        self.benefits = benefits or {}

    # ------------------------------------------------------------------

    def declaration(self) -> dict[str, Any]:
        if self.bondlayer_enabled:
            return caps.base_declaration(self.public_key_b64)
        return caps.plain_ucp_declaration()

    def _agent_capabilities(self, ucp_agent: str | None) -> list[str]:
        """Parse the UCP-Agent header's declared capability list."""
        if not ucp_agent:
            return [caps.CATALOG_SEARCH, caps.CATALOG_LOOKUP]
        # Format: "agent-name; capabilities=a,b,c"
        parts = [p.strip() for p in ucp_agent.split(";")]
        for p in parts:
            if p.startswith("capabilities="):
                return [c.strip() for c in p[len("capabilities="):].split(",") if c.strip()]
        return [caps.CATALOG_SEARCH, caps.CATALOG_LOOKUP]

    def _render(
        self, offer: Offer, active: dict[str, Any], member_id: str | None
    ) -> dict[str, Any]:
        """Render one offer under the negotiated capability set.

        If the extension was pruned, the member block and benefits simply are
        not there -- the response is byte-identical to plain UCP (D3).
        """
        body = offer.without_extension().model_dump(mode="json", exclude={"benefits", "member"})

        if caps.BENEFIT_VALUE not in active:
            return body

        records = self.benefits.get(offer.product_id, [])
        member = self.members.get(member_id) if member_id else None

        if not records and member is None:
            return body

        body[caps.BENEFIT_VALUE] = {
            "version": "2026-08-30",
            "benefits": [b.model_dump(mode="json") for b in records],
            "member": member.model_dump(mode="json") if member else None,
        }
        return body

    def build_app(self) -> FastAPI:
        app = FastAPI(title=f"UCP merchant: {self.merchant_name}")

        @app.get("/.well-known/ucp")
        def declaration() -> dict[str, Any]:
            return {
                "business": {"id": self.merchant_id, "name": self.merchant_name},
                "capabilities": self.declaration(),
            }

        @app.get("/ucp/catalog/search")
        def catalog_search(
            q: str = "",
            member_id: str | None = None,
            ucp_agent: str | None = Header(default=None, alias="UCP-Agent"),
        ) -> dict[str, Any]:
            active = caps.negotiate(self.declaration(), self._agent_capabilities(ucp_agent))
            if caps.CATALOG_SEARCH not in active:
                raise HTTPException(406, "catalog.search not in the negotiated set")

            terms = [t for t in q.lower().split() if len(t) > 2]
            matches = [
                o
                for o in self.offers
                if not terms
                or any(t in (o.title + " " + o.brand).lower() for t in terms)
            ]
            return {
                "active_capabilities": list(active),
                "results": [self._render(o, active, member_id) for o in matches],
            }

        @app.get("/ucp/catalog/lookup/{product_id}")
        def catalog_lookup(
            product_id: str,
            member_id: str | None = None,
            ucp_agent: str | None = Header(default=None, alias="UCP-Agent"),
        ) -> dict[str, Any]:
            active = caps.negotiate(self.declaration(), self._agent_capabilities(ucp_agent))
            for o in self.offers:
                if o.product_id == product_id:
                    return {
                        "active_capabilities": list(active),
                        "product": self._render(o, active, member_id),
                    }
            raise HTTPException(404, "no such product")

        @app.get("/ucp/identity/link")
        def identity_link(member_id: str) -> dict[str, Any]:
            """Stand-in for the OAuth flow -- the linked state is what matters."""
            member = self.members.get(member_id)
            if member is None:
                raise HTTPException(404, "not a member of this program")
            return {"linked": True, "member": member.model_dump(mode="json")}

        return app
