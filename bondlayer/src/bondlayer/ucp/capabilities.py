"""UCP capability negotiation -- server-selects, with extension pruning.

§5.3 of the proposal claims *"ordinary capability negotiation serves its plain
UCP with no special-case code path"*, and someone will ask us to prove it. So
the degradation is **structural, not conditional**: there is no branch anywhere
that reads "if this agent is dumb, return less". There is one response builder,
and it emits an extension block only when that extension survived negotiation.

The same property is what makes the control merchant honest. CityCircuit is
served by this module, on this route, through this builder. It simply does not
declare the benefit extension in its manifest, so the intersection prunes it.
If the control were a second implementation, the comparison would prove nothing
(assumption A2).

Negotiation, per the spec:

1. **Name intersection** -- only capabilities both parties declare proceed.
2. **Version selection** -- highest mutual version; no overlap means the
   capability is excluded entirely.
3. **Extension pruning** -- an extension is dropped when none of the parent
   capabilities it ``extends`` survived. Repeat until stable.

The active set is echoed in every response, so the agent always knows what is
live rather than having to infer it from what is missing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

#: Base capabilities we implement. Cart, checkout, order and payments are
#: deliberately absent -- BondLayer never touches them (§"not attempted").
CATALOG_SEARCH = "dev.ucp.shopping.catalog.search"
CATALOG_LOOKUP = "dev.ucp.shopping.catalog.lookup"
IDENTITY_LINKING = "dev.ucp.common.identity_linking"

#: Ours. Reverse-domain named under org.bondlayer because dev.ucp.* is
#: reserved exclusively for capabilities governed by the UCP Tech Council.
BENEFIT_VALUE = "org.bondlayer.benefit_value"

#: It extends *catalog*, not checkout. UCP's own loyalty extension hangs off
#: dev.ucp.shopping.checkout, so loyalty data only exists once the shopper has
#: already chosen the merchant -- by which time the comparison is over. Catalog
#: is where the agent actually decides. (DECISIONS.md D3.)
BENEFIT_VALUE_EXTENDS = (CATALOG_SEARCH, CATALOG_LOOKUP)


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

    The *only* difference between the BondLayer merchant and the control is
    this list -- data, from the manifest. Same module, same route, same builder.
    """
    caps = [
        Capability(CATALOG_SEARCH, ("2026-04-08",)),
        Capability(CATALOG_LOOKUP, ("2026-04-08",)),
        Capability(IDENTITY_LINKING, ("2026-04-08",)),
    ]
    if publishes_benefit_extension:
        caps.append(
            Capability(BENEFIT_VALUE, ("draft",), extends=BENEFIT_VALUE_EXTENDS)
        )
    return caps


def parse_agent_header(raw: str | None) -> dict[str, tuple[str, ...]]:
    """Read the platform's advertised capabilities from ``UCP-Agent``.

    Two accepted shapes, because an agent that cannot be parsed must degrade
    rather than fail:

    - JSON: ``{"capabilities": {"dev.ucp.shopping.catalog.search": ["2026-04-08"]}}``
    - terse: ``dev.ucp.shopping.catalog.search;dev.ucp.shopping.catalog.lookup``

    A missing or unreadable header means the agent declared nothing but the
    base catalogue calls -- the plain-UCP path, which is what every UCP agent
    in the world does today.
    """
    default = {CATALOG_SEARCH: ("2026-04-08",), CATALOG_LOOKUP: ("2026-04-08",)}
    if not raw:
        return default
    raw = raw.strip()
    if raw.startswith("{"):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return default
        declared = payload.get("capabilities", {})
        if not isinstance(declared, dict):
            return default
        return {
            str(k): tuple(v) if isinstance(v, (list, tuple)) else (str(v),)
            for k, v in declared.items()
        }
    return {name.strip(): ("draft", "2026-04-08") for name in raw.split(";") if name.strip()}


def negotiate(
    merchant: list[Capability], agent: dict[str, tuple[str, ...]]
) -> Negotiated:
    active: dict[str, str] = {}
    pruned: dict[str, str] = {}

    # 1 + 2 -- name intersection, then highest mutual version.
    for cap in merchant:
        agent_versions = agent.get(cap.name)
        if agent_versions is None:
            pruned[cap.name] = "not declared by the agent"
            continue
        mutual = [v for v in cap.versions if v in agent_versions]
        if not mutual:
            pruned[cap.name] = "no mutually supported version"
            continue
        active[cap.name] = max(mutual)

    # 3 -- extension pruning, repeated until stable.
    extensions = {c.name: c for c in merchant if c.is_extension}
    changed = True
    while changed:
        changed = False
        for name, cap in extensions.items():
            if name in active and not any(p in active for p in cap.extends):
                del active[name]
                pruned[name] = "no surviving parent capability"
                changed = True

    return Negotiated(active=active, pruned=pruned)
