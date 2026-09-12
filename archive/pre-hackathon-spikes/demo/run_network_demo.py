"""Offline merchant-network demo.

Run from this directory:
    python run_network_demo.py
    python run_network_demo.py --repeats 5

No API key or network access required. The HTTP calls are localhost-only and
all ranking arithmetic is deterministic.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from agentbridge.evaluation import run_case, run_repeats, scoreboard, visibility
from agentbridge.merchant_network import serve_network, stop_network

REQUEST = "Find me a good 65W USB-C GaN wall charger under $45"
EVIDENCE_DIR = Path(__file__).resolve().parent / "data" / "evidence"


def _print_run(record: dict) -> None:
    print(f"\n[{record['condition'].upper()}] recommendation: {record['recommendation']}")
    for decision in record["decisions"]:
        print(
            f"  {decision['merchant_id']:<12} "
            f"list=${decision['list_price_cents'] / 100:.2f} "
            f"effective=${decision['effective_cost_cents'] / 100:.2f} "
            f"verified=${decision['verified_value_cents'] / 100:.2f} "
            f"unsigned penalty=${decision['unsigned_penalty_cents'] / 100:.2f}"
        )
        if decision["constraints_unsatisfied"]:
            print(f"               unsatisfied: {', '.join(decision['constraints_unsatisfied'])}")
        for verdict in decision["verification"]:
            state = "VERIFIED" if verdict["verified"] else "REJECTED"
            print(f"               {state:<9} {verdict['card_id']}: {verdict['reason']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="offline merchant-network demo")
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be at least 1")

    urls, servers = serve_network()
    try:
        print("BondLayer merchant network — offline evaluation")
        print(f"Request: {REQUEST}")
        before = run_case(urls, REQUEST, extended=False, run_id="before")
        after = run_case(urls, REQUEST, extended=True, run_id="after")
        _print_run(before)
        _print_run(after)

        repeats, repeat_metrics = run_repeats(urls, REQUEST, args.repeats)
        print(f"\n[REPEATS] attempted={repeat_metrics['attempted']} "
              f"recorded={repeat_metrics['recorded']} "
              f"stable={repeat_metrics['stable']}/{repeat_metrics['attempted']}")
        print("  recommendation counts:", repeat_metrics["counts"])

        print("\n[VISIBILITY] harbor-tech")
        print(json.dumps(visibility(after, "harbor-tech"), indent=2))
        print("\n[SCOREBOARD]")
        print(json.dumps(scoreboard(after), indent=2))

        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        output = {
            "before": before,
            "after": after,
            "repeats": repeats,
            "repeat_metrics": repeat_metrics,
            "scoreboard": scoreboard(after),
        }
        path = EVIDENCE_DIR / "canonical.json"
        path.write_text(json.dumps(output, indent=2), encoding="utf-8")
        print(f"\nEvidence written to {path}")
    finally:
        stop_network(servers)


if __name__ == "__main__":
    main()
