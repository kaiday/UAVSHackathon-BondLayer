"""Agent-side discovery and comparison over merchant HTTP wires."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import httpx

from agentbridge import loyalty
from agentbridge.models import CustomerPolicy, OfferCard
from agentbridge.merchant_network import Merchant
from agentbridge.ucp import (
    BENEFIT_VALUE,
    CATALOG_LOOKUP,
    CATALOG_SEARCH,
    IDENTITY_LINKING,
)

AGENT_HEADER = (
    "bondlayer-demo/0.1; capabilities="
    f"{CATALOG_SEARCH},{CATALOG_LOOKUP},{IDENTITY_LINKING},{BENEFIT_VALUE}"
)
PLAIN_AGENT_HEADER = f"bondlayer-demo/0.1; capabilities={CATALOG_SEARCH},{CATALOG_LOOKUP}"


@dataclass(frozen=True)
class ConstraintSet:
    query: str
    max_price_cents: int | None = None
    required_power_watts: int | None = None
    required_connector: str | None = None
    required_category: str | None = None
    return_friendly: bool = False


@dataclass(frozen=True)
class MerchantDecision:
    merchant_id: str
    merchant_name: str
    product_id: str
    title: str
    list_price_cents: int
    effective_cost_cents: int
    available: bool
    verified_value_cents: int
    unsigned_penalty_cents: int
    constraints_satisfied: tuple[str, ...]
    constraints_unsatisfied: tuple[str, ...]
    citations: tuple[str, ...]
    verification: tuple[dict[str, Any], ...]
    arithmetic: str
    payload: dict[str, Any]


def parse_constraints(request: str) -> ConstraintSet:
    """Small deterministic interpreter for demo requests.

    This intentionally handles the frozen scenario vocabulary. It provides
    reliable fallback behavior while leaving richer language interpretation to
    an optional model layer.
    """
    text = request.casefold()
    max_price = None
    import re
    match = re.search(r"(?:under|below|less than)\s*(?:aud\s*|\$)?([\d,]+)", text)
    if match:
        max_price = int(match.group(1).replace(",", "")) * 100
        # A bare number after a currency symbol is dollars, not cents.
        if "$" in match.group(0) or "aud" in match.group(0):
            max_price = int(match.group(1).replace(",", "")) * 100
    power = None
    match = re.search(r"(\d+)\s*w", text)
    if match:
        power = int(match.group(1))
    connector = "USB-C" if "usb-c" in text or "usb c" in text else None
    category = "electronics" if any(x in text for x in ("laptop", "charger", "phone", "electronics")) else None
    return ConstraintSet(
        query=request,
        max_price_cents=max_price,
        required_power_watts=power,
        required_connector=connector,
        required_category=category,
        return_friendly=any(x in text for x in ("return", "easy to return", "fit my work")),
    )


def _verify_payload(payload: dict[str, Any], member_email: str | None) -> tuple[Any, list[dict[str, Any]]]:
    block = (payload.get("extensions") or {}).get(BENEFIT_VALUE) or {}
    records = block.get("benefit_records") or block.get("cards") or []
    key = block.get("signing_public_key")
    ring = loyalty.KeyRing()
    issuer = block.get("issuer")
    if issuer and key:
        ring.pin(issuer, key)
    item = payload.get("item") or {}
    offer = payload.get("offer") or {}
    cards: list[OfferCard] = []
    verdicts: list[dict[str, Any]] = []
    from datetime import date
    for raw in records:
        card = OfferCard(**{k: v for k, v in raw.items() if k not in ("verified", "verification")})
        cards.append(card)
        valid, reason = ring.verify(card, today=date.today().isoformat())
        verdicts.append({"card_id": card.card_id, "verified": valid, "reason": reason})
    member = loyalty.find_member(member_email) if member_email else None
    quote = loyalty.value_cards(
        member,
        int(offer.get("total_cents", 0)),
        item.get("category"),
        cards=cards,
        public_key_hex=key or loyalty.PUBLIC_KEY_HEX,
    ) if records else None
    return quote, verdicts


def _match_constraints(payload: dict[str, Any], constraints: ConstraintSet) -> tuple[list[str], list[str], list[str]]:
    item = payload.get("item") or {}
    attrs = item.get("attributes") or {}
    offer = payload.get("offer") or {}
    satisfied: list[str] = []
    unsatisfied: list[str] = []
    citations: list[str] = []
    if constraints.max_price_cents is not None:
        if int(offer.get("total_cents", 0)) <= constraints.max_price_cents:
            satisfied.append("budget")
            citations.append(f"offer.total_cents={offer.get('total_cents')}")
        else:
            unsatisfied.append("budget")
    if constraints.required_power_watts is not None:
        if attrs.get("power_watts") == constraints.required_power_watts:
            satisfied.append("power")
            citations.append(f"item.attributes.power_watts={attrs.get('power_watts')}")
        else:
            unsatisfied.append("power")
    if constraints.required_connector is not None:
        if str(attrs.get("connector", "")).casefold() == constraints.required_connector.casefold():
            satisfied.append("connector")
            citations.append(f"item.attributes.connector={attrs.get('connector')}")
        else:
            unsatisfied.append("connector")
    if constraints.required_category is not None:
        if item.get("category") == constraints.required_category:
            satisfied.append("category")
            citations.append(f"item.category={item.get('category')}")
        else:
            unsatisfied.append("category")
    if constraints.return_friendly:
        policy = item.get("return_policy", "")
        if policy:
            satisfied.append("return policy")
            citations.append(f"item.return_policy={policy}")
        else:
            unsatisfied.append("return policy")
    return satisfied, unsatisfied, citations


def fetch_offers(urls: dict[str, str], request: str, extended: bool = True,
                 member_email: str | None = "ava@example.com") -> list[MerchantDecision]:
    constraints = parse_constraints(request)
    header = AGENT_HEADER if extended else PLAIN_AGENT_HEADER
    decisions: list[MerchantDecision] = []
    with httpx.Client(timeout=10) as client:
        for merchant_id, base_url in urls.items():
            search = client.get(f"{base_url}/ucp/catalog/search",
                                params={"q": request}, headers={"UCP-Agent": header})
            search.raise_for_status()
            items = search.json()["result"]["items"]
            if not items:
                continue
            item_id = items[0]["id"]
            lookup = client.get(f"{base_url}/ucp/catalog/lookup",
                                params={"id": item_id, "quantity": 1},
                                headers={"UCP-Agent": header})
            lookup.raise_for_status()
            envelope = lookup.json()
            payload = envelope["result"]
            quote, verification = _verify_payload(payload, member_email)
            satisfied, unsatisfied, citations = _match_constraints(payload, constraints)
            offer = payload["offer"]
            if quote:
                effective = quote.effective_cost_cents
                verified_value = quote.price_credit_cents + quote.comparison_value_cents
                penalty = quote.unsigned_penalty_cents
                arithmetic = quote.arithmetic
            else:
                effective = int(offer["total_cents"])
                verified_value = penalty = 0
                arithmetic = f"{effective / 100:.2f} (no benefit extension)"
            decisions.append(MerchantDecision(
                merchant_id=merchant_id,
                merchant_name=payload["item"].get("title", merchant_id),
                product_id=item_id,
                title=payload["item"]["title"],
                list_price_cents=int(offer["total_cents"]),
                effective_cost_cents=effective,
                available=bool(offer.get("available", True)),
                verified_value_cents=verified_value,
                unsigned_penalty_cents=penalty,
                constraints_satisfied=tuple(satisfied),
                constraints_unsatisfied=tuple(unsatisfied),
                citations=tuple(citations),
                verification=tuple(verification),
                arithmetic=arithmetic,
                payload=payload,
            ))
    return decisions


def rank(decisions: list[MerchantDecision]) -> list[MerchantDecision]:
    return sorted(decisions, key=lambda d: (
        bool(d.constraints_unsatisfied),
        not d.available,
        d.effective_cost_cents,
        d.merchant_id,
    ))


def evidence_record(request: str, decisions: list[MerchantDecision], extended: bool,
                    run_id: str = "demo") -> dict[str, Any]:
    ranked = rank(decisions)
    return {
        "schema_version": "0.1",
        "run_id": run_id,
        "request": request,
        "condition": "extended" if extended else "plain",
        "agent_header": AGENT_HEADER if extended else PLAIN_AGENT_HEADER,
        "prompt_sha256": hashlib.sha256(request.encode()).hexdigest(),
        "recommendation": ranked[0].merchant_id if ranked else None,
        "decisions": [
            {
                "merchant_id": d.merchant_id,
                "merchant_name": d.merchant_name,
                "product_id": d.product_id,
                "title": d.title,
                "list_price_cents": d.list_price_cents,
                "effective_cost_cents": d.effective_cost_cents,
                "available": d.available,
                "verified_value_cents": d.verified_value_cents,
                "unsigned_penalty_cents": d.unsigned_penalty_cents,
                "constraints_satisfied": list(d.constraints_satisfied),
                "constraints_unsatisfied": list(d.constraints_unsatisfied),
                "citations": list(d.citations),
                "verification": list(d.verification),
                "arithmetic": d.arithmetic,
                "wire_payload": d.payload,
            }
            for d in decisions
        ],
    }
