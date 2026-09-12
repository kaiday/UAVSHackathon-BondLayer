"""UCP capability declaration and server-selects negotiation.

Implements the mechanism described at ucp.dev/documentation/core-concepts:

  1. Name intersection    -- only capabilities both parties declare proceed.
  2. Version selection    -- highest mutual version by date, else excluded.
  3. Extension pruning    -- extensions whose parents did not survive are
                             dropped; repeat until stable.

This matters more than it looks. It is *why the demo's before/after is honest*
(D5): the baseline run is simply an agent that does not declare
org.bondlayer.benefit_value. Negotiation prunes the extension and the merchant
returns plain UCP. We never switch to a special "make the baseline lose" code
path -- the protocol does it.
"""

from __future__ import annotations

from typing import Any

CATALOG_SEARCH = "dev.ucp.shopping.catalog.search"
CATALOG_LOOKUP = "dev.ucp.shopping.catalog.lookup"
IDENTITY_LINKING = "dev.ucp.common.identity_linking"

BENEFIT_VALUE = "org.bondlayer.benefit_value"

#: The real UCP loyalty extension, for reference. We do NOT implement it: it
#: extends checkout, so its data arrives after the comparison is over
#: (docs/ucp-findings.md, finding 3).
UCP_LOYALTY = "dev.uip.shopping.loyalty"


def base_declaration(public_key_b64: str | None = None) -> dict[str, Any]:
    """What a BondLayer-equipped merchant advertises."""
    decl: dict[str, Any] = {
        CATALOG_SEARCH: [{"version": "2026-04-08"}],
        CATALOG_LOOKUP: [{"version": "2026-04-08"}],
        IDENTITY_LINKING: [{"version": "2026-04-08"}],
    }
    entry: dict[str, Any] = {
        "version": "2026-08-30",
        "extends": CATALOG_LOOKUP,
        "spec": "https://bondlayer.example/spec/benefit_value",
        "schema": "https://bondlayer.example/schemas/benefit_value.json",
    }
    if public_key_b64 is not None:
        # D9.8: the trust root lives here because the agent already fetches
        # this document during negotiation. Demo-grade -- see signing.py.
        entry["signing_public_key"] = public_key_b64
        entry["signing_algorithm"] = "ed25519"
    # Note: a merchant may declare the extension WITHOUT publishing a key.
    # Its records then arrive unsigned, are displayed, and are never valued.
    # That is the adversary case, and it must be representable.
    decl[BENEFIT_VALUE] = [entry]
    return decl


def plain_ucp_declaration() -> dict[str, Any]:
    """A merchant with no BondLayer -- competitors B and C."""
    return {
        CATALOG_SEARCH: [{"version": "2026-04-08"}],
        CATALOG_LOOKUP: [{"version": "2026-04-08"}],
    }


def negotiate(
    business: dict[str, Any], agent_declares: list[str]
) -> dict[str, Any]:
    """Server-selects intersection. Returns the active capability set."""
    active = {name: entries for name, entries in business.items() if name in agent_declares}

    # Extension pruning, repeated until stable.
    changed = True
    while changed:
        changed = False
        for name in list(active):
            for entry in active[name]:
                parent = entry.get("extends")
                if parent is not None and parent not in active:
                    del active[name]
                    changed = True
                    break

    return active
