"""BondLayer visibility console — the merchant's view of agent traffic.

Answers the e-commerce lead's operational question from the proposal:
per agent session, how much of my real offer was legible, how much value
could the agent actually credit, and what was withheld (unsigned claims,
expired promos, tier/category conditions)?

Reads the structured JSON-line log every tool call already writes
(agentbridge.log) — no extra instrumentation, the audit trail IS the
data source.

Usage:
  python console.py           # report on the latest server session
  python console.py --all     # report across the whole log file
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from agentbridge.logging_config import LOG_FILE
from agentbridge.models import cents_to_str


def load_events(all_sessions: bool) -> list[dict]:
    if not Path(LOG_FILE).exists():
        raise SystemExit(f"No log file at {LOG_FILE} — run the server or benchmark first.")
    events = []
    with open(LOG_FILE, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if all_sessions:
        return events
    # Default window: everything since the most recent server/benchmark start.
    last_start = 0
    for i, ev in enumerate(events):
        if ev.get("event") == "server_start":
            last_start = i
    return events[last_start:]


def report(events: list[dict]) -> None:
    tools = Counter(ev.get("tool") for ev in events if ev.get("event") == "tool_call")
    identified = [ev for ev in events if ev.get("event") == "member_identified"]
    enrolled = [ev for ev in events if ev.get("event") == "member_enrolled"]
    quotes = [ev for ev in events if ev.get("event") == "loyalty_valued"]
    credits = [ev for ev in events if ev.get("event") == "loyalty_credited"]
    created = [ev for ev in events if ev.get("event") == "order_created"]
    confirmed = [ev for ev in events if ev.get("event") == "order_confirmed"]

    price_credit = sum(q.get("price_credit_cents", 0) for q in quotes)
    comparison = sum(q.get("comparison_value_cents", 0) for q in quotes)
    withheld = sum(q.get("withheld_cents", 0) for q in quotes)
    reject_reasons = Counter()
    for q in quotes:
        for reason in (q.get("rejected") or {}).values():
            # Collapse per-card detail into reason families for the summary.
            reject_reasons[reason.split(" (")[0]] += 1
    settled = sum(ev.get("total_cents", 0) for ev in confirmed)
    credited_on_orders = sum(ev.get("credit_cents", 0) for ev in credits)

    w = 62
    print("=" * w)
    print(f"{'BondLayer visibility console — agent traffic report':^{w}}")
    print("=" * w)
    print(f"{'Agent tool calls':<38}{sum(tools.values()):>24}")
    for tool, n in tools.most_common():
        print(f"  {tool or '?':<36}{n:>24}")
    print("-" * w)
    print(f"{'Members identified / enrolled':<38}"
          f"{f'{len(identified)} / {len(enrolled)}':>24}")
    print(f"{'Loyalty quotes issued':<38}{len(quotes):>24}")
    print(f"{'Value credited to price':<38}{cents_to_str(price_credit):>24}")
    print(f"{'Service value counted (effective cost)':<38}{cents_to_str(comparison):>24}")
    print(f"{'Value withheld (not credited)':<38}{cents_to_str(withheld):>24}")
    for reason, n in reject_reasons.most_common():
        print(f"  {reason:<48}{f'x{n}':>12}")
    print("-" * w)
    print(f"{'Orders created / confirmed':<38}"
          f"{f'{len(created)} / {len(confirmed)}':>24}")
    print(f"{'Loyalty credit honoured at settlement':<38}"
          f"{cents_to_str(credited_on_orders):>24}")
    print(f"{'Revenue settled (test mode)':<38}{cents_to_str(settled):>24}")
    print("=" * w)
    # TODO(roadmap): 'recommended' and 'why it lost' need the cross-merchant
    # comparison — the agent-side valuation library reports which merchant
    # won each request and which withheld/unverified value cost the loser.


def main() -> None:
    parser = argparse.ArgumentParser(description="BondLayer merchant console")
    parser.add_argument("--all", action="store_true",
                        help="report across the whole log, not just the latest session")
    args = parser.parse_args()
    report(load_events(args.all))


if __name__ == "__main__":
    main()
