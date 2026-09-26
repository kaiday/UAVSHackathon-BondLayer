"""``POST /{merchant}/ucp/identity/link`` -- the merchant answers for its own members.

``dev.ucp.common.identity_linking`` has been in every merchant's declared
capability list since the profile was written, and nothing implemented it. This
route does, and it is deliberately the smallest thing that can be true: the
agent offers an id, and the merchant says what -- if anything -- that id means
to it. No credential is exchanged, no session is created, nothing is stored.

**The answer is the merchant's, not the agent's.** An agent cannot send
``{"shopper_id": "x", "tier": "plus"}`` and be believed, because ``tier`` is not
a field this route reads. The only input is the id; the status, the tier and the
order count come out of the merchant's own roster
(``bondlayer.ucp.membership``). That matters because tier-gated records are
worth real money: if a tier could be asserted, the comparison would measure what
agents claim rather than what merchants owe.

**``linked: false`` is a normal answer.** An id the merchant does not carry is
not an error and not a 404 -- most shoppers are not members of most merchants,
and the agent needs to hear "not here" plainly so it can stop crediting this
merchant's member benefits rather than silently keep them.

The route exists mainly so a shopper can *check* a linkage before spending a
comparison on it. The catalogue call carries ``shopper_id`` itself and resolves
it through the same function, so nothing has to be linked here first.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from bondlayer.ucp.capabilities import IDENTITY_LINKING
from bondlayer.ucp.membership import resolve_shopper

router = APIRouter(tags=["ucp"])


def _server():
    """The merchant server's seeded state, fetched at call time.

    ``server`` includes this router, so a top-level import here would be
    circular and which module loaded first would depend on the caller.
    """
    from bondlayer.ucp import server

    return server


class LinkIn(BaseModel):
    """The whole request. One field, on purpose -- see the module docstring."""

    shopper_id: str | None = None


@router.post("/{merchant_id}/ucp/identity/link")
def identity_link(
    merchant_id: str,
    body: LinkIn,
    ucp_agent: str | None = Header(default=None, alias="UCP-Agent"),
) -> dict:
    srv = _server()
    merchant = srv._merchant(merchant_id)
    negotiated = srv._negotiated(merchant, ucp_agent)
    if IDENTITY_LINKING not in negotiated:
        raise HTTPException(406, "identity_linking was not negotiated")

    identity = resolve_shopper(srv._rosters, merchant.id, body.shopper_id)
    return {
        **identity,
        "merchant": merchant.id,
        "active_capabilities": negotiated.active,
    }
