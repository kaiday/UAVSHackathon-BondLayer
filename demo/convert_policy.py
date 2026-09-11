"""The approval gate CLI — model drafts in front of a human, nothing more.

  python convert_policy.py data/policy_docs/store_policy.md
  python convert_policy.py <doc> --approve-all   # rehearsal shortcut, labelled
  python convert_policy.py <doc> --live          # force a fresh model call

Reads the document, shows every model draft NEXT TO the source text it
quotes, asks y/N per draft, signs only what you approve, and writes the
result to data/approved_cards.json. Rejected drafts (bad quote, invented
facts) are shown too — the gate is only as good as what it lets you see.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agentbridge.converter import draft_cards
from agentbridge.models import cents_to_str

OUT = Path(__file__).resolve().parent / "data" / "approved_cards.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="policy -> draft cards -> human gate")
    parser.add_argument("document", help="path to the policy/loyalty prose document")
    parser.add_argument("--approve-all", action="store_true",
                        help="approve every surviving draft without asking "
                             "(REHEARSAL ONLY — the gate is the safety feature)")
    parser.add_argument("--live", action="store_true",
                        help="force a fresh model call (re-records the fixture)")
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    document = Path(args.document).read_text(encoding="utf-8")
    print(f"Read {args.document} ({len(document)} chars). Drafting…\n")
    try:
        accepted, rejected = draft_cards(document, model=args.model, live=args.live)
    except RuntimeError as exc:
        sys.exit(str(exc))

    if accepted:
        prov = accepted[0]["_provenance"]
        print(f"[drafts from {prov['source']}: {prov['model']}, "
              f"recorded {prov['recorded_at']}]\n")

    for d, reason in rejected:
        print(f"REJECTED by guardrail: {reason}")
        print(f"   {json.dumps({k: v for k, v in d.items() if k != '_provenance'})[:160]}\n")

    approved = []
    for i, d in enumerate(accepted, start=1):
        print(f"--- draft {i}/{len(accepted)} " + "-" * 40)
        print(f"  {d['description']}")
        print(f"  type={d['benefit_type']}  tier={d.get('min_tier')}  "
              f"category={d.get('category')}  "
              f"ceiling={cents_to_str(d['value_ceiling_cents'])}")
        print(f"  facts: {d['facts']}")
        print(f"  source: \"{d['source_quote']}\"")
        if args.approve_all:
            print("  -> approved (--approve-all: REHEARSAL MODE)")
            ok = True
        else:
            ok = input("  approve and sign? [y/N] ").strip().lower() == "y"
        if ok:
            from agentbridge.converter import approve_and_sign
            approved.append(approve_and_sign(d, i))
        print()

    if not approved:
        print("Nothing approved — nothing signed, nothing published.")
        return
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(
        [c.model_dump(mode="json") for c in approved], indent=2),
        encoding="utf-8")
    print(f"Signed and wrote {len(approved)} card(s) to {OUT}")
    print("(Serving still uses the built-in card set — wiring approved_cards.json")
    print(" into loyalty.CARDS is the deliberate next seam, so a rehearsal here")
    print(" can never silently change the demo's numbers.)")


if __name__ == "__main__":
    main()
