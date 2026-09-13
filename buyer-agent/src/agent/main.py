"""The shopping agent.

In live mode the model decodes the shopper's sentence, decides the
ranking, and it carries the conversation. ``bondlayer`` still does everything
that must not be guessed at: the UCP fan-out, signature verification, record
citation, the merchant's own decode, bundling and checkout. What it no longer
does here is pick the winner.

Deterministic effective costs are still computed and displayed as reference
figures, but the live winner is the model's pick. Explicit rules mode uses the
reference parser and ranking without making provider calls.

This process still never runs its own merchant, its own data or its own
signing keys -- there is one of each, in ``bondlayer/``.

Run it::

    BONDLAYER_MERCHANT_URL=http://127.0.0.1:8000 \\
        python -m uvicorn src.agent.main:app --host 127.0.0.1 --port 8001
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from decimal import Decimal

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field, field_validator

CHAT_APP = Path(__file__).resolve().parents[2]
STATIC_DIR = Path(__file__).parent / "static"
sys.path.insert(0, str(CHAT_APP.parent))

from bondlayer import ai
from bondlayer.types import BenefitType, Constraint, ConstraintKind
from bondlayer.agent.close_loop import close_loop, close_loop_step, record_unreachable
from bondlayer.agent.merchant_decode import merchant_decode_step, run_with_merchant_decode
from bondlayer.agent.trace import AgentRun
from bondlayer.bundle import CategoryBundler, bundle_payload

from . import llm, rank, ucp_client

app = FastAPI(
    title="BondLayer agent service",
    description="A shopping agent over UCP, with the model deciding the ranking.",
    version="0.4.0",
)


@app.exception_handler(ai.AIError)
async def ai_error(_request, exc: ai.AIError):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc), "provider": "openai"})

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ShoppingQuery(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    bondlayer_enabled: bool = True
    #: Unset means no identity is sent; live anonymous requests assume no membership.
    shopper_id: str | None = Field(default=None, max_length=200)
    values_aud: dict[BenefitType, Decimal] = Field(default_factory=dict)

    @field_validator("values_aud")
    @classmethod
    def valid_values(cls, values):
        if any(not value.is_finite() or value < 0 for value in values.values()):
            raise ValueError("Benefit values must be finite non-negative AUD amounts")
        return values

    @field_validator("query")
    @classmethod
    def nonblank_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be blank")
        return value.strip()


def _audit(run: AgentRun) -> list[dict]:
    """What the protocol established, independently of any model: which
    records verified, which were ignored, and why. Kept, and returned
    alongside the ranking -- never instead of it.

    Built straight from ``Ranked.citations``, which ``run_request`` already
    populates with exactly this breakdown per offer: cited-and-credited,
    cited-and-zero (a values claim, valid but never priced), or not cited at
    all (unverified -- displayed, never valued).
    """
    out = []
    for r in run.ranked:
        verified = [c for c in r.citations if c["cited"]]
        ignored = [c for c in r.citations if not c["cited"]]
        out.append({
            "sku_id": r.sku_id,
            "merchant": r.merchant,
            "title": r.title,
            "shelf_price_aud": str(r.shelf_price),
            "credited_aud": str(r.credited),
            "effective_cost_aud": str(r.effective_cost),
            "verified_count": len(verified),
            "verified": verified,
            "ignored_count": len(ignored),
            "ignored": ignored,
        })
    return out


def _resolved_payload(offer) -> list[dict]:
    """Why this offer matches, one entry per clause the shopper said.

    The shape matches ``bundle_payload``'s ``notes``/``resolved``, with the
    catalogue attribute added, so the UI has one renderer for both.

    This is what the UI used to guess at. It carried a keyword table that
    mapped "return" to ``free_returns`` and then looked for a citation of that
    type -- a rendering layer inventing the binding between a clause and the
    record answering it, which is exactly the "logic implied, not logic
    visible" failure the trace module warns about. The binding is the
    resolver's, and ``note`` is the resolver's sentence, not a restatement.
    """
    return [
        {
            "text": r.constraint.text,
            "kind": r.constraint.kind.value,
            "satisfied": r.satisfied,
            "evidence_record_id": r.evidence_record_id,
            "evidence_attribute": r.evidence_attribute,
            "note": r.note,
        }
        for r in offer.resolved
    ]


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "agent"}


@app.get("/merchant-health")
def merchant_health() -> dict:
    return ucp_client.merchant_health()


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/onboarding", include_in_schema=False)
def onboarding():
    return RedirectResponse(ucp_client.MERCHANT_BASE_URL.rstrip("/") + "/console/onboarding/")


#: ``catalog.search`` defaults to 20 results and caps at 100. Twenty silently
#: truncates a 149-row catalogue, and bundling is where that shows: "a work
#: laptop and a dock" sends no category (two product nouns widen the filter, so
#: the agent does the filtering), and every accessory falls off the end of page
#: one -- the set comes back as a laptop on its own. Set as a client-level
#: default so it rides every search without reaching into the fetcher.
#:
#: NOTE for Nguyen: this belongs in ``ucp_client._params_from_plan``, next to
#: the other query parameters, exactly as ``bondlayer/scripts/trace_run.py``
#: now does it. It is here only because WS-G's brief does not name
#: ``ucp_client.py``.
PAGE = 100


def _http_client():
    return httpx.Client(base_url=ucp_client.MERCHANT_BASE_URL, timeout=100)


def _sanitise(exc: Exception) -> str:
    """The failure, named by type and nothing else.

    A provider error can carry the prompt, a key fragment or a raw upstream
    body. The type is enough to debug from with the server log open, and is
    safe to put on a screen that is being projected.
    """
    return f"The agent could not complete this request ({type(exc).__name__})."


def _fetcher(http: httpx.Client, plan_override: dict | None = None,
             shopper_id: str | None = None):
    """The UCP fetcher, with the model's decode preferred over the interpreter's.

    ``run_request`` still computes its own typed plan and still passes it; where
    the model named a category or a ceiling those win, and the interpreter's
    plan backfills whatever the model left empty. A model that returns nothing
    usable therefore degrades to the old search rather than to no search.
    """
    base = ucp_client.make_fetcher(http, shopper_id=shopper_id)
    if not plan_override:
        return base

    # A caller may substitute a fetcher that predates typed plans (the tests do
    # exactly that). Wrapping one must not turn "this fetcher ignores plans"
    # into a 502, so ask before passing the argument.
    accepts_plan = "plan" in inspect.signature(base).parameters

    def fetch(merchant: str, query: str, *, extension: bool, plan: dict | None = None) -> dict:
        if not accepts_plan:
            return base(merchant, query, extension=extension)
        merged = dict(plan or {})
        for key, value in plan_override.items():
            if value not in (None, [], ""):
                merged[key] = value
        return base(merchant, query, extension=extension, plan=merged)

    for attr in ("client", "owns_client", "snapshots"):
        if hasattr(base, attr):
            setattr(fetch, attr, getattr(base, attr))
    return fetch


@app.post("/query")
def handle_query(request: ShoppingQuery) -> dict:
    try:
        with _http_client() as http:
            return _handle_query(request, http)
    except httpx.HTTPError as exc:
        raise HTTPException(503, "Merchant service is unavailable. Start it and retry.") from exc
    except (ai.AIError, HTTPException):
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=_sanitise(exc)) from exc


def _handle_query(request: ShoppingQuery, http: httpx.Client) -> dict:
    llm.reset_transcript()
    merchants = ucp_client.discover_merchants(http)
    live = ai.mode() == "openai"

    # (1) decode the sentence -- live model call, and it drives the search below.
    # Skipped entirely when nothing is onboarded: there is nothing to search, and
    # the onboarding prompt should not need a model key to appear.
    if merchants:
        intent = rank.parse_intent(request.query)
    else:
        intent = {"summary": request.query, "category": None, "max_price_aud": None,
                  "must_have": [], "constraints": [], "ai": {"provider": "none"},
                  "note": "no merchants onboarded; nothing decoded"}

    constraints = [Constraint(c["text"], ConstraintKind(c["kind"])) for c in intent["constraints"]]
    decode_meta = intent["ai"]
    fetch = _fetcher(http, rank.plan_from_intent(intent) if merchants else None,
                     shopper_id=request.shopper_id)
    verify = ucp_client.make_verifier(http, merchants=merchants)

    # ``run_request`` unchanged, then the shopper's sentence goes to every
    # merchant that negotiated ``org.bondlayer.intent_match`` and each one's
    # own decode and proposals come back as one more trace step. The merchant's
    # reading is shown NEXT TO the agent's, never instead of it, and nothing in
    # ``ranked`` is computed from it.
    run = run_with_merchant_decode(
        request.query,
        merchants if constraints else [],
        fetch,
        propose=ucp_client.make_proposer(http),
        extension=request.bondlayer_enabled,
        verify=verify,
        policy={kind.value: value for kind, value in request.values_aud.items()} if live else ucp_client.POLICY,
        satisfied_conditions=() if live else None,
        # Bundles are reference compositions; the model subsequently ranks offers.
        bundler=CategoryBundler(),
        interpret=lambda _utterance: constraints,
        enforce_constraints=live,
        merchant_domains=getattr(verify, "merchant_domains", None),
    )
    if run.steps:
        run.steps[0].detail["ai"] = decode_meta
    model_notes = {}
    rank_meta = {"provider": "rules" if not live else "none"}
    # (2) the model ranks. It is handed the shelf price and the verified terms
    # and never the effective cost, so what comes back is its judgement of what
    # the terms are worth rather than its agreement with arithmetic it was shown.
    # ``apply_ranking`` reorders ``run.ranked`` in place, which is why every step
    # below -- the checkout above all -- follows the model's pick.
    if run.ranked and live:
        ranking = rank.rank_offers(request.query, run)
        model_notes = rank.apply_ranking(run, ranking)
        recommendation = ranking.get("recommendation") or ""
        rank_meta = ranking.get("ai", {})
    elif run.ranked:
        recommendation = llm.narrate(run)["text"]
    else:
        # Nothing to rank, so no model call: an empty shelf is not a judgement.
        recommendation = (
            "No merchants have been onboarded. Add a merchant and upload a catalogue to start."
            if not merchants else
            "No merchant returned a matching, priced listing for this request."
        )

    # Step 5: the winning offer becomes an order (POST /ucp/checkout), citing
    # exactly the record ids the agent relied on. Deliberately after the
    # reorder: the offer checked out is the one the model chose.
    # A merchant that cannot be reached at checkout is recorded as a degraded
    # last step, never a 500: the ranking is not the checkout's to lose.
    try:
        close_loop(run, checkout=ucp_client.make_checkout(http), agent_ref="chat-app")
    except httpx.HTTPError as exc:
        record_unreachable(run, exc)

    steps = [
        {"phase": s.phase.value, "outcome": s.outcome.value, "summary": s.summary, "detail": s.detail}
        for s in run.steps
    ]
    steps.insert(0, {"phase": "intent_parse", "outcome": "ok" if merchants else "absent",
                     "summary": ("Model decoded the request." if live else "Explicit rules-mode decode.")
                     if merchants else "No merchants onboarded; no decode called.", "detail": intent})
    if run.ranked:
        steps.append({"phase": "rank" if live else "prose", "outcome": "ok" if live else "template",
                      "summary": f"Model ranked {len(run.ranked)} offer(s) from the verified terms."
                      if live else "Explicit rules mode; no OpenAI call.",
                      "detail": rank_meta})

    ranked = [
        {
            "merchant": r.merchant, "sku_id": r.sku_id, "title": r.title,
            "shelf_price_aud": str(r.shelf_price), "credited_aud": str(r.credited),
            "effective_cost_aud": str(r.effective_cost),
            "records_seen": r.records_seen, "records_verified": r.records_verified,
            "records_credited": r.records_credited,
            "citations": r.citations, "withheld_note": r.withheld_note,
            # The justification, per offer: which clause each record or
            # catalogue column answered, and the resolver's sentence saying
            # why. The UI renders this; it never derives it.
            "resolved": _resolved_payload(r),
            "unsatisfied": [{"text": c.text, "kind": c.kind.value}
                            for c in r.unsatisfied],
            # The model's own account of this offer: the verified terms it says
            # moved the decision, and its sentence. Empty when it did not rank
            # this offer.
            "decisive_terms": model_notes.get((r.merchant, r.sku_id), {}).get("decisive_terms", []),
            "reasoning": model_notes.get((r.merchant, r.sku_id), {}).get("reasoning", ""),
        }
        for r in run.ranked
    ]
    winner = ranked[0] if ranked else None
    cheapest_shelf = min(ranked, key=lambda r: float(r["shelf_price_aud"])) if ranked else None

    # The merchant-decode step's detail, plus its outcome and summary so the
    # page can render the block without hunting through ``steps`` for it.
    decode_step = merchant_decode_step(run)
    merchant_decodes = (
        {**decode_step.detail, "outcome": decode_step.outcome.value,
         "summary": decode_step.summary}
        if decode_step is not None else
        {"kind": "merchant_decode", "merchant_decodes": [], "outcome": "absent",
         "summary": "No merchant-decode step on this run."}
    )
    flipped = bool(winner and cheapest_shelf and (winner["merchant"], winner["sku_id"]) != (cheapest_shelf["merchant"], cheapest_shelf["sku_id"]))

    # The close-loop step's detail -- the request sent, the merchant's order
    # object and its honoured-benefits verdicts -- plus its outcome and summary
    # so the page can render the receipt without hunting through ``steps``.
    order_step = close_loop_step(run)
    order = (
        {**order_step.detail, "outcome": order_step.outcome.value,
         "summary": order_step.summary}
        if order_step is not None else
        {"kind": "close_loop", "order": None, "outcome": "absent",
         "summary": "No close-loop step on this run."}
    )

    request_id = None
    history_error = None
    from bondlayer.ucp.storage import test_data_enabled
    if merchants and (live or not test_data_enabled()):
        from bondlayer.activity import build_report
        try:
            report = build_report(run, merchants, getattr(fetch, "snapshots", {}),
                                  {"intent": decode_meta, "ranking": rank_meta}, order)
            request_id = ucp_client.submit_report(report, http)
        except (httpx.HTTPError, ValueError):
            history_error = "Comparison completed, but the merchant could not save its request report. Check service connectivity and BONDLAYER_SERVICE_TOKEN."

    return {
        "request_id": request_id, "history_error": history_error,
        "user_query": request.query,
        "ai": {"intent": decode_meta, "ranking": rank_meta},
        "ranking_source": "model" if live else "rules",
        "onboarding_required": not merchants,
        # The model's decode of the sentence, which drove the search above.
        "intent": intent,
        "bondlayer_enabled": request.bondlayer_enabled,
        "ucp_agent_header": ucp_client.agent_header(request.bondlayer_enabled),
        "constraints": run.constraints,
        "steps": steps,
        "ranked": ranked,
        "winner": winner,
        "cheapest_shelf": cheapest_shelf,
        "flipped": flipped,
        "recommendation": recommendation,
        # The set, best first. Each item carries its own notes, because the
        # bundle's rationale deliberately says nothing about why any individual
        # item fits -- that is already written on the item.
        "bundles": [bundle_payload(b) for b in run.bundles],
        # What each merchant understood and proposed when handed the sentence
        # itself (POST /ucp/intent/propose), with a clause-by-clause agreement
        # check against ``constraints`` above. Additive; ``ranked`` never reads it.
        "merchant_decodes": merchant_decodes,
        # The loop closed: the winning offer as the merchant confirmed it,
        # with the verdict on every record the agent cited. Additive; the
        # ranking never reads it.
        "order": order,
        "audit": _audit(run),
        "transcript": ([decode_meta] if decode_meta.get("provider") == "openai" else []) + llm.transcript_payload(),
    }


ROUTER_SYSTEM = """You are a shopping agent talking to a customer. Decide what to \
do with the conversation so far.

If the customer has told you enough to go and compare offers -- roughly, what kind \
of thing they want, and any budget or requirement that matters -- choose "search" \
and write the single sentence you would send to the merchants. Fold in everything \
the customer has said across the whole conversation, not just their last message.

If you genuinely cannot search yet, choose "reply" and ask one short question -- the \
one that unblocks you. Do not interrogate the customer; one good question beats \
three. If they are making small talk or asking something that is not a shopping \
request, choose "reply" and just answer them.

Reply as JSON: {"action": "search" or "reply", "utterance": "the sentence to send \
to merchants, when action is search", "reply": "what to say to the customer, when \
action is reply"}"""


class ChatTurn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatTurn]
    bondlayer_enabled: bool = True


@app.post("/chat")
def handle_chat(request: ChatRequest) -> dict:
    """One conversational turn: decide whether to answer or to go shopping.

    Deliberately does not run the search itself. The page shows the A/B --
    BondLayer off beside BondLayer on -- which is two ``/query`` runs, and
    running a third here just to produce the same paragraph would triple the
    model calls behind one message. So this returns the decision, and the page
    spends the runs it actually renders.

    Returns ``{"action", "reply", "utterance"}``: ``action`` is ``"search"``
    (then ``utterance`` is the sentence to send to merchants) or ``"reply"``
    (then ``reply`` is what to say to the customer).
    """
    thread = [{"role": t.role, "content": t.content} for t in request.messages]
    if not thread:
        raise HTTPException(status_code=400, detail="No messages in the conversation.")

    llm.reset_transcript()
    try:
        if ai.mode() == "rules":
            utterance = " ".join(t["content"] for t in thread if t["role"] == "user").strip()
            if not utterance:
                raise HTTPException(status_code=400, detail="No shopper request in the conversation.")
            return {"action": "search", "reply": "", "utterance": utterance,
                    "mode": "rules", "transcript": []}
        decision = llm.complete_json(
            "route",
            ROUTER_SYSTEM,
            "Conversation so far:\n"
            + "\n".join(f'{t["role"]}: {t["content"]}' for t in thread),
        )
        if not isinstance(decision, dict):
            decision = {}

        utterance = str(decision.get("utterance") or "").strip()
        if decision.get("action") == "search" and utterance:
            return {"action": "search", "reply": "", "utterance": utterance,
                    "transcript": llm.transcript_payload()}

        reply = str(decision.get("reply") or "").strip()
        if not reply:
            # The router answered unusably. Rather than inventing a line, let the
            # model speak for itself over the same thread.
            reply = llm.chat("converse", ROUTER_SYSTEM, thread)
        return {"action": "reply", "reply": reply, "utterance": None,
                "transcript": llm.transcript_payload()}
    except (ai.AIError, HTTPException):
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=_sanitise(exc)) from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.agent.main:app", host="127.0.0.1", port=8001, reload=True)
