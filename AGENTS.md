I am attending a hackathon (UAVS Hackathon 2026, FPT "B2A Shift" problem) and
this repository holds the team's deliverables and working notes.

Problem statement: `docs/FPT-Problem-Statement-Final.pdf`

Rules: `docs/Hackathon-Rulebook-2026-Final-Updated-1.pdf`

Day 2 plan, rulings and workstream briefs: `round2/DAY2-PLAN.md`

The product is `bondlayer/` (merchant-side UCP server, adapter, signed records,
dashboard). `round2/chat-app/` is the buyer-agent stand-in used in the demo.
`archive/pre-hackathon-spikes/` is Round 1 spike code kept for reference only;
nothing submitted imports from it. Never edit `bondlayer/src/bondlayer/types.py`
on a feature branch. No network calls at runtime.
