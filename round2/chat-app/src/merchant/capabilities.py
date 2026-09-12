"""UCP capability negotiation -- server-selects, with extension pruning.

The degradation is **structural, not conditional**: there is no branch anywhere
that reads "if this agent is not ours, return less". There is one response
builder, and it emits an extension block only when that extension survived
negotiation.

That property is also what makes the control merchant honest. CityCircuit is
served by this module, on these routes, through that same builder. It simply
does not declare the benefit extension in its manifest, so the name
intersection prunes it. If the control were a second implementation, the
before/after comparison would prove nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Base capabilities we implement. Cart, checkout, order and payments are
#: deliberately absent -- BondLayer never touches them.
CATALOG_SEARCH = "dev.ucp.shopping.catalog.search"
CATALOG_LOOKUP = "dev.ucp.shopping.catalog.lookup"
IDENTITY_LINKING = "dev.ucp.common.identity_linking"

#: Ours. Reverse-domain named under org.bondlayer because dev.ucp.* is reserved
#: for capabilities governed by the UCP Tech Council.
BENEFIT_VALUE = "org.bondlayer.benefit_value"

#: It extends *catalog*, not checkout. UCP's own loyalty extension hangs off
#: checkout, so loyalty data only exists once the shopper has already chosen the
#: merchant -- by which time the comparison is over. Catalog is where the agent
#: actually decides.
BENEFIT_VALUE_EXTENDS = (CATALOG_SEARCH, CATALOG_LOOKUP)

PROTOCOL_VERSION = "2026-04-08"


@dataclass(frozen=True)
class Capability:
    name: str
    versions: tuple[str, ...]
    extends: tuple[str, ...] = ()

    @property
    def is_extension(self) -> bool:
        return bool(self.extends)


@dataclass(frozen=True)
class Negotiated:
    """What survived. ``active`` is echoed to the agent in every response."""

    active: dict[str, str] = field(default_factory=dict)
    pruned: dict[str, str] = field(default_factory=dict)

    def __contains__(self, name: str) -> bool:
        return name in self.active

    @property
    def serves_benefit_extension(self) -> bool:
        return BENEFIT_VALUE in self.active


def merchant_capabilities(publishes_benefit_extension: bool) -> list[Capability]:
    """What one merchant declares.

    The *only* difference between the BondLayer merchant and the control is this
    list, and it comes from the manifest. Same module, same routes, same builder.
    """
    caps = [
        Capability(CATALOG_SEARCH, (PROTOCOL_VERSION,)),
        Capability(CATALOG_LOOKUP, (PROTOCOL_VERSION,)),
        Capability(IDENTITY_LINKING, (PROTOCOL_VERSION,)),
    ]
    if publishes_benefit_extension:
        caps.append(
            Capability(BENEFIT_VALUE, ("draft",), extends=BENEFIT_VALUE_EXTENDS)
        )
    return caps


def parse_agent_header(ucp_agent: str | None) -> dict[str, tuple[str, ...]]:
    """Parse the ``UCP-Agent`` request header into declared capabilities.

    Wire form, one header, capabilities separated by commas and an optional
    version after a semicolon::

        UCP-Agent: dev.ucp.shopping.catalog.search;v=2026-04-08,
                   org.bondlayer.benefit_value;v=draft

    An agent that declares nothing gets nothing negotiated, which is a valid
    UCP state and not an error.
    """
    if not ucp_agent:
        return {}

    declared: dict[str, tuple[str, ...]] = {}
    for part in ucp_agent.split(","):
        part = part.strip()
        if not part:
            continue
        name, _, params = part.partition(";")
        name = name.strip()
        if not name:
            continue
        versions: list[str] = []
        for param in params.split(";"):
            param = param.strip()
            if param.startswith("v="):
                versions.append(param[2:].strip())
        declared[name] = tuple(versions) if versions else (PROTOCOL_VERSION, "draft")
    return declared


def negotiate(
    merchant: list[Capability], agent: dict[str, tuple[str, ...]]
) -> Negotiated:
    """Intersect, select a version, then prune orphaned extensions.

    1. **Name intersection** -- only capabilities both parties declare proceed.
    2. **Version selection** -- highest mutual version; no overlap means the
       capability is excluded entirely.
    3. **Extension pruning** -- an extension is dropped when none of the parent
       capabilities it ``extends`` survived. Repeated until stable.
    """
    active: dict[str, str] = {}
    pruned: dict[str, str] = {}

    for cap in merchant:
        if cap.name not in agent:
            pruned[cap.name] = "not declared by agent"
            continue
        mutual = sorted(set(cap.versions) & set(agent[cap.name]), reverse=True)
        if not mutual:
            pruned[cap.name] = "no mutual version"
            continue
        active[cap.name] = mutual[0]

    # Prune extensions whose parents did not survive. Repeat until stable: an
    # extension of an extension has to fall over too.
    by_name = {c.name: c for c in merchant}
    changed = True
    while changed:
        changed = False
        for name in list(active):
            cap = by_name.get(name)
            if not cap or not cap.is_extension:
                continue
            if not any(parent in active for parent in cap.extends):
                del active[name]
                pruned[name] = "no surviving parent capability"
                changed = True

    return Negotiated(active=active, pruned=pruned)
