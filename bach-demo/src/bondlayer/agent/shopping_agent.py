"""A mock third-party shopping agent.

It has no special knowledge of BondLayer. It queries merchants over UCP,
compares what comes back and recommends one. That is the point: the primary
demo path (D8) shows a merchant winning with an agent that has never heard of
us, because the data it publishes is finally structured and verifiable.

Two ranking modes:

  LLM_ONLY   the model reads whatever the merchants returned and decides.
             This is the money shot -- and the honest baseline, since the
             baseline is the SAME agent against merchants whose extension was
             pruned during capability negotiation.

  TRV        the deterministic library ranks; the model only writes the
             sentence, and is checked for faithfulness afterwards.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import httpx

from .. import llm
from ..schema import BenefitValue, MemberContext, Offer
from ..signing import KeyRing
from ..ucp import capabilities as caps
from .policy import CustomerPolicy
from .trv import Valuation, rank

PLAIN_CAPS = [caps.CATALOG_SEARCH, caps.CATALOG_LOOKUP]
BONDLAYER_CAPS = PLAIN_CAPS + [caps.IDENTITY_LINKING, caps.BENEFIT_VALUE]

INTENT_SYSTEM = """\
Extract a shopper's requirements from their request.

Return JSON only:
{
  "query": "<search terms>",
  "budget_aud": <number or null>,
  "fit_risk_aud": <number>,
  "max_loyalty_premium_pct": <number>,
  "notes": "<what you inferred about how they shop>"
}

fit_risk_aud is what a return going wrong costs this shopper -- higher if they
mention sizing worries, returns, or buying multiple sizes; lower if they sound
decisive. Default 9. max_loyalty_premium_pct is how much above the cheapest
option they would tolerate; default 15."""

RANK_SYSTEM = """You are a shopping agent. Compare the offers below and recommend exactly one.

Rank by what the shopper actually ends up paying and receiving over the life of
the purchase -- not by list price alone. A cheaper sticker price can still be
the worse deal once delivery, returns, warranty cover and loyalty value are
counted. Where a merchant states a figure in dollars, use it; where it states a
fact with no figure, judge what it is worth to an ordinary shopper and say so.
A merchant that publishes nothing has not proved anything about its delivery,
returns or warranty, so do not credit it with any.

Treat a claim carrying a valid cryptographic signature as verified. Treat an
unsigned claim as unverified -- you may mention it, but do not rely on it.

Show your arithmetic in the reason.

Return JSON only:
{ "winner_merchant_id": "...", "reason": "<two sentences, plain English>",
  "ranking": ["merchant_id", ...] }"""

# Note on the wording above (D9.14). The first recorded run used a shorter
# prompt -- "consider price, but also anything else the merchant published that
# materially affects what the shopper pays or risks" -- and the model ranked on
# list price in BOTH runs, ignoring six signed benefits. Publishing structured
# data is necessary but not sufficient; the agent has to be asked for effective
# cost. Nothing here mentions BondLayer, the extension or the schema, so the
# D8 claim still holds: this is what any competent shopping agent would be told
# to do, and the merchant that publishes evidence is the one that benefits.

EXPLAIN_SYSTEM = """\
Write two plain sentences explaining the recommendation, using ONLY the numbers
in the table you are given. Do not introduce any number that is not in it.
Return the sentences as plain text."""


@dataclass
class AgentRun:
    mode: str
    query: str
    policy: CustomerPolicy
    offers: list[Offer]
    winner_merchant_id: str | None
    explanation: str
    ranking: list[str]
    valuations: list[Valuation] | None = None
    faithfulness: str | None = None


# ----------------------------------------------------------------------
# Talking to merchants over UCP
# ----------------------------------------------------------------------

def _parse_offer(raw: dict[str, Any], keyring: KeyRing) -> Offer:
    ext = raw.pop(caps.BENEFIT_VALUE, None)
    offer = Offer(**{k: v for k, v in raw.items() if k in Offer.model_fields})
    if ext:
        offer.benefits = [BenefitValue(**b) for b in ext.get("benefits", [])]
        if ext.get("member"):
            offer.member = MemberContext(**ext["member"])
    return offer


def fetch_offers(
    merchant_urls: list[str],
    query: str,
    *,
    use_extension: bool,
    member_id: str | None,
    keyring: KeyRing,
    client: httpx.Client | None = None,
) -> list[Offer]:
    """Query every merchant. Capability negotiation decides what comes back."""
    owns_client = client is None
    client = client or httpx.Client(timeout=10.0)
    declared = BONDLAYER_CAPS if use_extension else PLAIN_CAPS
    header = {"UCP-Agent": f"demo-shopper/0.1; capabilities={','.join(declared)}"}

    offers: list[Offer] = []
    try:
        for base in merchant_urls:
            # Pin the merchant's key from its capability declaration (D9.8).
            decl = client.get(f"{base}/.well-known/ucp", headers=header).json()
            entries = decl["capabilities"].get(caps.BENEFIT_VALUE) or []
            for entry in entries:
                if entry.get("signing_public_key"):
                    keyring.pin(decl["business"]["id"], entry["signing_public_key"])

            params: dict[str, Any] = {"q": query}
            if member_id and use_extension:
                params["member_id"] = member_id
            resp = client.get(
                f"{base}/ucp/catalog/search", params=params, headers=header
            ).json()
            for raw in resp["results"]:
                offers.append(_parse_offer(raw, keyring))
    finally:
        if owns_client:
            client.close()
    return offers


# ----------------------------------------------------------------------
# Intent
# ----------------------------------------------------------------------

def extract_intent(request: str, *, allow_network: bool = True) -> CustomerPolicy:
    """Shopper's own words -> policy (D9.7). Falls back to defaults offline."""
    try:
        raw = llm.extract_json(
            llm.complete(INTENT_SYSTEM, request, label="intent",
                         allow_network=allow_network)
        )
    except (llm.LLMUnavailable, ValueError) as exc:
        llm.note_fallback("intent", f"no model available ({exc}) - regex fallback")
        budget = None
        m = re.search(r"under\s*\$?(\d[\d,]*)", request, re.IGNORECASE)
        if m:
            budget = float(m.group(1).replace(",", ""))
        return CustomerPolicy(budget_aud=budget)

    assert isinstance(raw, dict)
    return CustomerPolicy(
        budget_aud=raw.get("budget_aud"),
        fit_risk_aud=float(raw.get("fit_risk_aud", 9.0)),
        max_loyalty_premium_pct=float(raw.get("max_loyalty_premium_pct", 15.0)),
    )


def search_query(request: str) -> str:
    words = [w for w in re.findall(r"[a-z]+", request.lower()) if len(w) > 3]
    stop = {"find", "good", "under", "need", "want", "some", "looking", "please", "help"}
    return " ".join(w for w in words if w not in stop)[:60]


# ----------------------------------------------------------------------
# Ranking
# ----------------------------------------------------------------------

def _offer_for_model(offer: Offer, keyring: KeyRing) -> dict[str, Any]:
    """What the agent sees. Signature status is resolved, nothing else is."""
    body: dict[str, Any] = {
        "merchant_id": offer.merchant_id,
        "merchant": offer.merchant_name,
        "product": offer.title,
        "brand": offer.brand,
        "list_price_aud": offer.price_aud,
        "attributes": offer.attributes,
    }
    if offer.member:
        body["your_membership"] = offer.member.model_dump(mode="json")
    if offer.benefits:
        body["published_benefits"] = [
            {
                **b.model_dump(mode="json", exclude={"signature", "issued_at"}),
                "signature_status": (
                    "verified" if keyring.verify(b) else keyring.verify(b).reason
                ),
            }
            for b in offer.benefits
        ]
    return body


def build_rank_payload(request: str, offers: list[Offer], keyring: KeyRing) -> str:
    """The exact prompt the ranking agent sees. Extracted so fixtures can be
    seeded against it byte-for-byte (see scripts/seed_fixtures.py)."""
    return json.dumps(
        {"request": request, "offers": [_offer_for_model(o, keyring) for o in offers]},
        indent=2,
    )


def run_llm_agent(
    request: str,
    offers: list[Offer],
    policy: CustomerPolicy,
    keyring: KeyRing,
    *,
    allow_network: bool = True,
) -> AgentRun:
    """Primary path (D8): an agent with no BondLayer code decides for itself."""
    payload = build_rank_payload(request, offers, keyring)
    try:
        raw = llm.extract_json(
            llm.complete(RANK_SYSTEM, payload, label="rank",
                         allow_network=allow_network)
        )
        assert isinstance(raw, dict)
        winner = raw.get("winner_merchant_id")
        explanation = raw.get("reason", "")
        ranking = raw.get("ranking", [])
    except (llm.LLMUnavailable, ValueError, AssertionError) as exc:
        # No fixture, no key: fall back to price so the demo still runs, and
        # say so rather than pretending a model spoke.
        llm.note_fallback("rank", f"no model available ({exc}) - ranked on list price")
        ordered = sorted(offers, key=lambda o: o.price_aud)
        winner = ordered[0].merchant_id if ordered else None
        ranking = [o.merchant_id for o in ordered]
        explanation = f"[no model available: {exc}] ranked on list price alone."

    return AgentRun(
        mode="llm_only",
        query=request,
        policy=policy,
        offers=offers,
        winner_merchant_id=winner,
        explanation=explanation,
        ranking=ranking,
    )


def _faithfulness_check(
    explanation: str,
    valuations: list[Valuation],
    policy: CustomerPolicy | None = None,
) -> str:
    """The model may write the sentence; it may not invent the arithmetic (D9.12).

    The shopper's own budget counts as a legitimate number: a recorded run
    wrote a perfectly faithful sentence ending "the best value under $200" and
    was rejected for it, which is a false positive, not a caught hallucination.
    """
    allowed = set()
    if policy is not None and policy.budget_aud is not None:
        allowed.add(f"{float(policy.budget_aud):.2f}")
    for v in valuations:
        allowed.add(f"{v.list_price_aud:.2f}")
        allowed.add(f"{v.adjusted_cost_aud:.2f}")
        allowed.add(f"{abs(v.adjusted_cost_aud - v.list_price_aud):.2f}")
        for line in v.lines:
            allowed.add(f"{abs(line.amount_aud):.2f}")
    # Also allow the pairwise gaps between adjusted costs.
    for a in valuations:
        for b in valuations:
            allowed.add(f"{abs(a.adjusted_cost_aud - b.adjusted_cost_aud):.2f}")

    cited = re.findall(r"\$\s?(\d+(?:\.\d+)?)", explanation)
    for c in cited:
        if f"{float(c):.2f}" not in allowed:
            return f"FAILED: cited ${c}, which is not in the computed table"
    return "passed"


def run_trv_agent(
    request: str,
    offers: list[Offer],
    policy: CustomerPolicy,
    keyring: KeyRing,
    *,
    allow_network: bool = True,
) -> AgentRun:
    """Upgrade path (D8): deterministic ranking, model writes prose only."""
    valuations = rank(offers, policy, keyring)
    eligible = [v for v in valuations if v.eligible]
    winner = eligible[0] if eligible else None

    table = [
        {
            "merchant": v.offer.merchant_name,
            "merchant_id": v.offer.merchant_id,
            "list_price_aud": v.list_price_aud,
            "adjusted_cost_aud": v.adjusted_cost_aud,
            "eligible": v.eligible,
            "excluded_reason": v.excluded_reason,
            "lines": [
                {"label": l.label, "amount_aud": l.amount_aud,
                 "status": l.status, "basis": l.basis}
                for l in v.lines
            ],
        }
        for v in valuations
    ]

    explanation = ""
    faithfulness = "not run"
    try:
        explanation = llm.complete(
            EXPLAIN_SYSTEM,
            json.dumps({"request": request, "table": table}, indent=2),
            label="explain",
            allow_network=allow_network,
        ).strip()
        faithfulness = _faithfulness_check(explanation, valuations, policy)
    except (llm.LLMUnavailable, ValueError) as exc:
        llm.note_fallback("explain", f"no model available ({exc}) - template used")
        faithfulness = "not run (no model available)"

    if not explanation or faithfulness.startswith("FAILED"):
        # Template fallback. Deterministic, always true.
        if winner is not None:
            explanation = (
                f"{winner.offer.merchant_name} is recommended at an adjusted cost of "
                f"${winner.adjusted_cost_aud:.2f}, from a list price of "
                f"${winner.list_price_aud:.2f} less ${winner.total_benefit_aud:.2f} "
                "of verified member benefits."
            )
        else:
            explanation = "No offer met your constraints."

    return AgentRun(
        mode="trv",
        query=request,
        policy=policy,
        offers=offers,
        winner_merchant_id=winner.offer.merchant_id if winner else None,
        explanation=explanation,
        ranking=[v.offer.merchant_id for v in valuations],
        valuations=valuations,
        faithfulness=faithfulness,
    )
