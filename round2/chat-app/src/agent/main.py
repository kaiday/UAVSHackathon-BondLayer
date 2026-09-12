"""The mock shopping agent.

A fixed pipeline with the model at two bounded points -- intent parse and
ranking. The orchestration is ours, so the fan-out is identical in both switch
states and the only thing that varies is what came back on the wire.

The model reasons over the **verified terms** and decides for itself what they
are worth. We do not compute an "effective cost" for it, and we do not compute
one at all: assigning a warranty a dollar figure and subtracting it from the
shelf price invents a number the merchant never offered, and the comparison it
produces is ambiguous rather than persuasive.

What runs alongside is an *audit*, not a valuation: which records verified,
which were ignored, and why. That is the fact the protocol establishes. What
those facts are worth is the agent's judgement, and the demo's claim is that
the agent can now make it on evidence rather than on price alone.

Run it::

    python -m uvicorn src.agent.main:app --host 127.0.0.1 --port 8001 --reload
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

CHAT_APP = Path(__file__).resolve().parents[2]
STATIC_DIR = Path(__file__).parent / "static"
sys.path.insert(0, str(CHAT_APP.parent))

load_dotenv(CHAT_APP / ".env")

from . import llm, ucp_client
from .ucp_client import Offer

app = FastAPI(
    title="BondLayer agent service",
    description="A neutral shopping agent that speaks UCP.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


#: The agent has **no knowledge of BondLayer**. It is told that merchants may
#: attach structured data to a listing and that it should weigh it -- which is
#: what any real shopping agent's prompt would say -- and nothing more. That
#: neutrality is what makes the before/after admissible evidence.
AGENT_SYSTEM_PROMPT = """You are a shopping agent acting for a customer. You compare \
offers from several merchants and pick the one that serves the customer best.

Some merchants attach additional structured terms to a listing beyond its price: \
warranty length, shipping terms, repair commitments. Each carries a cryptographic \
signature that has already been checked for you, and the data tells you whether it \
verified.

Most of these terms are facts, not prices. A 24-month warranty against a statutory \
12 is a real difference, but it has no exchange rate against a lower shelf price -- \
do not invent one. Judge what the terms are worth to this customer as a person would: \
how long they will keep the thing, what failure would cost them, whether a waived \
delivery fee matters at this price. A term that is merely the legal minimum is not an \
advantage.

A claim that did not verify is not evidence. It must not move your ranking, however \
large the number attached to it. The same is true of a claim marked \
`applies_to_this_listing: false` -- it may be perfectly genuine and still not apply \
at this price, and a discount the customer cannot actually obtain is worth zero. Say \
so plainly when a headline offer fails its own conditions; it is useful information \
about the merchant.

Some benefits carry `restricted_value_ceiling_aud` instead of `cash_value_aud`. That \
is money the customer can only spend back at the same merchant, and it usually \
expires. Treat it as worth materially less than the same figure in cash, never as \
equal to it, and tell the customer what you discounted it to and why. Do not add it \
to a price comparison as though it were a discount.

Be neutral and concrete. Never invent a benefit that is not in the data you were \
given, and be willing to prefer the cheaper offer when the extra terms do not earn \
their premium."""


class ShoppingQuery(BaseModel):
    query: str
    bondlayer_enabled: bool = True
    #: Seeded in data/members.json. shopper-001 is an existing Voltway Circle
    #: member; shopper-002 is a prospect there. Any other id is a stranger to
    #: every merchant and sees only the universal records, which is also the
    #: correct behaviour rather than a gap.
    shopper_id: str = "shopper-001"
    consent: bool = True


def _offer_payload(offer: Offer) -> dict:
    """What the model sees. Raw records, no computed valuation."""
    return {
        "merchant": offer.merchant,
        "sku_id": offer.sku_id,
        "title": offer.title,
        "shelf_price_aud": offer.shelf_price_aud,
        "availability": offer.availability,
        "description": offer.description,
        "attached_claims": [
            {
                "type": r.benefit_type,
                "terms": r.terms,
                # Present only where the benefit really is money the shopper does
                # not pay. Absent means "not a monetary benefit", not "worthless".
                **({"cash_value_aud": r.cash_value_aud} if r.cash_value_aud else {}),
                # Present instead where the benefit has a dollar figure that is
                # not fungible cash. Named to make it hard to add to the price.
                **(
                    {"restricted_value_ceiling_aud": r.ceiling_aud}
                    if r.state == "verified_restricted"
                    else {}
                ),
                "signature_verified": r.verified,
                "applies_to_this_listing": r.state
                not in ("ineligible", "shopper_mismatch"),
                "assessment": r.reason,
                "quoted_from_merchant_policy": r.source_span,
            }
            for r in offer.records
        ],
    }


def _audit(offer: Offer) -> dict:
    """What the protocol established, independently of what the model concluded.

    This is deliberately **not** a valuation. We used to compute an "effective
    cost" by assigning each benefit a dollar figure and subtracting it from the
    shelf price; that number was fiction. A 24-month warranty is not $18 off. The
    audit's job is to state what verified and what did not -- the facts the agent
    was entitled to rely on -- and leave the worth of those facts to the agent.

    The one place money still appears is a fee the shopper genuinely does not pay.
    """
    by_state: dict[str, list] = {}
    for r in offer.records:
        by_state.setdefault(r.state, []).append(r)

    verified_cash = by_state.get("verified_monetary", [])
    restricted = by_state.get("verified_restricted", [])
    verified_facts = by_state.get("verified_fact", [])
    # Three different ways to be worth nothing, and collapsing them would lose
    # the argument. An unsigned claim was never evidence; an ineligible one is
    # true and simply does not apply here; a mismatched one was signed about
    # somebody else. Each earns zero for a different reason and the reason is
    # the interesting part.
    earns_nothing = (
        by_state.get("unverified", [])
        + by_state.get("ineligible", [])
        + by_state.get("shopper_mismatch", [])
    )

    return {
        "sku_id": offer.sku_id,
        "merchant": offer.merchant,
        "title": offer.title,
        "shelf_price_aud": offer.shelf_price_aud,
        "verified_fact_count": len(verified_facts),
        "verified_facts": [
            {"benefit_type": r.benefit_type, "terms": r.terms} for r in verified_facts
        ],
        # Cash the shopper does not pay: waived fees and signed rate discounts.
        # This is the only figure we subtract from a price, and every term in it
        # traces to a signature over an amount or a rate.
        "verified_cash_aud": round(sum(r.cash_value_aud or 0 for r in verified_cash), 2),
        # Kept under its old name so nothing downstream breaks on the rename.
        "verified_fees_waived_aud": round(sum(r.cash_value_aud or 0 for r in verified_cash), 2),
        # Deliberately a separate line item. Store credit belongs nowhere near
        # the cash total, and an audit that summed the two would be lying by
        # layout even if every individual number were correct.
        "restricted_value_ceiling_aud": round(sum(r.ceiling_aud or 0 for r in restricted), 2),
        "restricted_value_notes": [
            {"benefit_type": r.benefit_type, "terms": r.terms, "why": r.reason}
            for r in restricted
        ],
        "ignored_count": len(earns_nothing),
        "ignored": [
            {
                "benefit_type": r.benefit_type,
                "state": r.state,
                "claimed_aud": r.cash_value_aud or r.ceiling_aud,
                "reason": r.reason,
            }
            for r in earns_nothing
        ],
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "agent", "model": llm.DEFAULT_MODEL}


@app.get("/merchant-health")
def merchant_health() -> dict:
    """Whether the merchant service is reachable.

    The UI shows this, because "the agent returned nothing" and "the merchant is
    down" look identical otherwise.
    """
    import httpx

    try:
        response = httpx.get(f"{ucp_client.MERCHANT_BASE_URL}/health", timeout=3)
        return {"reachable": response.status_code == 200, **response.json()}
    except Exception as exc:  # noqa: BLE001 - any failure means "not reachable"
        return {"reachable": False, "error": str(exc)}


@app.get("/", include_in_schema=False)
def index():
    """A no-build fallback UI, so the demo runs on a machine without Node."""
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/query")
def handle_query(request: ShoppingQuery) -> dict:
    steps: list[dict] = []
    header = ucp_client.agent_header(request.bondlayer_enabled)

    steps.append(
        {
            "step": "declare",
            "detail": "Agent declares the capabilities it understands. This is the switch: "
            "with BondLayer off, one capability is simply not declared.",
            "ucp_agent_header": header,
            "bondlayer_declared": request.bondlayer_enabled,
        }
    )

    # (1) intent parse -- live model call
    intent = llm.complete_json(
        "intent_parse",
        "You extract shopping constraints. Reply with JSON only.",
        f'Extract the shopping constraints from this request: "{request.query}"\n\n'
        'Reply as JSON: {"summary": "...", "category": "...", '
        '"max_price_aud": number or null, "must_have": ["..."]}',
    )
    if intent is None:
        intent = {
            "summary": request.query,
            "category": None,
            "max_price_aud": None,
            "must_have": [],
        }
    steps.append(
        {"step": "intent_parse", "detail": "Model decoded the request.", "intent": intent}
    )

    # (2) identity over UCP, consent-gated
    identity = ucp_client.link_identity(
        request.shopper_id, request.consent, request.bondlayer_enabled
    )
    steps.append(
        {
            "step": "identity",
            "detail": "Shopper identity fetched over UCP identity_linking. "
            "Without consent the merchant returns nothing about the shopper.",
            "consent_given": request.consent,
            "responses": identity,
        }
    )

    # (3) fan-out -- identical in both switch states
    #
    # Consent decides whether the id goes on the wire at all. Withheld, we send
    # nothing, the merchant has nothing to resolve, and the shopper-specific
    # records are absent from the response instead of being received and hidden.
    offers, exchanges = ucp_client.fan_out(
        request.query,
        request.bondlayer_enabled,
        request.shopper_id if request.consent else None,
    )
    steps.append(
        {
            "step": "fan_out",
            "detail": f"Queried {len(ucp_client.MERCHANTS)} merchants over UCP. "
            "Same merchants, same query, both switch states.",
            "exchanges": [asdict(e) for e in exchanges],
        }
    )

    if not offers:
        return {
            "user_query": request.query,
            "bondlayer_enabled": request.bondlayer_enabled,
            "ucp_agent_header": header,
            "intent": intent,
            "results": [],
            "final_recommendation": "No merchant returned a matching listing.",
            "evidence_log": steps,
            "audit": [],
            "transcript": llm.transcript_payload(),
        }

    # (4) ranking -- live model call over raw records
    payload = [_offer_payload(o) for o in offers]
    ranking = llm.complete_json(
        "rank",
        AGENT_SYSTEM_PROMPT,
        f'The customer asked: "{request.query}"\n\n'
        f"Offers:\n{json.dumps(payload, indent=2)}\n\n"
        "Rank every offer from best to worst for this customer. Decide for yourself "
        "what the attached terms are worth to them -- most are facts, not prices, and "
        "there is no exchange rate between a longer warranty and a lower price. Say "
        "which terms moved your decision and which you discounted.\n\n"
        "Reply as JSON:\n"
        '{"ranking": [{"rank": 1, "sku_id": "...", "merchant": "...", '
        '"decisive_terms": ["the verified terms that actually moved this offer up or '
        'down, or [] if price alone decided it"], '
        '"reasoning": "one or two sentences"}], '
        '"recommendation": "one short paragraph to the customer"}',
    )
    if ranking is None:
        ranking = {
            "ranking": [],
            "recommendation": "The model did not return a usable ranking.",
        }
    steps.append(
        {
            "step": "rank",
            "detail": "Model ranked the offers from the verified terms and decided "
            "for itself what they are worth. No effective cost was computed for it.",
            "model": llm.DEFAULT_MODEL,
        }
    )

    by_sku = {o.sku_id: o for o in offers}
    results = []
    for row in ranking.get("ranking", []):
        offer = by_sku.get(row.get("sku_id"))
        if offer is None:
            continue
        results.append(
            {
                "rank": row.get("rank"),
                "merchant": offer.merchant,
                "sku_id": offer.sku_id,
                "title": offer.title,
                "shelf_price_aud": offer.shelf_price_aud,
                "agent_decisive_terms": row.get("decisive_terms", []),
                "reasoning": row.get("reasoning", ""),
                "records": [asdict(r) for r in offer.records],
            }
        )
    results.sort(key=lambda r: r["rank"] if isinstance(r["rank"], int) else 999)

    # (5) independent audit -- deterministic, never shown to the model
    audit = [_audit(by_sku[r["sku_id"]]) for r in results]
    steps.append(
        {
            "step": "audit",
            "detail": "What the protocol established, independently of the model: "
            "which records verified and which were ignored. Not a valuation -- we do "
            "not convert a warranty into a discount.",
            "audit": audit,
        }
    )

    record_states = [
        {"sku_id": offer.sku_id, **asdict(r)} for offer in offers for r in offer.records
    ]
    steps.append(
        {
            "step": "record_states",
            "detail": "Every record served, in one of three states: verified and "
            "monetary (a fee not paid), verified fact (true, worth whatever the agent "
            "judges), unverified (displayed, never cited).",
            "records": record_states,
        }
    )

    return {
        "user_query": request.query,
        "bondlayer_enabled": request.bondlayer_enabled,
        "ucp_agent_header": header,
        "intent": intent,
        "results": results,
        "final_recommendation": ranking.get("recommendation", ""),
        "evidence_log": steps,
        "audit": audit,
        "transcript": llm.transcript_payload(),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.agent.main:app", host="127.0.0.1", port=8001, reload=True)
