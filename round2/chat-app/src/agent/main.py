"""The buyer-agent stand-in.

**Not a consumer product** -- a stand-in for the agent side of the protocol,
so the demo can show what a real UCP shopping agent would see and do.

Ranking is deterministic, always: ``bondlayer.agent.composition.run_request``
computes effective cost from records that actually verified, over the same
merchant server (``bondlayer/``, on :8000) the trace CLI in
``bondlayer/scripts/trace_run.py`` runs against. This process never runs its
own merchant, its own data, or its own valuation -- there is one of each, in
``bondlayer/``.

The one place a model appears is ``llm.narrate``: one paragraph of prose
*after* the ranking is already decided, template-only when no key is
configured, and never able to change a winner (D4).

Run it::

    BONDLAYER_MERCHANT_URL=http://127.0.0.1:8000 \\
        python -m uvicorn src.agent.main:app --host 127.0.0.1 --port 8001
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

CHAT_APP = Path(__file__).resolve().parents[2]
STATIC_DIR = Path(__file__).parent / "static"
sys.path.insert(0, str(CHAT_APP.parent))

load_dotenv(CHAT_APP / ".env")

from bondlayer.agent import run_request
from bondlayer.agent.merchant_decode import merchant_decode_step, run_with_merchant_decode
from bondlayer.agent.trace import AgentRun
from bondlayer.bundle import CategoryBundler, bundle_payload

from . import llm, ucp_client

app = FastAPI(
    title="BondLayer agent service",
    description="Buyer-agent stand-in -- not a consumer product.",
    version="0.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ShoppingQuery(BaseModel):
    query: str
    bondlayer_enabled: bool = True


def _audit(run: AgentRun) -> list[dict]:
    """What the protocol established, independently of any model: which
    records verified, which were ignored, and why. Kept, and returned
    alongside the deterministic ranking (D1) -- never instead of it.

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


def _fetcher():
    return ucp_client.make_fetcher(
        httpx.Client(base_url=ucp_client.MERCHANT_BASE_URL, timeout=10,
                     params={"limit": PAGE}),
    )


@app.post("/query")
def handle_query(request: ShoppingQuery) -> dict:
    fetch = _fetcher()
    verify = ucp_client.make_verifier()

    # ``run_request`` unchanged, then the shopper's sentence goes to every
    # merchant that negotiated ``org.bondlayer.intent_match`` and each one's
    # own decode and proposals come back as one more trace step. The merchant's
    # reading is shown NEXT TO the agent's, never instead of it, and nothing in
    # ``ranked`` is computed from it.
    run = run_with_merchant_decode(
        request.query,
        ucp_client.MERCHANTS,
        fetch,
        propose=ucp_client.make_proposer(),
        extension=request.bondlayer_enabled,
        verify=verify,
        policy=ucp_client.POLICY,
        # Composition, after the ranking. The bundler cannot add a listing,
        # change a price or reorder the ranking -- everything above stays
        # exactly what it was before bundling existed (D1: the deterministic
        # ranking is never replaced, only added to).
        bundler=CategoryBundler(),
        **ucp_client.interpret_kwargs(run_request),
    )

    steps = [
        {"phase": s.phase.value, "outcome": s.outcome.value, "summary": s.summary, "detail": s.detail}
        for s in run.steps
    ]
    prose = llm.narrate(run)
    steps.append({"phase": "prose", "outcome": prose["source"], "summary": prose["note"], "detail": {}})

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
    flipped = bool(winner and cheapest_shelf and winner["sku_id"] != cheapest_shelf["sku_id"])

    return {
        "user_query": request.query,
        "bondlayer_enabled": request.bondlayer_enabled,
        "ucp_agent_header": ucp_client.agent_header(request.bondlayer_enabled),
        "constraints": run.constraints,
        "steps": steps,
        "ranked": ranked,
        "winner": winner,
        "cheapest_shelf": cheapest_shelf,
        "flipped": flipped,
        "recommendation": prose["text"],
        # The set, best first. Each item carries its own notes, because the
        # bundle's rationale deliberately says nothing about why any individual
        # item fits -- that is already written on the item.
        "bundles": [bundle_payload(b) for b in run.bundles],
        # What each merchant understood and proposed when handed the sentence
        # itself (POST /ucp/intent/propose), with a clause-by-clause agreement
        # check against ``constraints`` above. Additive; ``ranked`` never reads it.
        "merchant_decodes": merchant_decodes,
        "audit": _audit(run),
        "transcript": llm.transcript_payload(),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.agent.main:app", host="127.0.0.1", port=8001, reload=True)
