"""The agent's side of the protocol: declare, fetch, verify.

**This module is where the BondLayer switch lives, and it is the only place.**

"Off" is not a different code path, a flag in the response builder, or a second
server. It is this agent declining to declare one capability in its
``UCP-Agent`` header, after which ordinary UCP negotiation on the merchant side
(``bondlayer``'s -- there is no other one) prunes the extension. Same route,
same builder, same fan-out, same merchants.

    on  -> dev.ucp.shopping.catalog.search;dev.ucp.shopping.catalog.lookup;org.bondlayer.benefit_value
    off -> dev.ucp.shopping.catalog.search;dev.ucp.shopping.catalog.lookup

``catalog.search`` has to be declared for search itself to succeed -- an agent
that sends only ``catalog.lookup;org.bondlayer.benefit_value`` gets a 406 on
the search route before negotiation ever reaches the extension. Everything
else about the two runs is identical. That is the only reason the comparison
is admissible evidence rather than a demo trick.

Verification is real ES256, against whatever key each merchant actually
published at its own ``/.well-known/ucp`` -- resolved live, every request,
never from a local copy (``bondlayer.records.signing``, the same module the
merchant server signs with).
"""

from __future__ import annotations

import inspect
import os
import re
from typing import Callable

import httpx

from bondlayer.interpreter.parser import parse as parse_utterance
from bondlayer.records.serialise import record_from_json
from bondlayer.records.signing import ES256Signer
from bondlayer.types import ConstraintKind, SignedRecord
from bondlayer.valuation.reference_policy import REFERENCE_SHOPPER_POLICY

#: Overridable so the demo, a test, or a judge's laptop can point this agent at
#: a merchant server running anywhere -- never a second implementation, always
#: bondlayer's own.
MERCHANT_BASE_URL = os.environ.get("BONDLAYER_MERCHANT_URL", "http://127.0.0.1:8000")
MERCHANTS = ["voltway", "citycircuit", "northgear"]

#: The reference shopper (bondlayer.valuation.reference_policy) -- the same one
#: bondlayer/scripts/trace_run.py and the evaluation run are valued against.
#: NOT composition.py's DEFAULT_POLICY: its 9999 sentinels exist so an unwired
#: verifier's zero-credit path never looks artificially capped, not as a real
#: shopper's numbers, and pair badly with composition.py not yet deduplicating
#: repeat benefit types the way bondlayer.valuation.DeterministicValuation
#: does. Converted to the ``{benefit_type_value: Decimal}`` shape
#: ``run_request``'s ``policy`` parameter expects.
POLICY = {bt.value: v for bt, v in REFERENCE_SHOPPER_POLICY.values_aud.items()}

CATALOG_SEARCH = "dev.ucp.shopping.catalog.search"
CATALOG_LOOKUP = "dev.ucp.shopping.catalog.lookup"
BENEFIT_VALUE = "org.bondlayer.benefit_value"

#: Same vocabulary the interpreter's parser matches categories on, so the
#: search query built from decoded HARD constraints lands on the category the
#: interpreter actually saw. Transport, not intelligence -- the real matching
#: is the parser's; this just turns what it found into query params.
_CATEGORIES = (
    "portable ssd", "coffee machine", "rice cooker", "laptop", "microphone",
    "headset", "monitor", "phone", "vacuum", "dock",
)
_PRICE = re.compile(
    r"\b(?:under|below|less\s+than|no\s+more\s+than|up\s+to)\s*\$?\s*([\d,]+(?:\.\d+)?)",
    re.IGNORECASE,
)


def agent_header(bondlayer_enabled: bool) -> str:
    """What this agent declares it can understand.

    The switch, in full. Nothing else in the system branches on it. Note that
    ``catalog.search`` is declared in *both* states -- the toggle only ever
    adds or removes the benefit extension, never the base capability the
    search route requires to answer at all.
    """
    declared = [CATALOG_SEARCH, CATALOG_LOOKUP]
    if bondlayer_enabled:
        declared.append(BENEFIT_VALUE)
    return ";".join(declared)


def _search_params(utterance: str) -> dict:
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


def make_fetcher(client: httpx.Client | None = None) -> Callable[..., dict]:
    """A ``bondlayer.agent.composition.Fetcher`` over real HTTP.

    ``client`` is accepted so a caller (a test, or a script) can hand in one
    already pointed at an in-process app; the default opens a real connection
    to ``MERCHANT_BASE_URL`` -- the one place this agent touches the network,
    and only ever localhost.
    """
    owns_client = client is None
    http = client or httpx.Client(base_url=MERCHANT_BASE_URL, timeout=10)

    def fetch(merchant: str, query: str, *, extension: bool) -> dict:
        header = CATALOG_SEARCH + ";" + CATALOG_LOOKUP
        if extension:
            header += ";" + BENEFIT_VALUE
        response = http.get(
            f"/{merchant}/ucp/catalog/search",
            params=_search_params(query),
            headers={"UCP-Agent": header},
        )
        if response.status_code == 406:
            raise PermissionError(response.json().get("detail", response.text))
        response.raise_for_status()
        return response.json()

    fetch.client = http  # type: ignore[attr-defined]
    fetch.owns_client = owns_client  # type: ignore[attr-defined]
    return fetch


def make_verifier(client: httpx.Client | None = None) -> Callable[[dict], bool]:
    """Real ES256 verification against each merchant's own published key.

    Resolved from ``/.well-known/ucp``'s ``signing_keys[]`` the moment this is
    called -- never a copy shipped with the agent. A key that does not
    resolve, or a record whose issuer does not match the key it claims,
    verifies false: fail closed, exactly as ``bondlayer.agent.composition``
    expects of a ``verify`` callable.
    """
    http = client or httpx.Client(base_url=MERCHANT_BASE_URL, timeout=10)
    keys_by_issuer: dict[str, dict[str, dict]] = {}
    for merchant in MERCHANTS:
        try:
            response = http.get(f"/{merchant}/.well-known/ucp")
        except httpx.HTTPError:
            continue
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


def merchant_health() -> dict:
    """Whether the merchant service is reachable.

    The UI shows this, because "the agent returned nothing" and "the merchant
    is down" look identical otherwise.
    """
    try:
        with httpx.Client(base_url=MERCHANT_BASE_URL, timeout=3) as http:
            response = http.get("/voltway/.well-known/ucp")
        return {"reachable": response.status_code == 200, "status_code": response.status_code}
    except httpx.HTTPError as exc:
        return {"reachable": False, "error": str(exc)}


def interpret_kwargs(run_request_fn: Callable) -> dict:
    """Pass the parser as ``interpret`` if ``run_request`` has grown that
    parameter (WS-A's resolver wiring, DAY2-PLAN.md WS-A step 2), else as
    ``parse`` (today's signature). Decided by introspection, so ``main.py``
    keeps working whether or not that lands on this branch's base first.
    """
    params = inspect.signature(run_request_fn).parameters
    return {"interpret": parse_utterance} if "interpret" in params else {"parse": parse_utterance}
