"""Plain-English merchant policy -> draft benefit_value records -> approval.

The other half of "the plug" (D7), and the highest-risk component in the whole
design. It is where an LLM is genuinely necessary -- nobody hand-codes every
merchant's T&Cs -- and where hallucination would do the most damage, because
the output feeds a valuation.

The guardrail is structural, not statistical:

    the model DRAFTS, a person APPROVES, and only signed records are valued.

Nothing here can produce a signature. `sign_approved()` is a separate step
that requires an explicit approval decision per record. An unapproved draft is
displayed in the merchant dashboard and ignored by every agent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from .. import llm
from ..schema import BenefitType, BenefitValue, Conditions
from ..signing import MerchantSigner

SYSTEM = """\
You convert a retailer's plain-English customer policy into structured benefit
records for a machine-readable commerce catalogue.

Rules:
- Extract ONLY what the document actually states. Never infer a number that is
  not written down. If a value is not stated, omit the field.
- Never estimate what a benefit is "worth" in dollars. You state facts; a
  separate system decides value.
- The only exception: where the document states an intrinsic monetary rate
  (a points redemption rate, a fixed member discount), put that figure in
  declared_bound_aud.
- Use these types only: points_earn, member_price, free_returns, free_shipping,
  warranty_extension, tier_progression.
- Use explicit units in fact names: return_window_days, warranty_months,
  free_over_aud, discount_aud, return_shipping_paid, statutory_baseline_months.

Return a JSON array. Each element:
{
  "id": "kebab-case-id",
  "type": "<one of the types above>",
  "title": "short human-readable summary",
  "facts": { ... },
  "declared_bound_aud": <number or null>,
  "conditions": {
     "requires_membership": bool,
     "requires_tier": "<tier name or null>",
     "min_order_aud": <number>,
     "excludes_sale_items": bool
  },
  "source_quote": "the exact sentence from the document this came from"
}
Return the array and nothing else."""


@dataclass
class Draft:
    """A model-produced record awaiting a human decision. Never valued."""

    benefit: BenefitValue
    source_quote: str
    warnings: list[str] = field(default_factory=list)
    approved: bool = False


#: Markdown emphasis and the document's hard line wrapping are formatting, not
#: content. Comparing raw strings rejected every single draft in the first
#: recorded run -- the model had quoted the document correctly and merely
#: dropped the ** around a number. That is a false positive, and a check that
#: fires on everything catches nothing. See DECISIONS.md D9.15.
_EMPHASIS = re.compile(r"[*_`]+")
_SPACE = re.compile(r"\s+")


def _normalise(text: str) -> str:
    """Formatting-insensitive form for quote matching.

    Emphasis marks are deleted (so `**$12.95**,` and `$12.95,` agree) and
    whitespace is collapsed (so the document's hard wrapping does not split a
    sentence the model quoted on one line). Words, numbers and punctuation are
    otherwise preserved exactly, so an invented sentence still fails.
    """
    return _SPACE.sub(" ", _EMPHASIS.sub("", text.lower())).strip()


def _validate(record: dict[str, Any], document: str) -> list[str]:
    """Cheap checks that catch the failure modes we actually expect."""
    warnings: list[str] = []

    quote = (record.get("source_quote") or "").strip().strip('"')
    if not quote:
        warnings.append("no source quote given")
    elif _normalise(quote) not in _normalise(document):
        # The single most valuable check here: the model citing a sentence the
        # document does not contain is the clearest hallucination signal we get.
        warnings.append(f"source quote not found in the document: {quote!r}")

    bound = record.get("declared_bound_aud")
    if bound is not None:
        btype = record.get("type")
        if btype in ("free_returns", "free_shipping", "warranty_extension"):
            warnings.append(
                f"declared_bound_aud on {btype}: this type has no intrinsic "
                "monetary rate, so the merchant should not be putting a price on it"
            )
        if isinstance(bound, (int, float)) and bound > 100:
            warnings.append(f"declared bound of ${bound} is unusually large; check it")

    for key in record.get("facts", {}):
        if not any(
            key.endswith(s) for s in ("_days", "_months", "_aud", "_paid", "_pct", "_mm")
        ):
            warnings.append(f"fact {key!r} has no unit in its name; may not be legible")

    return warnings


def draft_from_document(
    document: str,
    merchant_id: str,
    *,
    allow_network: bool = True,
) -> list[Draft]:
    """Ask the model for structured drafts. Produces nothing signed."""
    text = llm.complete(
        SYSTEM,
        document,
        label=f"policy-{merchant_id}",
        allow_network=allow_network,
    )
    records = llm.extract_json(text)
    if not isinstance(records, list):
        raise ValueError("policy converter did not return a JSON array")

    now = datetime.now(timezone.utc)
    drafts: list[Draft] = []
    for record in records:
        warnings = _validate(record, document)
        try:
            benefit = BenefitValue(
                id=record["id"],
                type=BenefitType(record["type"]),
                title=record["title"],
                facts=record.get("facts", {}),
                declared_bound_aud=record.get("declared_bound_aud"),
                conditions=Conditions(**(record.get("conditions") or {})),
                issuer=merchant_id,
                issued_at=now,
                expires_at=now + timedelta(days=30),
                signature=None,
            )
        except Exception as exc:  # malformed draft -- surface, do not crash
            drafts.append(
                Draft(
                    benefit=BenefitValue(
                        id=str(record.get("id", "malformed")),
                        type=BenefitType.free_returns,
                        title=str(record.get("title", "malformed draft")),
                        issuer=merchant_id,
                        issued_at=now,
                    ),
                    source_quote=str(record.get("source_quote", "")),
                    warnings=[f"could not be parsed: {exc}"],
                )
            )
            continue

        drafts.append(
            Draft(benefit=benefit, source_quote=record.get("source_quote", ""),
                  warnings=warnings)
        )

    return drafts


def sign_approved(drafts: list[Draft], signer: MerchantSigner) -> list[BenefitValue]:
    """The approval gate. Only records a human marked approved get signed."""
    return [signer.sign(d.benefit) for d in drafts if d.approved]
