"""The policy converter — prose in, DRAFT benefit cards out, human gate last.

This is the AI component of the proposal: a language model reads the
retailer's human-written policy/loyalty/warranty documents and drafts
structured benefit records. Three rules make it safe rather than magic:

1. EVERY draft must carry a `source_quote` — and the quote must actually
   appear in the document (normalised: markdown emphasis stripped,
   whitespace collapsed, case folded — the team spike's D9.15 lesson,
   where `**$12.95**` vs `$12.95` silently rejected all ten faithful
   drafts). A draft whose quote is not found is REJECTED, not repaired.
2. Facts must use the recognised vocabulary (the customer-policy value
   channels). A model inventing a new value channel is rejected.
3. NOTHING publishes itself: drafts wait at the human approval gate
   (convert_policy.py), and only approved drafts are signed.

The model call is fixture-first (agentbridge.llm): recorded once with a
real key, replayed offline forever after.
"""

from __future__ import annotations

import json
import re
from datetime import date

from agentbridge import llm, loyalty
from agentbridge.logging_config import log_event
from agentbridge.models import MemberTier, OfferCard

RECOGNISED_FACTS = {"percent_off", "credit_cents", "extra_warranty_months",
                    "express_fee_waived_cents"}

SYSTEM = (
    "You extract loyalty and service benefits from a retailer's policy "
    "document into machine-readable drafts. Reply with ONLY a JSON array; "
    "each element: {\"description\": str (factual, no adjectives), "
    "\"benefit_type\": \"member_price\"|\"warranty\"|\"shipping\"|\"bonus_credit\", "
    "\"facts\": object using ONLY these keys where applicable: percent_off "
    "(number), credit_cents (int), extra_warranty_months (int), "
    "express_fee_waived_cents (int), "
    "\"conditions\": str, \"min_tier\": \"BRONZE\"|\"SILVER\"|\"GOLD\"|null, "
    "\"category\": \"electronics\"|\"apparel\"|null, "
    "\"value_ceiling_cents\": int (the cap the document states, or your "
    "conservative estimate of the benefit's per-order value), "
    "\"source_quote\": str — copied VERBATIM from the document, the exact "
    "sentence(s) this draft is based on}. "
    "Only extract benefits a specific customer receives (membership pricing, "
    "tier perks). Do not invent anything not stated in the document."
)


def _normalise(text: str) -> str:
    """Markdown emphasis and whitespace must not defeat a faithful quote."""
    text = re.sub(r"[*_`#>]", "", text)
    return re.sub(r"\s+", " ", text).strip().casefold()


def quote_appears(quote: str, document: str) -> bool:
    return bool(quote) and _normalise(quote) in _normalise(document)


def draft_cards(document: str, model: str | None = None,
                live: bool = False) -> tuple[list[dict], list[tuple[dict, str]]]:
    """Run the model over the document. Returns (accepted_drafts,
    rejected_drafts_with_reasons). Accepted still means UNAPPROVED —
    the human gate comes after."""
    result = llm.complete(SYSTEM, document, model=model, tag="converter",
                          live=live)
    raw = result["answer"].strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    try:
        drafts = json.loads(raw)
        assert isinstance(drafts, list)
    except (json.JSONDecodeError, AssertionError):
        return [], [({"raw": raw[:200]}, "model reply was not a JSON array")]

    accepted: list[dict] = []
    rejected: list[tuple[dict, str]] = []
    for d in drafts:
        quote = d.get("source_quote", "")
        facts = d.get("facts") or {}
        if not quote_appears(quote, document):
            rejected.append((d, "source_quote not found in the document"))
        elif not facts or not set(facts) <= RECOGNISED_FACTS:
            rejected.append((d, f"unrecognised facts {sorted(set(facts) - RECOGNISED_FACTS)}"))
        elif not isinstance(d.get("value_ceiling_cents"), int) \
                or d["value_ceiling_cents"] <= 0:
            rejected.append((d, "missing/invalid value_ceiling_cents"))
        else:
            accepted.append(d)
    d_prov = {"source": result["source"], "model": result["model"],
              "recorded_at": result.get("recorded_at")}
    log_event("converter_drafts", accepted=len(accepted),
              rejected=len(rejected), **d_prov)
    for d in accepted:
        d["_provenance"] = d_prov
    return accepted, rejected


def approve_and_sign(draft: dict, index: int) -> OfferCard:
    """Called ONLY after a human approved the draft. Builds and signs the
    card; the signature binds exactly what was approved."""
    card = OfferCard(
        card_id=f"conv_{date.today().strftime('%Y%m%d')}_{index}",
        issuer=loyalty.MERCHANT_ID,
        benefit_type=draft["benefit_type"],
        description=draft["description"],
        conditions=draft.get("conditions", ""),
        min_tier=MemberTier(draft["min_tier"]) if draft.get("min_tier") else None,
        category=draft.get("category"),
        facts={k: v for k, v in draft["facts"].items()},
        value_ceiling_cents=draft["value_ceiling_cents"],
        affects_price=draft["benefit_type"] in ("member_price", "bonus_credit"),
        issued_at=date.today().isoformat(),
        expires_at=draft.get("expires_at") or "2027-12-31",
    )
    loyalty.sign_card(card)
    log_event("card_approved_and_signed", card_id=card.card_id,
              source_quote=draft.get("source_quote", "")[:120])
    return card
