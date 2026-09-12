"""Run one shopper request end to end and print the trace, in-process.

    python scripts/trace_run.py "<utterance>" [--control]

This is Part 1 of WS-B, day 2: the insurance demo. It runs
``bondlayer.agent.composition.run_request`` against the real merchant server
-- via FastAPI's ``TestClient``, exactly as ``tests/test_ucp.py`` and
``tests/test_composition.py`` do, so there is no second implementation and no
network call -- with the real deterministic parser (Hieu's
``interpreter/parser.py``) decoding intent, and real ES256 verification
(``bondlayer.records.signing``) checking every record against the key each
merchant actually published at ``/.well-known/ucp``.

``--control`` runs with the extension undeclared -- the same code path, the
same fetcher, the same merchants, one header shorter. Nothing here decides who
wins; ``run_request`` does, from what the wire actually returned.

Per the negotiation fact from WS-C: ``UCP-Agent`` must declare
``catalog.search`` itself, or the search route 406s before anything else runs.
The two headers this script sends are exactly:

    on  -> dev.ucp.shopping.catalog.search;dev.ucp.shopping.catalog.lookup;org.bondlayer.benefit_value
    off -> dev.ucp.shopping.catalog.search;dev.ucp.shopping.catalog.lookup
"""

from __future__ import annotations

import argparse
import inspect
import re
import sys
from pathlib import Path
from typing import Callable

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from fastapi.testclient import TestClient  # noqa: E402

from bondlayer.agent import Outcome, Phase, run_request  # noqa: E402
from bondlayer.agent.trace import AgentRun, Ranked, Step  # noqa: E402
from bondlayer.interpreter.parser import parse as parse_utterance  # noqa: E402
from bondlayer.records.serialise import record_from_json  # noqa: E402
from bondlayer.records.signing import ES256Signer  # noqa: E402
from bondlayer.types import ConstraintKind, SignedRecord  # noqa: E402
from bondlayer.ucp.server import create_app  # noqa: E402
from bondlayer.valuation.reference_policy import REFERENCE_SHOPPER_POLICY  # noqa: E402

#: The reference shopper (bondlayer.valuation.reference_policy) -- what the
#: pitch's own evaluation is valued against, not composition.py's DEFAULT_POLICY
#: (its 9999 sentinels exist so an unwired verifier's zero-credit path never
#: looks capped; they were never meant to be a real shopper's numbers and,
#: combined with composition.py not yet deduplicating repeat benefit types the
#: way bondlayer.valuation.DeterministicValuation does, push R01's effective
#: cost negative). Converted to the ``{benefit_type_value: Decimal}`` shape
#: ``run_request``'s ``policy`` parameter expects.
POLICY = {bt.value: v for bt, v in REFERENCE_SHOPPER_POLICY.values_aud.items()}

MERCHANTS = ["voltway", "citycircuit", "northgear"]

CATALOG_SEARCH = "dev.ucp.shopping.catalog.search"
CATALOG_LOOKUP = "dev.ucp.shopping.catalog.lookup"
BENEFIT_VALUE = "org.bondlayer.benefit_value"

#: The same category vocabulary the parser matches on, so a query built from
#: the decoded HARD constraints lands on the same category the interpreter saw.
_CATEGORIES = (
    "portable ssd", "coffee machine", "rice cooker", "laptop", "microphone",
    "headset", "monitor", "phone", "vacuum", "dock",
)
_PRICE = re.compile(
    r"\b(?:under|below|less\s+than|no\s+more\s+than|up\s+to)\s*\$?\s*([\d,]+(?:\.\d+)?)",
    re.IGNORECASE,
)


def _search_params(utterance: str) -> dict:
    """Category and price ceiling from the decoded HARD constraints.

    This is transport, not intelligence -- the same shallow job the merchant's
    own ``q`` param does (README, "The adapter: normalising the mess"). The
    real matching is the interpreter's; this just turns what it already found
    into query params the search route understands, so the wire request is
    built from decoded intent rather than the raw sentence.
    """
    hard_text = " ".join(
        c.text for c in parse_utterance(utterance) if c.kind is ConstraintKind.HARD
    ) or utterance
    category = next(
        (c for c in _CATEGORIES if re.search(rf"\b{re.escape(c)}\b", hard_text, re.IGNORECASE)),
        None,
    )
    price_match = _PRICE.search(hard_text)
    params: dict = {}
    if category:
        params["category"] = category
    if price_match:
        params["max_price"] = float(price_match.group(1).replace(",", ""))
    return params


def make_fetcher(client: TestClient) -> Callable[..., dict]:
    def fetch(merchant: str, query: str, *, extension: bool) -> dict:
        header = CATALOG_SEARCH + ";" + CATALOG_LOOKUP
        if extension:
            header += ";" + BENEFIT_VALUE
        response = client.get(
            f"/{merchant}/ucp/catalog/search",
            params=_search_params(query),
            headers={"UCP-Agent": header},
        )
        if response.status_code == 406:
            raise PermissionError(response.json().get("detail", response.text))
        response.raise_for_status()
        return response.json()

    return fetch


def make_verifier(client: TestClient, merchants: list[str]) -> Callable[[dict], bool]:
    """Real ES256 verification against each merchant's own published key.

    Resolved once, from ``/.well-known/ucp``'s ``signing_keys[]`` -- never from
    a local copy. A key that does not resolve, or a record whose issuer does
    not match the key it claims, verifies false: fail closed.
    """
    keys_by_issuer: dict[str, dict[str, dict]] = {}
    for merchant in merchants:
        response = client.get(f"/{merchant}/.well-known/ucp")
        if response.status_code != 200:
            continue
        body = response.json()
        domain = body.get("business", {}).get("domain")
        if not domain:
            continue
        keys_by_issuer[domain] = {
            jwk["kid"]: jwk for jwk in body.get("signing_keys", []) if jwk.get("kid")
        }

    def verify(entry: dict) -> bool:
        record = entry.get("record") or {}
        issuer = record.get("issuer")
        key_id = entry.get("key_id")
        signature = entry.get("signature")
        if not issuer or not key_id or not signature:
            return False
        jwk = keys_by_issuer.get(issuer, {}).get(key_id)
        if jwk is None:
            return False
        try:
            benefit_record = record_from_json(record)
            signed = SignedRecord(record=benefit_record, signature=signature, key_id=key_id)
            verifier = ES256Signer.from_jwk(jwk, issuer=issuer)
        except (ValueError, KeyError, TypeError):
            return False
        return verifier.verify(signed)

    return verify


def _interpret_kwargs(parser: Callable[[str], list]) -> dict:
    """Pass the parser as ``interpret`` if ``run_request`` has grown that
    parameter (WS-A's resolver wiring, DAY2-PLAN.md WS-A step 2), else as
    ``parse`` (today's signature). Checked by introspection so this script
    does not have to be edited the moment that lands on a merged base --
    and does not break before it does.
    """
    params = inspect.signature(run_request).parameters
    return {"interpret": parser} if "interpret" in params else {"parse": parser}


# --- rendering ---------------------------------------------------------------

_BAR = "-" * 78


def _step_line(step: Step) -> str:
    return f"  [{step.phase.value:<11}:{step.outcome.value:<8}] {step.summary}"


def _money(value) -> str:
    return f"${value:.2f}"


def render(run: AgentRun, *, extension: bool) -> str:
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append(f"utterance : {run.utterance!r}")
    lines.append(f"extension : {'ON  (declares org.bondlayer.benefit_value)' if extension else 'OFF (--control, capability not declared)'}")
    lines.append(_BAR)

    lines.append("constraints parsed:")
    if run.constraints:
        for c in run.constraints:
            lines.append(f"  {c['kind']:<8} {c['text']!r}")
    else:
        lines.append("  (none -- no interpreter wired)")
    lines.append(_BAR)

    lines.append("steps:")
    for step in run.steps:
        lines.append(_step_line(step))
    lines.append(_BAR)

    if not run.ranked:
        lines.append("No offers were ranked -- every merchant refused or returned nothing.")
        return "\n".join(lines)

    lines.append("ranking (effective cost, ascending):")
    header = f"  {'#':<3}{'merchant':<13}{'sku_id':<10}{'shelf':>10}{'credited':>10}{'effective':>11}   seen/verified/credited"
    lines.append(header)
    for i, r in enumerate(run.ranked, start=1):
        lines.append(
            f"  {i:<3}{r.merchant:<13}{r.sku_id:<10}{_money(r.shelf_price):>10}"
            f"{_money(r.credited):>10}{_money(r.effective_cost):>11}   "
            f"{r.records_seen}/{r.records_verified}/{r.records_credited}"
            + (f"   ({r.withheld_note})" if r.withheld_note else "")
        )
    lines.append(_BAR)

    top = run.winner
    lines.append(f"citations for the winner ({top.merchant} {top.sku_id}):")
    if top.citations:
        for c in top.citations:
            lines.append(f"  {c['benefit_type']:<16} credited={c['credited']:<8} cited={c['cited']!s:<5} {c['why']}")
    else:
        lines.append("  (no records published for this listing)")
    lines.append(_BAR)

    cheapest_shelf = min(run.ranked, key=lambda r: r.shelf_price)
    flipped = top.sku_id != cheapest_shelf.sku_id
    if flipped:
        lines.append(
            f"FLIP: {top.merchant} ({top.sku_id}) wins on effective cost {_money(top.effective_cost)} "
            f"despite {cheapest_shelf.merchant} ({cheapest_shelf.sku_id}) having the cheaper shelf "
            f"price {_money(cheapest_shelf.shelf_price)}."
        )
    else:
        lines.append(
            f"NO FLIP: {top.merchant} ({top.sku_id}) wins on both shelf price and effective cost."
        )
    lines.append("=" * 78)
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("utterance", help="the shopper's request, in quotes")
    parser.add_argument(
        "--control", action="store_true",
        help="do not declare org.bondlayer.benefit_value -- the baseline run",
    )
    args = parser.parse_args()

    client = TestClient(create_app())
    extension = not args.control

    run = run_request(
        args.utterance,
        MERCHANTS,
        make_fetcher(client),
        extension=extension,
        verify=make_verifier(client, MERCHANTS),
        policy=POLICY,
        **_interpret_kwargs(parse_utterance),
    )
    print(render(run, extension=extension))


if __name__ == "__main__":
    main()
