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
import textwrap
from pathlib import Path
from typing import Callable

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from fastapi.testclient import TestClient  # noqa: E402

from bondlayer.agent import Outcome, Phase, run_request  # noqa: E402
from bondlayer.agent.close_loop import close_loop, close_loop_step  # noqa: E402
from bondlayer.agent.merchant_decode import (  # noqa: E402
    EXTENSION_OFF_SUMMARY,
    merchant_decode_step,
    run_with_merchant_decode,
)
from bondlayer.agent.trace import AgentRun, Ranked, Step  # noqa: E402
from bondlayer.bundle import CategoryBundler, role_of  # noqa: E402
from bondlayer.interpreter.parser import parse as parse_utterance  # noqa: E402
#: Rendered verbatim for an unanswered SERVICE/VALUES clause. Imported from the
#: resolver rather than spelled again here: the marker is the resolver's own
#: finding, and a console able to produce it independently could produce it when
#: the resolver did not. If this line is on screen, a ResolvedConstraint said so.
from bondlayer.interpreter.resolver import UNANSWERED  # noqa: E402
from bondlayer.records.serialise import record_from_json  # noqa: E402
from bondlayer.records.signing import ES256Signer  # noqa: E402
from bondlayer.types import ConstraintKind, SignedRecord  # noqa: E402
from bondlayer.ucp.capabilities import CHECKOUT, INTENT_MATCH  # noqa: E402
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
    if not utterance or not utterance.strip():
        # composition.run_request sends an empty ``query`` when the shopper
        # named no product; the typed plan carries category and ceiling instead.
        return {"limit": PAGE}
    hard_text = " ".join(
        c.text for c in parse_utterance(utterance) if c.kind is ConstraintKind.HARD
    ) or utterance
    category = next(
        (c for c in _CATEGORIES if re.search(rf"\b{re.escape(c)}\b", hard_text, re.IGNORECASE)),
        None,
    )
    price_match = _PRICE.search(hard_text)
    params: dict = {"limit": PAGE}
    if category:
        params["category"] = category
    if price_match:
        params["max_price"] = float(price_match.group(1).replace(",", ""))
    return params


#: ``catalog.search`` defaults to 20 results and caps at 100. Twenty silently
#: truncates a 149-row catalogue, which matters for bundling: a podcasting
#: request names no category, so the untruncated shelf is what the set has to
#: be composed from, and a microphone that fell off the end of page one cannot
#: be in it. Asking for the cap costs nothing offline and changes no ranking --
#: every request whose plan filters at all returns well under 20 per merchant.
PAGE = 100


def _params_from_plan(plan: dict) -> dict:
    """Typed search plan from ``composition.run_request`` -> query params.

    The interpreter already decoded category, ceiling and any product name;
    this only spells them the way the search route reads them.
    """
    params: dict = {"limit": PAGE}
    if plan.get("category"):
        params["category"] = str(plan["category"])
    if plan.get("max_price") is not None:
        params["max_price"] = float(plan["max_price"])
    if plan.get("terms"):
        params["q"] = " ".join(str(t) for t in plan["terms"])
    return params


def make_fetcher(client: TestClient) -> Callable[..., dict]:
    def fetch(merchant: str, query: str, *, extension: bool, plan: dict | None = None) -> dict:
        header = CATALOG_SEARCH + ";" + CATALOG_LOOKUP
        if extension:
            header += ";" + BENEFIT_VALUE
        response = client.get(
            f"/{merchant}/ucp/catalog/search",
            params=_params_from_plan(plan) if plan else _search_params(query),
            headers={"UCP-Agent": header},
        )
        if response.status_code == 406:
            raise PermissionError(response.json().get("detail", response.text))
        response.raise_for_status()
        return response.json()

    return fetch


def make_proposer(client: TestClient) -> Callable[..., dict | None]:
    """A ``bondlayer.agent.merchant_decode.Proposer`` over the in-process app.

    Mirrors ``make_fetcher``: same client, same header logic, one capability
    more. ``POST /{merchant}/ucp/intent/propose`` with the sentence verbatim;
    406 (the merchant did not negotiate ``org.bondlayer.intent_match``) is
    ``None``, any other failure raises. The extension-off run never gets here
    -- the wrapper does not call ``propose`` at all -- but the header logic is
    kept honest anyway: without the extension nothing beyond plain search is
    declared, so the answer would be 406 and ``None``.
    """
    def propose(merchant: str, utterance: str, *, extension: bool) -> dict | None:
        if not extension:
            return None
        header = ";".join([CATALOG_SEARCH, CATALOG_LOOKUP, BENEFIT_VALUE, INTENT_MATCH])
        response = client.post(
            f"/{merchant}/ucp/intent/propose",
            json={"utterance": utterance, "limit": 5},
            headers={"UCP-Agent": header},
        )
        if response.status_code == 406:
            return None
        response.raise_for_status()
        return response.json()

    return propose


def make_checkout(client: TestClient) -> Callable[..., dict | None]:
    """A ``bondlayer.agent.close_loop.Checkout`` over the in-process app.

    Mirrors ``make_proposer``: same client, same header logic. ``checkout`` is
    base UCP, so it is declared in **both** states -- the control run places a
    plain order on the same route; only whether the confirmation can carry
    honoured benefit records depends on the extension. 406 (the merchant did
    not negotiate ``dev.ucp.shopping.checkout``) is ``None``; any other
    failure raises.
    """
    def checkout(merchant: str, body: dict, *, extension: bool) -> dict | None:
        declared = [CATALOG_SEARCH, CATALOG_LOOKUP, CHECKOUT]
        if extension:
            declared.append(BENEFIT_VALUE)
        response = client.post(
            f"/{merchant}/ucp/checkout",
            json=body,
            headers={"UCP-Agent": ";".join(declared)},
        )
        if response.status_code == 406:
            return None
        response.raise_for_status()
        return response.json()

    return checkout


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


def _wrap(text: str, indent: str = "  ", width: int = 78) -> list[str]:
    return textwrap.wrap(text, width=width, initial_indent=indent,
                         subsequent_indent=indent) or [indent.rstrip()]


def _evidence(rc) -> str:
    """Where this clause's answer came from: a record, or a catalogue column."""
    if rc.evidence_record_id:
        return f"cites record {rc.evidence_record_id}"
    if rc.evidence_attribute:
        return f"on attribute {rc.evidence_attribute}"
    return "no evidence"


def render_justification(offer: Ranked, *, indent: str = "    ") -> list[str]:
    """Why this offer matches, one line per clause the shopper said.

    This is the answer to the thing the problem statement weighs highest: not
    "here are some SKUs" but "this clause, answered by this record or this
    column, for this reason". An unanswered SERVICE or VALUES clause keeps the
    resolver's own marker, so the trace says what the shelf could *not* do just
    as plainly as what it could.
    """
    if not offer.resolved:
        return [indent + "(no interpreter wired -- nothing to justify)"]
    lines: list[str] = []
    for rc in offer.resolved:
        kind = rc.constraint.kind.value
        lines.extend(_wrap(f"{kind:<8} {rc.constraint.text!r}", indent))
        if rc.note == UNANSWERED:
            # Never wrapped. This marker is a fixed string the console renders
            # verbatim, and a line break through the middle of it would make it
            # ungreppable and unquotable.
            lines.append(indent + "    " + UNANSWERED)
            continue
        lines.extend(_wrap(f"-> {_evidence(rc)} - {rc.note}", indent + "    "))
    return lines


def render_why(run: AgentRun) -> list[str]:
    """The per-constraint justification for the winner and for each rival.

    The winner alone would not make the point. The argument the demo has to
    land is comparative -- Voltway can answer "I can return it easily" and
    "a brand that actually repairs things" with two signed records, and
    CityCircuit answers neither -- so the best offer from every merchant gets
    its own block, and the ones that answer nothing say so.
    """
    if not run.ranked:
        return []
    lines = ["why these match (one line per clause the shopper said):"]
    seen: set[str] = set()
    for i, offer in enumerate(run.ranked):
        if offer.merchant in seen:
            continue
        seen.add(offer.merchant)
        tag = " <- WINNER" if i == 0 else ""
        lines.append("")
        lines.append(f"  {offer.merchant} {offer.sku_id} "
                     f"({_money(offer.effective_cost)} effective){tag}")
        lines.extend(render_justification(offer))
        if offer.unsatisfied:
            lines.extend(_wrap(
                "unsatisfied: " + "; ".join(c.text for c in offer.unsatisfied),
                "    "))
    return lines


def render_bundles(run: AgentRun) -> list[str]:
    """The composed set, rendered as a set.

    The point of this block is that it must not read as three search results
    stacked on top of each other. So the set gets one price and one reason --
    the combined total and the rationale for why these items belong *together*
    -- and the items hang underneath it as its parts, each with the notes that
    justified it individually. If a judge can read this as a list of offers,
    the criterion is lost on screen whatever the JSON says.
    """
    if not run.bundles:
        return []
    best = run.bundles[0]
    merchant = str(best.items[0].sku.attributes.get("merchant", "?"))
    lines = [_BAR, f"BUNDLE - {len(best.items)} items composed as one set "
                   f"({best.bundle_id})"]
    lines.append("")
    lines.append(f"  {merchant.upper()}   combined shelf price "
                 f"{_money(best.combined_shelf_price)}   "
                 f"one merchant, one order")
    lines.append("")
    lines.extend(_wrap("why these belong together: " + best.rationale, "  "))
    lines.append("")

    # Each item's own evidence, underneath it. A clause-level note is shown
    # when the shopper asked something a record answers; otherwise the records
    # that verified on that listing are cited directly. Either way the evidence
    # is per item, because the bundle's rationale deliberately says nothing
    # about why any individual item fits.
    by_sku = {r.sku_id: r for r in run.ranked}

    def paying_citations(item) -> list[dict]:
        offer = by_sku.get(item.sku.sku_id)
        return [c for c in (offer.citations if offer else [])
                if c.get("cited") and c.get("credited") not in (None, "0.00")]

    # A record the merchant publishes shelf-wide credits every item in the set
    # identically. Printing it five times says the same thing five times and
    # buries what is actually per item, so it is hoisted to where it belongs:
    # this really is a property of the set, which is the argument for buying
    # the set from one merchant in the first place.
    shared: list[dict] = []
    if len(best.items) > 1:
        common = set.intersection(*(
            {c["record_id"] for c in paying_citations(i)} for i in best.items
        ))
        seen_ids: set[str] = set()
        for c in paying_citations(best.items[0]):
            if c["record_id"] in common and c["record_id"] not in seen_ids:
                shared.append(c)
                seen_ids.add(c["record_id"])
    shared_ids = {c["record_id"] for c in shared}

    if shared:
        lines.append("  records that cover every item in this set:")
        for c in shared:
            lines.extend(_wrap(
                f"cites {c['record_id']} ({c['benefit_type']}) ${c['credited']} "
                f"per item - {c['why']}", "    "))
        lines.append("")

    for n, item in enumerate(best.items, start=1):
        role = (role_of(item) or item.sku.category).replace("_", " ")
        lines.append(
            f"   {n}. {item.sku.title[:44]:<44}{_money(item.sku.shelf_price):>10}"
            f"   [{role}]"
        )
        for note in item.resolved:
            if note.note == UNANSWERED:
                # Verbatim and unwrapped here too, so the marker reads the same
                # inside a set as it does under a single offer.
                lines.append("        " + UNANSWERED)
                continue
            mark = "cites" if note.evidence_record_id else "note "
            lines.extend(_wrap(f"{mark} {note.note}", "        "))
        if item.resolved:
            continue
        offer = by_sku.get(item.sku.sku_id)
        cited = [c for c in (offer.citations if offer else []) if c.get("cited")]
        if not cited:
            lines.append("        note  matched on catalogue attributes; this "
                         "listing published no record that verified")
            continue
        # What is left after the set-level records: only what is true of this
        # item and not of its neighbours.
        own = [c for c in paying_citations(item) if c["record_id"] not in shared_ids]
        for c in own:
            lines.extend(_wrap(
                f"cites {c['record_id']} ({c['benefit_type']}) "
                f"${c['credited']} - {c['why']}", "        "))
        zeroed = len(cited) - len(paying_citations(item))
        tail = []
        if not own and shared:
            tail.append("covered by the set-level records above")
        if zeroed:
            tail.append(f"{zeroed} further verified record"
                        f"{'s' if zeroed != 1 else ''} credit $0 here, out of "
                        "scope for this category")
        if tail:
            lines.extend(_wrap("note  " + "; ".join(tail), "        "))
    lines.append("")
    lines.append(f"   {'combined':<47}{_money(best.combined_shelf_price):>10}")

    for note in best.resolved:
        lines.extend(_wrap(f"set-level: {note.note}", "  "))
    for c in best.unsatisfied:
        lines.extend(_wrap(f"set-level UNSATISFIED ({c.kind.value}): {c.text}", "  "))

    others = run.bundles[1:]
    if others:
        lines.append("")
        lines.append("  other merchants could also assemble a set:")
        for b in others:
            m = str(b.items[0].sku.attributes.get("merchant", "?"))
            lines.append(f"    {m:<13}{len(b.items)} items"
                         f"{_money(b.combined_shelf_price):>12}")
    return lines


def render_merchant_decode(run: AgentRun) -> list[str]:
    """What each merchant understood and proposed, next to the agent's decode.

    Not a second ranking. Each line is the merchant's own reading of the
    sentence -- how many clauses it found, how many of them coincide with the
    agent's, and the first item on its own shelf that answers them, with the
    clauses that item leaves unanswered. The agent's ranking below decides
    nothing from this block; it is here so a judge can see the merchant system
    do steps 1-4 itself, and see where the two decodes would diverge.

    Empty when the run carries no merchant-decode step, so a run produced by
    plain ``run_request`` renders exactly as it did before this section existed.
    """
    step = merchant_decode_step(run)
    if step is None:
        return []
    lines = ["merchant decode (POST /ucp/intent/propose):"]
    if step.summary == EXTENSION_OFF_SUMMARY:
        lines.extend(_wrap(step.summary, "  "))
        lines.append(_BAR)
        return lines
    for d in step.detail.get("merchant_decodes", []):
        name = f"  {d['merchant']:<13}"
        if d.get("error"):
            lines.extend(_wrap(f"{name}could not be asked -- {d['error']}", ""))
            continue
        if not d["negotiated"]:
            lines.append(f"{name}did not negotiate {INTENT_MATCH} -- decoded nothing")
            continue
        decoded = d["decoded_intent"] or {}
        agree = d["agreement"]
        head = (f"{name}negotiated  {len(decoded.get('constraints', []))} constraints  "
                f"agrees with agent {agree['agreed']}/{agree['total']}")
        if d["proposals"]:
            top = d["proposals"][0]
            answered = sum(1 for r in top["resolved"] if r.get("satisfied"))
            tail = f"{answered}/{len(top['resolved'])} clauses answered"
            if top["unsatisfied"]:
                tail += "; unsatisfied: " + "; ".join(u["text"] for u in top["unsatisfied"])
            head += f"  first proposal {top['sku_id']} ({tail})"
        else:
            head += "  no proposal -- nothing on its shelf passes the HARD clauses"
        lines.append(head)
        indent = " " * 15
        for clause in agree["clauses"]:
            if not clause["agree"]:
                lines.extend(_wrap(
                    f"disagrees: agent read {clause['agent']['kind']} "
                    f"{clause['agent']['text']!r}; merchant did not", indent))
        for extra in agree.get("merchant_only", []):
            lines.extend(_wrap(
                f"merchant also read {extra['kind']} {extra['text']!r}", indent))
        # The console's contract (tests/test_trace_run.py, "the marker is never
        # broken across lines"): a line that says "no catalogue attribute" IS
        # the resolver's marker, verbatim, and nothing else may say it. Two of
        # the merchant's assumption sentences use those words to explain a
        # record-only clause, so those clauses are rendered from the merchant's
        # typed interpretation instead -- the benefit type it says a record must
        # carry -- and every other assumption is printed as the merchant wrote it.
        for a in decoded.get("assumptions", []):
            if "no catalogue attribute" in a:
                continue
            lines.extend(_wrap(f"assumes: {a}", indent))
        for c in decoded.get("constraints", []):
            need = (c.get("interpretation") or {}).get("benefit_type")
            if need:
                lines.extend(_wrap(
                    f"record-only: {c['text']!r} can only be answered by a "
                    f"verified {need} record", indent))
        if decoded.get("clarifying_question"):
            lines.extend(_wrap(f"asks: {decoded['clarifying_question']}", indent))
    lines.append(_BAR)
    return lines


def render_close_loop(run: AgentRun) -> list[str]:
    """The order the winning offer became, rendered as a receipt.

    Not another ranking: one line naming the merchant, the SKU, the order id,
    its status and the subtotal; one line saying payment is out of scope; then
    the merchant's verdict on every record the agent cited -- a tick or a cross,
    the id, the benefit type read off the returned envelope when there is one,
    and the merchant's own reason. The control run's order is a plain UCP order
    and says so in one line. Empty when the run carries no close-loop step, so
    a run produced without it renders exactly as before this section existed.
    """
    step = close_loop_step(run)
    if step is None:
        return []
    lines = [_BAR, "close the loop (POST /ucp/checkout):"]
    order = step.detail.get("order")
    if not order:
        lines.extend(_wrap(step.summary, "  "))
        return lines
    top = run.winner
    subtotal = (order.get("subtotal") or {}).get("amount", "0")
    lines.append(
        f"  {top.merchant:<13}{top.sku_id:<10}order {order.get('order_id', '?')}  "
        f"{order.get('status', '?')}  subtotal ${float(subtotal):,.2f}"
    )
    payment = order.get("payment") or {}
    if payment.get("status") == "out_of_scope":
        lines.append("  payment: out of scope for this prototype; no funds move")
    verdicts = step.detail.get("honoured_benefits")
    cited = step.detail.get("summary_counts", {}).get("cited", 0)
    if verdicts is None:
        if cited:
            lines.extend(_wrap(
                f"{cited} cited record{'s' if cited != 1 else ''} sent; the merchant "
                "returned no verdicts without the benefit extension.", "  "))
        else:
            lines.append("  plain UCP order: no benefit records were cited, so the order binds none.")
        return lines
    by_type = {c["record_id"]: c.get("benefit_type") for c in top.citations if c.get("record_id")}
    honoured = sum(1 for v in verdicts if v.get("honoured"))
    lines.append(f"  honoured benefits bound into the order ({honoured}/{cited} cited):")
    for v in verdicts:
        mark = "✓" if v.get("honoured") else "✗"
        btype = by_type.get(v.get("record_id"))
        label = f"{v.get('record_id')}" + (f" ({btype})" if btype else "")
        lines.extend(_wrap(f"{mark} {label:<28} {v.get('reason', '')}", "    "))
    return lines


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

    lines.extend(render_merchant_decode(run))

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

    lines.extend(render_why(run))
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
    lines.extend(render_bundles(run))
    # The last thing the trace shows: the winning offer became an order.
    lines.extend(render_close_loop(run))
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

    run = run_with_merchant_decode(
        args.utterance,
        MERCHANTS,
        make_fetcher(client),
        propose=make_proposer(client),
        extension=extension,
        verify=make_verifier(client, MERCHANTS),
        policy=POLICY,
        bundler=CategoryBundler(),
        **_interpret_kwargs(parse_utterance),
    )
    # Step 5: the winning offer becomes an order, citing exactly the records the
    # agent relied on. Appends one step; the ranking above is already decided.
    close_loop(run, checkout=make_checkout(client), agent_ref="trace_run")
    print(render(run, extension=extension))


if __name__ == "__main__":
    main()
