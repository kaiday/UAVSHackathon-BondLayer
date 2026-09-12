"""The agent-side composition root.

Three correct components can still never meet. This is where they meet: the
interpreter (Hieu), signature verification and valuation (Bach), and the served
catalogue and benefit extension (Nguyen). Nothing here implements any of them.

Two rules govern everything below.

**Fail closed.** A component that is not wired yet is ABSENT, and absent never
means "assume it passed". An unverifiable record is worth zero, an unwired
verifier means *every* record is worth zero, and the trace says so out loud. A
demo that silently credits unverified value is the exact failure the whole
proposal argues against.

**Degrade honestly.** Every component is optional and the run still completes
without it, at lower fidelity, with a Step recording what was missing. Today
records[] is empty everywhere and no verifier exists; the run still produces a
ranking on shelf price and a trace that explains why nothing was credited.
That is a truthful demo of an incomplete system, which beats a fabricated demo
of a complete one.
"""

from __future__ import annotations

import inspect
from dataclasses import replace
from decimal import Decimal
from typing import Any, Callable, Protocol

from bondlayer.agent.trace import AgentRun, Outcome, Phase, Ranked, Step
from bondlayer.interpreter.resolver import (
    _plan_categories,
    interpret_hard,
)
from bondlayer.interpreter.resolver import resolve as default_resolve
from bondlayer.records.serialise import signed_from_json
from bondlayer.types import (
    BenefitType,
    Bundle,
    Constraint,
    ConstraintKind,
    Proposal,
    ShopperPolicy,
    SignedRecord,
    Sku,
)
from bondlayer.valuation import (
    ATTESTED_CONDITIONS,
    MERCHANT_DOMAINS,
    REFERENCE_SHOPPER_POLICY,
    DeterministicValuation,
)

#: The extension's reverse-domain name, as negotiated on the wire.
BENEFIT_EXT = "org.bondlayer.benefit_value"

def policy_from(shopper: ShopperPolicy) -> dict[str, Decimal]:
    """A ``ShopperPolicy`` in the dict shape ``run_request`` takes.

    One shopper, defined once in ``valuation/reference_policy.py``, used by the
    evaluation, the flip tests and the demo -- so the number on screen is the
    number in ``docs/eval-results.md``.
    """
    return {btype.value: value for btype, value in shopper.values_aud.items()}


#: What the shopper thinks each benefit is worth. Lives agent-side and is never
#: sent to a merchant, so no merchant can price against it (proposal §5.3).
#:
#: This **is** the reference shopper from ``valuation/reference_policy.py``.
#: It used to carry ``9999`` sentinels meaning "accept the merchant's face
#: value, uncapped", which was survivable against the small synthetic ceilings
#: in the tests and wrong against the real published records: Voltway's $700
#: laptop trade-in plus points plus member price summed past the shelf price
#: and drove effective cost negative. A caller who passes no policy now gets
#: the same shopper the evaluation and the flip tests are scored against, so
#: the number on screen is the number in ``docs/eval-results.md``.
DEFAULT_POLICY: dict[str, Decimal] = policy_from(REFERENCE_SHOPPER_POLICY)


class Fetcher(Protocol):
    """Returns a parsed UCP search response for one merchant.

    A fetcher may additionally declare a ``plan`` keyword. When it does, it is
    handed the decoded HARD clauses -- ``{"category": ..., "max_price": ...}``,
    the shape ``catalog.search`` already takes as query parameters -- so the
    filter travels as typed parameters instead of as words in a search box. A
    fetcher that does not declare it keeps working unchanged.
    """

    def __call__(self, merchant: str, query: str, *, extension: bool) -> dict: ...


def _accepts_plan(fetch: Fetcher) -> bool:
    try:
        params = inspect.signature(fetch).parameters
    except (TypeError, ValueError):  # a builtin or a C callable
        return False
    return "plan" in params or any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()
    )


def _decimal(v: Any) -> Decimal:
    # price.amount is a STRING, quantized to 2dp. Never re-round it.
    return Decimal(str(v))


# --- the valuation seam -----------------------------------------------------
#
# `bondlayer.valuation` is THE valuation (ruling D4/R2). Nothing below computes
# a credit; it rebuilds the wire response into the objects the valuation takes
# and hands the arithmetic over. Crediting inline here is what made the
# composition root and the evaluation disagree by $70 on R01: the inline
# version skipped scope gating, condition gating and per-benefit-type budget
# sharing, so a laptop earned the appliance warranty and the opened-audio
# returns window.


def _wire_record(entry: dict, block_issuer: str | None) -> SignedRecord | None:
    """One wire envelope as a ``SignedRecord``, or ``None`` if it is unreadable.

    The published feed carries every field, so the strict reader handles it.
    Minimal envelopes -- a hand-written test fixture, a merchant mid-rollout --
    are filled in from the block: a record with no issuer of its own is the
    issuing block's, and a record with no timestamp is read as undated rather
    than dropped. Degrade honestly: an unreadable record is skipped and its
    absence shows up as a record seen and not credited, never as a crash.
    """
    raw = entry.get("record")
    if not isinstance(raw, dict) or not raw.get("record_id"):
        return None
    payload = dict(raw)
    payload.setdefault("issuer", block_issuer)
    payload.setdefault("issued_at", "1970-01-01T00:00:00+00:00")
    ceiling = payload.get("value_ceiling_aud")
    if ceiling is not None and not isinstance(ceiling, str):
        payload["value_ceiling_aud"] = str(ceiling)
    if not payload.get("issuer"):
        return None
    try:
        return signed_from_json({
            "record": payload,
            "signature": entry.get("signature"),
            "key_id": entry.get("key_id"),
        })
    except (ValueError, KeyError, TypeError):
        return None


def _wire_sku(product: dict, merchant: str) -> Sku:
    """One wire product as a ``Sku``, so scope and binding can be checked.

    ``merchant`` is what the valuation's trust map is keyed on: a record binds
    to this listing only if its issuer is the domain this merchant publishes
    under. Category carries the scope check -- Voltway's 24-month appliance
    cover must not attach to a laptop.
    """
    attributes = dict(product.get("attributes") or {})
    attributes["merchant"] = merchant
    return Sku(
        sku_id=product.get("id", ""),
        title=product.get("title", ""),
        category=str(product.get("category", "")).lower(),
        shelf_price=_decimal(product.get("price", {}).get("amount", "0")),
        attributes=attributes,
    )


class _WireVerifier:
    """Adapts the agent's wire-level ``verify(entry)`` to the ``Signer`` seam.

    The valuation asks a ``Signer`` whether a ``SignedRecord`` verifies; the
    agent was handed a predicate over the wire envelope instead. This maps one
    onto the other by identity, so trust stays exactly where the caller put it
    and this module never decides what verifies.
    """

    def __init__(self, verify: Callable[[dict], bool] | None,
                 entries: dict[int, dict]) -> None:
        self._verify = verify
        self._entries = entries

    def sign(self, record):  # pragma: no cover - an agent never signs
        raise NotImplementedError("the agent side never signs a record")

    def verify(self, signed: SignedRecord) -> bool:
        # Fail closed: no verifier wired means nothing is verified.
        if self._verify is None:
            return False
        entry = self._entries.get(id(signed))
        return False if entry is None else bool(self._verify(entry))


def realisable_credit(valued: Decimal, shelf_price: Decimal) -> tuple[Decimal, Decimal]:
    """Split a valuation total into what this listing can carry, and what it cannot.

    A benefit cannot be worth more than the thing it is attached to. Merchant-
    wide records bind to every listing, so a $40 returns window and a $55
    member price land on a $30 cable and would rank it below free -- which is
    not a bargain, it is a broken number on screen.

    This is a **ranking floor, not a second valuation**: the input is whatever
    `bondlayer.valuation` already decided, and the excess is returned rather
    than discarded so the caller can report it as value the shopper cannot
    realise here. Both the composition root and the evaluation runner call
    this, so the agent's ranking and the merchant console cannot disagree.
    """
    if valued <= shelf_price:
        return valued, Decimal("0")
    return shelf_price, valued - shelf_price


def _shopper(policy: dict[str, Decimal]) -> ShopperPolicy:
    """The agent's ``{benefit_type: Decimal}`` dict as a ``ShopperPolicy``.

    An unknown benefit name is dropped rather than guessed: the valuation
    treats an absent entry as $0, which is the honest reading of "this shopper
    never said what that is worth".
    """
    values: dict[BenefitType, Decimal] = {}
    for name, value in policy.items():
        try:
            values[BenefitType(name)] = Decimal(str(value))
        except (ValueError, ArithmeticError):
            continue
    return ShopperPolicy(values_aud=values,
                         max_premium_over_cheapest_aud=Decimal("0"))


def _search_query(parsed: list) -> tuple[str, dict]:
    """The query sent to merchants, built from the HARD clauses.

    A decoded intent is not a keyword string, and sending the raw utterance
    would waste the decode: "A laptop under $1,500 I can return easily ..."
    asks a merchant to keyword-match on "return" and "repairs". The SERVICE and
    VALUES clauses are deliberately **not** sent at all -- they are the
    shopper's, they are answered from published records on the agent side, and
    a merchant that never sees them cannot price against them.

    The category and the ceiling travel as typed parameters in ``plan``, not as
    words in ``q``: ``catalog.search`` matches ``q`` as a shallow substring of
    the title, and no laptop's title contains the word "laptop". Only a product
    name the shopper actually said ("ThinkBook 14 G3") belongs in ``q``. With no
    such name the query is empty, the merchant returns its shelf, and the
    resolver does the filtering agent-side -- which is the architecture: the
    merchant publishes, the agent decides -- and, when it negotiates
    ``org.bondlayer.intent_match``, also receives the utterance and proposes;
    the agent still verifies and ranks.
    """
    hard = [c for c in parsed
            if getattr(getattr(c, "kind", None), "value", "") == "hard"]
    by_text = {c.text: interpret_hard(c.text) for c in hard}
    specs = [s for group in by_text.values() for s in group]

    # How the category clauses combine is the resolver's rule, called here
    # rather than reimplemented, so the shelf the merchant is asked for and the
    # shelf the resolver filters cannot drift apart. Two product nouns ("a work
    # laptop and a dock") widen it to both categories -- and `catalog.search`
    # takes one `category`, so the honest move is to send none and let the
    # agent filter. That is the architecture stated above: the merchant
    # publishes, the agent decides. Sending only the first noun would silently
    # drop the dock before any bundler could see it.
    wanted, _scoping = _plan_categories(hard, by_text)
    category = str(next(iter(wanted))) if wanted and len(wanted) == 1 else None
    ceilings = [s.value for s in specs if s.kind == "price"]
    terms = [str(s.value) for s in specs if s.kind == "product"]
    plan: dict = {}
    if category:
        plan["category"] = category
    if ceilings:
        plan["max_price"] = str(min(ceilings))
    if terms:
        plan["terms"] = terms
    return " ".join(terms).strip(), plan


# --- the bundling seam ------------------------------------------------------
#
# A `Bundler` takes `(constraints, proposals)`. This module never runs the
# resolver -- the merchant already filtered the shelf from the typed plan, so
# what came back over the wire *is* this merchant's match for the request. The
# proposals below are those wire listings, in the order the agent's own
# valuation ranked them, so the bundler's "first acceptable item wins" rule
# picks on effective cost without the bundler ever computing one.


class Bundler(Protocol):
    def compose(
        self, constraints: list[Constraint], proposals: list[Proposal],
    ) -> list[Bundle]: ...


class Resolve(Protocol):
    """``ConstraintInterpreter.resolve``'s signature, as a callable.

    The default is the real resolver. A caller passes its own only to test the
    seam; nothing in the product does.
    """

    def __call__(
        self, constraints: list[Constraint], skus: list[Sku],
        records: list[SignedRecord],
    ) -> list[Proposal]: ...


def _typed_constraints(constraints: list[dict]) -> list[Constraint]:
    """The decoded clauses as ``Constraint``s, whatever parser produced them.

    ``run_request`` accepts any callable as ``interpret`` and only ever reads
    ``.text`` and ``.kind`` off what comes back. The bundler needs the real
    types, so they are rebuilt here from the same dicts the trace already
    carries. A clause whose kind nothing recognised is dropped rather than
    guessed at.
    """
    out: list[Constraint] = []
    for c in constraints:
        try:
            out.append(Constraint(text=c["text"], kind=ConstraintKind(c["kind"])))
        except (KeyError, ValueError):
            continue
    return out


# --- the resolution seam ----------------------------------------------------
#
# The interpreter's `resolve()` is what turns a ranking into a justification:
# one `ResolvedConstraint` per clause the shopper said, carrying the catalogue
# attribute or the verified record that answers it and a sentence saying why.
# It used to run only inside `scripts/eval_run.py`, so the number on stage was
# provable and the *reason* for it was not. It runs here now, on the same path
# the demo and the chat app use.
#
# This replaces an earlier `_item_resolved` helper, which rebuilt a partial
# version of the same thing out of the valuation's citations and could only
# ever answer SERVICE and VALUES clauses. One resolver, one answer.


def _proposals_from(ranked: list[Ranked], skus: dict[str, Sku],
                    resolved: dict[str, Proposal]) -> list[Proposal]:
    """The ranked wire listings as ``Proposal``s, best effective cost first.

    A listing the resolver returned keeps the resolver's own ``Proposal`` --
    its notes, its citations and its unsatisfied clauses -- so the bundler and
    the ranking read the same justification. A listing the resolver excluded on
    a HARD clause, or that came back with no interpreter wired at all, still
    appears, with an empty justification rather than an invented one.
    """
    out: list[Proposal] = []
    for r in ranked:
        if r.sku_id in resolved:
            out.append(resolved[r.sku_id])
        elif r.sku_id in skus:
            out.append(Proposal(sku=skus[r.sku_id], resolved=[],
                                unsatisfied=[], records=[]))
    return out


def run_request(
    utterance: str,
    merchants: list[str],
    fetch: Fetcher,
    *,
    extension: bool = True,
    parse: Callable[[str], list] | None = None,
    interpret: Callable[[str], list] | None = None,
    verify: Callable[[dict], bool] | None = None,
    value_of: Callable[[dict], Decimal] | None = None,
    policy: dict[str, Decimal] | None = None,
    bundler: Bundler | None = None,
    resolve: Resolve | None = None,
) -> AgentRun:
    """One shopper request across every merchant, with the reasoning recorded.

    ``bundler`` is optional and strictly additive: without one the run is byte
    for byte what it was, and with one a ``Phase.BUNDLE`` step is appended
    *after* the ranking and ``AgentRun.bundles`` is populated. A bundler cannot
    add a listing, change a price or reorder the ranking -- it only says which
    of the already-ranked offers belong together.

    ``interpret`` (or its older name ``parse``) is the interpreter's
    ``parse`` seam. When one is passed, ``Phase.INTENT`` is ``OK``, the decoded
    constraints are in the step detail, and the query on the wire is built from
    the HARD clauses instead of the raw utterance. When neither is passed the
    ABSENT path still runs and the utterance goes through as a keyword query --
    degrade honestly, and say so in the trace.

    ``resolve`` is the interpreter's other seam, and it defaults to the real
    resolver, so a decoded request is justified clause by clause without the
    caller asking for it. Each ``Ranked`` offer then carries ``resolved`` and
    ``unsatisfied``, and a ``Phase.RESOLVE`` step summarises how much of the
    request the shelf could answer. Resolution never filters and never
    reorders -- the ranking is the same arithmetic it always was.
    """
    policy = policy or DEFAULT_POLICY
    shopper = _shopper(policy)
    steps: list[Step] = []
    constraints: list[dict] = []
    decode = interpret or parse
    query = utterance
    plan: dict = {}

    # --- intent -----------------------------------------------------------
    if decode is None:
        steps.append(Step(Phase.INTENT, Outcome.ABSENT,
                          "No interpreter wired - the request is passed through as a keyword query.",
                          {"utterance": utterance}))
    else:
        parsed = decode(utterance)
        constraints = [{"text": getattr(c, "text", str(c)),
                        "kind": getattr(getattr(c, "kind", None), "value", "unknown")}
                       for c in parsed]
        by_kind: dict[str, int] = {}
        for c in constraints:
            by_kind[c["kind"]] = by_kind.get(c["kind"], 0) + 1
        # ConstraintKind values are lowercase; counting the uppercase spelling
        # silently reported zero unanswerable clauses on every request.
        unanswerable = by_kind.get("service", 0) + by_kind.get("values", 0)
        query, plan = _search_query(parsed)
        steps.append(Step(
            Phase.INTENT, Outcome.OK,
            f"Decoded {len(constraints)} constraints; {unanswerable} of them cannot be "
            f"answered from any catalogue attribute.",
            {"constraints": constraints, "by_kind": by_kind,
             "query": query, "search_plan": plan}))

    # --- discovery, negotiation, verification, valuation ------------------
    ranked: list[Ranked] = []
    #: Every listing that came back, kept as a Sku so the bundler can compose
    #: sets from the same objects the valuation priced.
    wire_skus: dict[str, Sku] = {}
    #: Every record that **verified**, by record_id, and nothing else. This is
    #: the only collection the resolver is handed, which is what makes "an
    #: unsigned record is never cited" a property of the wiring rather than a
    #: rule the resolver has to remember. A merchant-wide record rides on every
    #: product block, so the id keys deduplicate it.
    verified_signed: dict[str, SignedRecord] = {}
    verifier_missing = verify is None
    any_records = False
    with_plan = bool(plan) and _accepts_plan(fetch)

    for merchant in merchants:
        try:
            body = (fetch(merchant, query, extension=extension, plan=plan)
                    if with_plan else fetch(merchant, query, extension=extension))
        except PermissionError as exc:  # 406: a legitimate protocol answer
            steps.append(Step(Phase.NEGOTIATION, Outcome.REFUSED,
                              f"{merchant} refused a capability this agent did not declare.",
                              {"merchant": merchant, "detail": str(exc)}))
            continue

        products = body.get("products", [])
        # `extensions` is ABSENT, not empty, when negotiation dropped it.
        ext_blocks = body.get("extensions", {}).get(BENEFIT_EXT)
        steps.append(Step(
            Phase.DISCOVERY, Outcome.OK,
            f"{merchant} returned {len(products)} products"
            + (" with the benefit extension." if ext_blocks is not None else " as plain UCP."),
            {"merchant": merchant, "products": len(products),
             "extension": ext_blocks is not None,
             "capabilities": sorted(body.get("active_capabilities", {}))}))

        if ext_blocks is None and extension:
            steps.append(Step(
                Phase.NEGOTIATION, Outcome.DEGRADED,
                f"{merchant} does not publish the benefit extension - it is ranked on shelf price alone.",
                {"merchant": merchant}))

        # blocks are positional, one per product, but each carries sku_id
        by_sku = {b.get("sku_id"): b for b in (ext_blocks or [])}

        merchant_id = body.get("business", {}).get("id", merchant)

        for product in products:
            sku_id = product.get("id")
            shelf = _decimal(product.get("price", {}).get("amount", "0"))
            block = by_sku.get(sku_id, {})
            records = block.get("records", [])
            any_records = any_records or bool(records)

            # Rebuild the wire into what the valuation takes. `entries` keeps
            # each SignedRecord bound to the envelope it came from, so the
            # caller's own verifier decides what verified.
            sku = _wire_sku(product, merchant_id)
            wire_skus[sku.sku_id] = sku
            entries: dict[int, dict] = {}
            signed_records: list[SignedRecord] = []
            unreadable: list[dict] = []
            for entry in records:
                rebuilt = _wire_record(entry, block.get("issuer"))
                if rebuilt is None:
                    unreadable.append(entry)
                    continue
                entries[id(rebuilt)] = entry
                signed_records.append(rebuilt)

            cost = DeterministicValuation(
                _WireVerifier(verify, entries),
                merchant_domains=MERCHANT_DOMAINS,
                satisfied_conditions=ATTESTED_CONDITIONS,
            ).effective_cost(sku, signed_records, shopper)

            verified = [e for r, e in ((r, entries[id(r)]) for r in signed_records)
                        if not verifier_missing and verify(e)]
            for rebuilt in signed_records:
                if not verifier_missing and verify(entries[id(rebuilt)]):
                    verified_signed.setdefault(rebuilt.record.record_id, rebuilt)

            citations = []
            for line, rebuilt in zip(cost.credited, signed_records):
                entry = entries[id(rebuilt)]
                cited = not verifier_missing and bool(verify(entry))
                credit = line.credited_aud if value_of is None else value_of(entry)
                citations.append({
                    "record_id": line.record_id,
                    "benefit_type": line.benefit_type.value,
                    "credited": f"{credit:.2f}",
                    "cited": cited,
                    # The valuation's own reason, not a restatement of it.
                    "why": line.reason,
                })
            for entry in unreadable:
                citations.append({
                    "record_id": (entry.get("record") or {}).get("record_id"),
                    "benefit_type": "unknown", "credited": "0.00", "cited": False,
                    "why": "Record could not be read from the wire; credited $0",
                })

            valued = (
                cost.total_credited if value_of is None
                else sum((Decimal(c["credited"]) for c in citations), Decimal("0"))
            )

            credited_total, unusable = realisable_credit(valued, shelf)
            withheld_note = None
            if not records:
                withheld_note = "no machine-readable offer published"
            elif unusable > 0:
                withheld_note = (
                    f"${unusable:.2f} of verified benefit exceeds the ${shelf:.2f} "
                    "shelf price and cannot be realised on this listing"
                )

            ranked.append(Ranked(
                merchant=merchant_id,
                sku_id=sku_id, title=product.get("title", ""),
                shelf_price=shelf, credited=credited_total,
                effective_cost=shelf - credited_total,
                records_seen=len(records), records_verified=len(verified),
                records_credited=sum(1 for c in citations if c["cited"] and c["credited"] != "0.00"),
                citations=citations,
                withheld_note=withheld_note,
            ))

    # --- verification / valuation honesty ---------------------------------
    if verifier_missing:
        steps.append(Step(
            Phase.VERIFICATION, Outcome.ABSENT,
            "No signature verifier wired - every record is treated as unverified and credited nothing.",
            {"rule": "fail closed"}))
    if not any_records:
        steps.append(Step(
            Phase.VALUATION, Outcome.DEGRADED,
            "No benefit records were published by any merchant, so effective cost equals shelf price.",
            {"rule": "nothing credited without a record"}))

    # --- resolution -------------------------------------------------------
    #
    # Why each offer matches, clause by clause. This never filters and never
    # reorders: the ranking below is computed from effective cost exactly as it
    # was before this block existed. It only attaches, to each offer the wire
    # returned, the justification the interpreter can give for it.
    #
    # The resolver is handed `verified_signed` and nothing else. A record that
    # did not verify is still *seen* -- it appears in `citations` with
    # `cited: False` and earns nothing -- but it never reaches the resolver, so
    # no unsigned claim can become evidence for anything.
    typed = _typed_constraints(constraints)
    resolved_by_sku: dict[str, Proposal] = {}
    if typed and ranked:
        resolver = resolve or default_resolve
        try:
            proposals = resolver(typed, list(wire_skus.values()),
                                 list(verified_signed.values()))
        except Exception as exc:  # degrade honestly: a ranking without a reason
            steps.append(Step(
                Phase.RESOLVE, Outcome.DEGRADED,
                "The interpreter could not resolve these clauses against the "
                "shelf, so the ranking is shown without its per-clause "
                "justification.",
                {"error": f"{type(exc).__name__}: {exc}"}))
        else:
            resolved_by_sku = {p.sku.sku_id: p for p in proposals}
            ranked = [
                replace(r,
                        resolved=list(resolved_by_sku[r.sku_id].resolved),
                        unsatisfied=list(resolved_by_sku[r.sku_id].unsatisfied))
                if r.sku_id in resolved_by_sku else r
                for r in ranked
            ]

            # Answered *per request*, not per listing: the shopper's question is
            # whether this shelf can answer the clause at all, which is the same
            # reading `scripts/eval_run.py` scores against.
            answered = {
                rc.constraint.text
                for r in ranked for rc in r.resolved if rc.satisfied
            }
            by_record = {
                rc.constraint.text
                for r in ranked for rc in r.resolved
                if rc.satisfied and rc.evidence_record_id is not None
            }
            unanswered = [c for c in typed if c.text not in answered]
            steps.append(Step(
                Phase.RESOLVE, Outcome.OK if not unanswered else Outcome.DEGRADED,
                f"{len(answered)} of {len(typed)} constraints answered; "
                f"{len(by_record)} answered only by a verified record.",
                {"answered": len(answered), "total": len(typed),
                 "by_record": sorted(by_record),
                 "unanswered": [{"text": c.text, "kind": c.kind.value}
                                for c in unanswered],
                 "records_cited": sorted({
                     rc.evidence_record_id
                     for r in ranked for rc in r.resolved
                     if rc.evidence_record_id is not None
                 })}))

    # --- ranking ----------------------------------------------------------
    ranked.sort(key=lambda r: (r.effective_cost, r.shelf_price))
    if ranked:
        top = ranked[0]
        cheapest_shelf = min(ranked, key=lambda r: r.shelf_price)
        flipped = top.sku_id != cheapest_shelf.sku_id
        steps.append(Step(
            Phase.RANKING, Outcome.OK,
            (f"{top.merchant} wins on effective cost {top.effective_cost:.2f} "
             f"despite a higher shelf price than {cheapest_shelf.merchant}."
             if flipped else
             f"{top.merchant} wins on both shelf price and effective cost - no flip."),
            {"winner": top.sku_id, "flipped": flipped,
             "cheapest_shelf": cheapest_shelf.sku_id}))

    # --- bundling ---------------------------------------------------------
    # Composition, not matching, and strictly after the ranking: the bundler is
    # handed the offers the valuation already ordered and only decides which of
    # them belong together. It cannot add a listing, reorder the ranking, or
    # cross a merchant boundary, so nothing above this line can change here.
    bundles: list[Bundle] = []
    if bundler is not None:
        bundles = list(bundler.compose(
            typed, _proposals_from(ranked, wire_skus, resolved_by_sku)))
        if bundles:
            best = bundles[0]
            steps.append(Step(
                Phase.BUNDLE, Outcome.OK,
                (f"Composed a set of {len(best.items)} items from "
                 f"{best.items[0].sku.attributes.get('merchant', 'one merchant')} "
                 f"at a combined shelf price of {best.combined_shelf_price:.2f}."
                 if len(best.items) > 1 else
                 "Nothing on the winning merchant's shelf complements the best "
                 "match, so the set is that one item."),
                {"bundles": len(bundles), "bundle_id": best.bundle_id,
                 "items": [p.sku.sku_id for p in best.items],
                 "combined_shelf_price": f"{best.combined_shelf_price:.2f}",
                 "rationale": best.rationale,
                 "unsatisfied": [c.text for c in best.unsatisfied]}))
        else:
            steps.append(Step(
                Phase.BUNDLE, Outcome.DEGRADED,
                "No set could be composed from these offers - the request names "
                "no product family this bundler has a recipe for.",
                {"bundles": 0}))

    # What no offer on any shelf could answer. The winner's own unsatisfied
    # list is the honest per-offer answer; this is the request-level one, and
    # it is empty when some offer answered every clause.
    answered_anywhere = {rc.constraint.text
                         for r in ranked for rc in r.resolved if rc.satisfied}
    unsatisfied = [{"text": c.text, "kind": c.kind.value}
                   for c in typed if c.text not in answered_anywhere]

    return AgentRun(utterance=utterance, extension_enabled=extension,
                    steps=steps, ranked=ranked, constraints=constraints,
                    unsatisfied=unsatisfied, bundles=bundles)
