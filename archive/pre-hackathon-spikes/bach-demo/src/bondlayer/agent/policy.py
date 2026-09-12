"""The customer's valuation policy. Agent-side. The merchant never sees it.

Every parameter here answers "what is this worth TO ME", which is why it
cannot live merchant-side: free returns are worth a great deal to someone who
buys two sizes and sends one back, and nothing to someone who never returns
anything. There is no true value, only a value under a stated policy -- the
design never claims otherwise (DECISIONS.md, known weakness 3).

Defaults are derived from the shopper's own words by intent extraction (D9.7)
and then exposed as sliders for live manipulation.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CustomerPolicy(BaseModel):
    budget_aud: float | None = Field(
        default=None, description="Hard ceiling from the shopper's request."
    )

    # --- what benefits are worth to this shopper ---
    fit_risk_aud: float = Field(
        default=9.0,
        description=(
            "Expected cost of a return going wrong: postage, hassle, the risk "
            "of being stuck with it. What free returns is worth to me."
        ),
    )
    shipping_cost_assumption_aud: float = Field(
        default=12.0, description="What I would otherwise pay for delivery."
    )
    warranty_value_per_year_aud: float = Field(
        default=8.0, description="What each extra year of warranty is worth."
    )
    tier_progression_value_aud: float = Field(
        default=4.0,
        description=(
            "What reaching the next loyalty tier is worth to me. No merchant "
            "fact can establish this, so it has to be my number -- the "
            "merchant's declared bound can only cap it (D4)."
        ),
    )

    # --- confidence, not preference ---
    points_confidence: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description=(
            "Fraction of a merchant's declared points value I actually expect "
            "to realise, after breakage and expiry."
        ),
    )
    provisional_confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Weight applied to forecast benefits, e.g. tier progression.",
    )

    # --- what I refuse to count ---
    count_tier_progression: bool = True
    count_points: bool = True

    # --- how I treat claims I cannot verify (D9.5) ---
    unverified_penalty_rate: float = Field(
        default=0.5,
        ge=0.0,
        description=(
            "Fraction of an unverifiable claim's notional value added as a "
            "penalty. Gives lying a price proportional to the size of the lie."
        ),
    )
    unverified_penalty_cap_aud: float = Field(
        default=25.0, description="Ceiling on total penalty per merchant."
    )

    # --- how much loyalty is allowed to cost me ---
    max_loyalty_premium_pct: float = Field(
        default=15.0,
        description=(
            "I will not pay more than this much above the cheapest list price, "
            "no matter how good the adjusted number looks."
        ),
    )
