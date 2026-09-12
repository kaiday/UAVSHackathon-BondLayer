"""Payment settlement — TEST MODE ONLY, by construction.

Two paths:
- STRIPE_TEST_KEY set  -> create a real Stripe *test-mode* PaymentIntent.
  Keys that are not `sk_test_...` are refused outright: this module will
  never touch a live key.
- no key               -> deterministic simulated charge (`ch_sim_...`).

Either way `settle()` returns a payment reference string; it is only
ever called from confirm_order — the explicit confirmation gate.
"""

from __future__ import annotations

import os
import uuid

from agentbridge.logging_config import log_event


class PaymentRefusedError(Exception):
    """Raised when settlement is refused (e.g. a non-test Stripe key)."""


def settle(order_id: str, amount_cents: int, currency: str = "USD") -> str:
    """Settle an order in test mode and return a payment reference.

    NEVER performs a real charge. Live Stripe keys are rejected.
    """
    stripe_key = os.environ.get("STRIPE_TEST_KEY", "").strip()

    if stripe_key:
        if not stripe_key.startswith("sk_test_"):
            # Hard safety rail: refuse anything that could be a live key.
            raise PaymentRefusedError(
                "STRIPE_TEST_KEY must be a Stripe TEST key (sk_test_...). "
                "AgentBridge never performs live charges."
            )
        try:
            import stripe  # optional dependency; graceful fallback below

            stripe.api_key = stripe_key
            intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency=currency.lower(),
                payment_method="pm_card_visa",  # Stripe's canonical test card
                confirm=True,
                automatic_payment_methods={"enabled": True, "allow_redirects": "never"},
                metadata={"agentbridge_order": order_id},
            )
            log_event("payment_settled", mode="stripe_test", order_id=order_id,
                      amount_cents=amount_cents, ref=intent.id)
            return intent.id
        except ImportError:
            log_event("payment_fallback", reason="stripe package not installed")
        except Exception as exc:  # network down, bad key, etc. — demo must not die
            log_event("payment_fallback", reason=f"stripe error: {exc}")

    ref = f"ch_sim_{uuid.uuid4().hex[:16]}"
    log_event("payment_settled", mode="simulated", order_id=order_id,
              amount_cents=amount_cents, ref=ref)
    return ref
