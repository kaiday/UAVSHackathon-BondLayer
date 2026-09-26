I am attending a hackathon (UAVS Hackathon 2026, FPT "B2A Shift" problem) and
this repository holds the team's deliverables and working notes.

Problem statement: `docs/FPT-Problem-Statement-Final.pdf`

Rules: `docs/Hackathon-Rulebook-2026-Final-Updated-1.pdf`

Day 2 plan, rulings and workstream briefs: `docs/notes/DAY2-PLAN.md`

The product is `bondlayer/` (merchant-side UCP server, adapter, signed records,
dashboard). `buyer-agent/` is the buyer-agent stand-in used in the demo.
Round 1 spike code was removed from the tree on 13/09 (git history, commit
`074e51c`); nothing submitted imported from it. Never edit `bondlayer/src/bondlayer/types.py`
on a feature branch. Live AI features use the server-side OpenAI integration in
`bondlayer/src/bondlayer/ai.py`. Use `BONDLAYER_AI_MODE=rules` for explicit offline operation;
tests must stub provider transport or select rules mode, never make paid API calls.
