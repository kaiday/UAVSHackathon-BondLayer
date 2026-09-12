"""Seed the LLM fixture cache.

    python scripts/seed_fixtures.py              # record against a live model
    python scripts/seed_fixtures.py --authored   # write hand-authored stand-ins

Recording needs one of three things (see bondlayer/llm.py, D9.13):

    OPENAI_API_KEY set           -> the OpenAI SDK, or
    ANTHROPIC_API_KEY set        -> the Anthropic SDK, or
    `claude` on PATH, logged in  -> the Claude Code CLI in headless mode

All three produce genuine model output for the exact prompt the agent sends,
and the fixture records which one answered, under which model, when, how long
it took and what it cost. Anything recorded that way carries
"source": "openai" | "anthropic" | "claude_cli".

BONDLAYER_LLM picks the transport and BONDLAYER_MODEL the model id. The
fixture key hashes the model, so switching either misses the cache and
re-records -- deliberately, because a fixture from a different model is a
different experiment.

--authored writes hand-written stand-ins instead, for a machine with neither.
Those carry "source": "authored" and are surfaced as such everywhere in the
demo, because a hand-written completion is not evidence of model behaviour and
must never be allowed to look like one.

Existing fixtures are reused; pass --force to re-record them.

--repeats N additionally records N ranking calls per condition with the offers
in a different order each time (demo-flow-v2 3b). Position bias is the failure
mode most likely to be raised by a judge, and n=1 cannot answer it. The
reordering changes the prompt, so each repeat lands on its own fixture key.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from bondlayer import config, llm  # noqa: E402
from bondlayer.agent import repeat  # noqa: E402
from bondlayer.agent import shopping_agent as sa  # noqa: E402
from bondlayer.demo_data import GOLD_MEMBER, merchant_urls  # noqa: E402
from bondlayer.signing import KeyRing  # noqa: E402

REQUEST = "Find me a good waterproof jacket under $200."
GTIN = "9312345678907"

AUTHORED = "--authored" in sys.argv
MODEL = llm.default_model()
FORCE = "--force" in sys.argv


def _repeats_arg() -> int:
    if "--repeats" in sys.argv:
        i = sys.argv.index("--repeats")
        if i + 1 < len(sys.argv):
            return int(sys.argv[i + 1])
        return 5
    return 0


REPEATS = _repeats_arg()


AUTHORED_INTENT = json.dumps(
    {
        "query": "waterproof jacket",
        "budget_aud": 200,
        "fit_risk_aud": 9,
        "max_loyalty_premium_pct": 15,
        "notes": "No sizing anxiety expressed; treated as an average returner.",
    },
    indent=2,
)

AUTHORED_BASELINE = json.dumps(
    {
        "winner_merchant_id": "peak",
        "reason": (
            "All three merchants list the same Alpine Outfitters Stormline 3L "
            "jacket with identical specifications, so there is nothing to "
            "separate them except price. Peak Supply Co is the cheapest at "
            "$179.00, twenty dollars below Alpine Outfitters and sixteen below "
            "Ridgeway Gear."
        ),
        "ranking": ["peak", "ridgeway", "alpine"],
    },
    indent=2,
)

AUTHORED_BONDLAYER = json.dumps(
    {
        "winner_merchant_id": "alpine",
        "reason": (
            "Alpine Outfitters lists at $199.00 against Peak Supply Co's "
            "$179.00, but publishes six cryptographically verified member "
            "benefits that Peak does not: a 5% Gold member discount, free "
            "60-day returns with postage paid, a 24-month warranty, free "
            "delivery, and Summit Club points. Those verified benefits are "
            "worth more than the $20.00 price difference, and Ridgeway Gear's "
            "warranty claim carries no signature, so I have not relied on it."
        ),
        "ranking": ["alpine", "peak", "ridgeway"],
    },
    indent=2,
)

AUTHORED_EXPLAIN = (
    "Alpine Outfitters is the best value at an adjusted cost of $155.26, "
    "despite a list price of $199.00, because $43.74 of verified member "
    "benefits apply to you. Peak Supply Co is cheaper on the shelf at $179.00 "
    "but publishes nothing you can claim against it."
)


AUTHORED_POLICY_DRAFTS = "[\n  {\n    \"id\": \"alpine-free-returns\",\n    \"type\": \"free_returns\",\n    \"title\": \"Free returns within 60 days, return postage paid\",\n    \"facts\": {\n      \"return_window_days\": 60,\n      \"return_shipping_paid\": true\n    },\n    \"declared_bound_aud\": null,\n    \"conditions\": {\n      \"requires_membership\": false,\n      \"requires_tier\": null,\n      \"min_order_aud\": 0,\n      \"excludes_sale_items\": true\n    },\n    \"source_quote\": \"We accept returns on unworn items with tags attached for **60 days** from the\\ndelivery date.\"\n  },\n  {\n    \"id\": \"alpine-warranty\",\n    \"type\": \"warranty_extension\",\n    \"title\": \"24 month manufacturer warranty\",\n    \"facts\": {\n      \"warranty_months\": 24,\n      \"statutory_baseline_months\": 12\n    },\n    \"declared_bound_aud\": null,\n    \"conditions\": {\n      \"requires_membership\": false,\n      \"requires_tier\": null,\n      \"min_order_aud\": 0,\n      \"excludes_sale_items\": false\n    },\n    \"source_quote\": \"Every Alpine Outfitters hardshell carries a **24 month** manufacturer warranty\"\n  },\n  {\n    \"id\": \"alpine-free-shipping\",\n    \"type\": \"free_shipping\",\n    \"title\": \"Free standard delivery over $100\",\n    \"facts\": {\n      \"free_over_aud\": 100.0\n    },\n    \"declared_bound_aud\": null,\n    \"conditions\": {\n      \"requires_membership\": false,\n      \"requires_tier\": null,\n      \"min_order_aud\": 0,\n      \"excludes_sale_items\": false\n    },\n    \"source_quote\": \"Standard delivery is free on orders over $100.\"\n  },\n  {\n    \"id\": \"alpine-points\",\n    \"type\": \"points_earn\",\n    \"title\": \"Summit Club points \\u2014 2 per dollar, 100 points = $1\",\n    \"facts\": {\n      \"points_per_aud\": 2,\n      \"redemption_points_per_aud\": 100,\n      \"points_expire_months\": 24\n    },\n    \"declared_bound_aud\": null,\n    \"conditions\": {\n      \"requires_membership\": true,\n      \"requires_tier\": null,\n      \"min_order_aud\": 0,\n      \"excludes_sale_items\": false\n    },\n    \"source_quote\": \"Members earn **2 points per dollar** spent.\"\n  },\n  {\n    \"id\": \"alpine-member-price\",\n    \"type\": \"member_price\",\n    \"title\": \"Gold member price \\u2014 5% off full-price items\",\n    \"facts\": {\n      \"discount_pct\": 5.0\n    },\n    \"declared_bound_aud\": null,\n    \"conditions\": {\n      \"requires_membership\": true,\n      \"requires_tier\": \"Gold\",\n      \"min_order_aud\": 0,\n      \"excludes_sale_items\": true\n    },\n    \"source_quote\": \"receive an additional **5% off the list price** of all full-price\\nitems\"\n  },\n  {\n    \"id\": \"alpine-price-match\",\n    \"type\": \"member_price\",\n    \"title\": \"Price match guarantee \\u2014 we beat any competitor by 10%\",\n    \"facts\": {\n      \"discount_pct\": 10.0,\n      \"discount_aud\": 25.0\n    },\n    \"declared_bound_aud\": 25.0,\n    \"conditions\": {\n      \"requires_membership\": false,\n      \"requires_tier\": null,\n      \"min_order_aud\": 0,\n      \"excludes_sale_items\": false\n    },\n    \"source_quote\": \"Alpine Outfitters will beat any competitor's advertised price by 10%.\"\n  },\n  {\n    \"id\": \"alpine-lifetime-repairs\",\n    \"type\": \"warranty_extension\",\n    \"title\": \"Free lifetime repairs\",\n    \"facts\": {\n      \"warranty_months\": 600,\n      \"statutory_baseline_months\": 12\n    },\n    \"declared_bound_aud\": 120.0,\n    \"conditions\": {\n      \"requires_membership\": false,\n      \"requires_tier\": null,\n      \"min_order_aud\": 0,\n      \"excludes_sale_items\": false\n    },\n    \"source_quote\": \"All Alpine hardshells include free repairs for the life of the garment.\"\n  }\n]"


def write(label: str, system: str, prompt: str, completion: str) -> None:
    """Write a HAND-AUTHORED stand-in. Marked so it can never pass as a recording."""
    path = llm.FIXTURE_DIR / f"{label}-{llm._key(system, prompt, MODEL)}.json"
    llm.FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "label": label,
                "model": MODEL,
                "source": "authored",
                "authored": True,
                "warning": (
                    "HAND-AUTHORED, not recorded model output. Re-run "
                    "scripts/seed_fixtures.py without --authored to record."
                ),
                "system": system,
                "prompt": prompt,
                "completion": completion,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"  authored {path.name}  ({label})")


def main() -> None:
    transport = llm.available_transport()
    if not AUTHORED and transport is None:
        sys.exit(
            "No live transport.\n"
            f"  {config.describe()}\n"
            "  Put OPENAI_API_KEY (or ANTHROPIC_API_KEY) in demo/.env -- copy "
            ".env.example to start -- or log into the `claude` CLI, or pass "
            "--authored to write stand-ins."
        )
    print(f"config: {config.describe()}")
    if not AUTHORED:
        print(f"recording against: {llm.SOURCE_LABELS[transport]}  ({MODEL})")

    print("booting merchants...")
    import run_demo  # noqa: E402  (adds src to path itself)

    run_demo.serve(block=False)

    from bondlayer.ingest import policy_converter as pc

    policy_doc = (ROOT / "data" / "merchants" / "alpine" / "policy.md").read_text(
        encoding="utf-8"
    )

    payloads: list[tuple[str, str, str, str]] = [
        ("intent", sa.INTENT_SYSTEM, REQUEST, AUTHORED_INTENT),
        ("policy-alpine", pc.SYSTEM, policy_doc, AUTHORED_POLICY_DRAFTS),
    ]

    for use_ext, authored in ((False, AUTHORED_BASELINE), (True, AUTHORED_BONDLAYER)):
        keyring = KeyRing()
        offers = [
            o
            for o in sa.fetch_offers(
                merchant_urls(),
                sa.search_query(REQUEST),
                use_extension=use_ext,
                member_id=GOLD_MEMBER.member_id,
                keyring=keyring,
            )
            if o.gtin == GTIN
        ]
        payloads.append(
            ("rank", sa.RANK_SYSTEM, sa.build_rank_payload(REQUEST, offers, keyring),
             authored)
        )

        # The n=5 tally. Each ordering is a distinct prompt and so a distinct
        # fixture; the first ordering is the natural one already queued above,
        # and `write` skips anything already on disk.
        for order in repeat.orderings(len(offers), REPEATS):
            shuffled = [offers[i] for i in order]
            payloads.append(
                ("rank", sa.RANK_SYSTEM,
                 sa.build_rank_payload(REQUEST, shuffled, keyring), authored)
            )

        if use_ext:
            policy = sa.extract_intent(REQUEST, allow_network=False)
            trv_run = sa.run_trv_agent(
                REQUEST, offers, policy, keyring, allow_network=False
            )
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
                for v in trv_run.valuations
            ]
            payloads.append(
                ("explain", sa.EXPLAIN_SYSTEM,
                 json.dumps({"request": REQUEST, "table": table}, indent=2),
                 AUTHORED_EXPLAIN)
            )

    print("\nfixtures:")
    for label, system, prompt, authored in payloads:
        path = llm.FIXTURE_DIR / f"{label}-{llm._key(system, prompt, MODEL)}.json"
        if AUTHORED:
            write(label, system, prompt, authored)
            continue
        if path.exists() and not FORCE:
            blob = json.loads(path.read_text(encoding="utf-8"))
            src = blob.get("source", "unknown")
            if src in llm.RECORDED_SOURCES:
                print(f"  kept     {path.name}  ({label}, already {src})")
                continue
            print(f"  replacing {path.name}  (was {src})")
            path.unlink()
        elif path.exists():
            path.unlink()

        llm.complete(system, prompt, label=label, allow_network=True)
        call = llm.last_call(label)
        cost = call.usage.get("cost_usd")
        print(
            f"  recorded {call.fixture}  ({label}, {call.latency_ms} ms, "
            f"{call.usage.get('output_tokens', '?')} out"
            + (f", ${cost:.4f}" if cost else "")
            + ")"
        )
        # A Windows console is cp1252, and a model that answers with a real
        # minus sign or a curly quote would otherwise kill the run *after* the
        # fixture was written, losing the rest of the batch to a progress line.
        # This preview is cosmetic; it must never raise.
        enc = sys.stdout.encoding or "utf-8"
        preview = call.completion.replace("\n", " ")[:100]
        print("      " + preview.encode(enc, "replace").decode(enc) + "...")

    counts = llm.fixture_provenance()
    print(f"\nfixture provenance on disk: {counts}")
    if counts["authored"] or counts["unknown"]:
        print(
            "WARNING: some fixtures are hand-authored. The demo labels them, "
            "but they are not evidence of model behaviour."
        )


if __name__ == "__main__":
    main()
