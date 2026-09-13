> Historical: written when these notes lived in `round2/`. Since 13/09 the chat app is `buyer-agent/` and these notes are in `docs/notes/`; tree listings below describe the old layout.

# Round 2 — working folder

*Rewritten 12/09 evening against `round2/dev` to describe what exists, not what was planned.
Verified with `ls` and by running the code. The plan of record is [`DAY2-PLAN.md`](DAY2-PLAN.md).*

## Where the product actually lives

The Round 2 product is **`bondlayer/` at the repository root**, not in this folder. It is one
Python package (`pip install -e bondlayer[dev]`) holding the merchant-side UCP server, the catalogue
adapter, signed benefit records, valuation, the intent interpreter, the agent composition root and
the merchant dashboard. Its suite is 95 tests, all offline.

This folder holds the **buyer-agent stand-in** used in the demo (`chat-app/`), the Day 1 valuation
prototype that was later absorbed into `bondlayer/`, and the team's working notes.

Run everything from the repository root:

```bash
./run.sh            # venv, install, merchant server :8000, agent :8001 (+ Vite UI :5173 if npm)
./run.sh --check    # venv, install, pytest -- what scripts/clean_clone_check.sh runs in a fresh clone
```

## What is in `round2/` (real tree)

```
round2/
├── README.md                    this file
├── DAY2-PLAN.md                 Day 2 plan: verified state, Ford's rulings D1–D6, workstream briefs
├── chat-app/                    buyer-agent stand-in (WS-B is repointing it at bondlayer/'s server)
│   ├── src/agent/               FastAPI agent on :8001 (main.py, llm.py, ucp_client.py, static/)
│   ├── src/merchant/            Day 1 copy of the merchant -- being DELETED (D1); never start it
│   ├── src/ui/                  React + Vite chat UI (:5173)
│   ├── data/                    Day 1 copies of catalogue/records/keys -- being deleted (D1)
│   ├── tests/
│   ├── requirements.txt         being rewritten to depend on bondlayer
│   ├── launch.sh, launch.ps1, run-windows.*   Day 1 launchers; superseded by the root run.sh / run.ps1
│   └── README.md, WINDOWS_SETUP.md
├── valuation/                   Day 1 signing + effective-cost prototype (feat/bach-records-signing)
├── tests/test_invariants.py     9 tests over round2/valuation (pytest tests, from this folder)
├── pyproject.toml               Day 1 packaging for round2/valuation (also named "bondlayer"; see note)
├── demo_issue_13.py             Day 1 CLI walk-through of the signing invariants
├── system-architecture.md       Day 1 architecture sketch (WS-D is rewriting it)
├── overview-progress.md         Day 1 status as of 13:05; historical
└── Day 1 working notes (kept for the trail, some superseded -- see the note at the top of each):
    IMPLEMENTATION_SUMMARY.md, IMPLEMENTATION-SUMMARY.md, ISSUE-18-SUMMARY.md,
    ISSUE_15_QUICKSTART.md, ISSUE_15_STATUS.md, P5-IMPLEMENTATION.md, P6-TRUST-AND-LOYALTY.md
```

`IMPLEMENTATION-SUMMARY.md` and `ISSUE-18-SUMMARY.md` were moved here from the repository root so
the root holds only the README, LICENSE, `CLAUDE.md`/`AGENTS.md`, the run scripts and directories.

**Note on `round2/pyproject.toml`.** It is also named `bondlayer` and lists packages
(`interpreter`, `ucp`, `adapters`) that do not exist under `round2/`. Do not `pip install` it; it is
only there so `pytest tests` works from this folder. The one real package is `bondlayer/pyproject.toml`.

## Day 1 branches → what they became

| Branch | Became |
|---|---|
| `feat/nguyen-ucp-head` | `bondlayer/src/bondlayer/ucp/` (profile, capabilities, server, onboard, policy_onboard), `bondlayer/src/bondlayer/adapters/catalog.py`, `bondlayer/app/dashboard/` |
| `feat/hieu-interpreter` | `bondlayer/src/bondlayer/interpreter/` (parser; resolver being built by WS-A) |
| `feat/bach-records-signing`, `feat/bach` | `buyer-agent/` (agent + UI), `round2/valuation/` (absorbed into `bondlayer/src/bondlayer/records/` and `valuation/`) |
| `feat/minh-console` | `bondlayer/src/bondlayer/agent/` (composition root + trace), `bondlayer/app/dashboard/` |
| `feat/nha-eval-data` | `bondlayer/data/` (catalogue, records, policies, `eval/requests.json`) and `bondlayer/docs/` |

All five were merged into `round2/dev` on 12/09; each is 0 commits ahead of it (DAY2-PLAN §1).

## Status

Do not read status from this file. `DAY2-PLAN.md` §1 is the verified state at 16:20 on 12/09, and
§5 is the clock. The numbers policy (§6) applies: a figure appears in a pitch document only if it is
in `bondlayer/docs/eval-results.md` with a commit hash.

## Key references

- Problem statement: [`../docs/FPT-Problem-Statement-Final.pdf`](../FPT-Problem-Statement-Final.pdf)
- Rulebook: [`../docs/Hackathon-Rulebook-2026-Final-Updated-1.pdf`](../Hackathon-Rulebook-2026-Final-Updated-1.pdf)
- Merchant service and wire contract: [`../bondlayer/README.md`](../../bondlayer/README.md)
- Pre-hackathon spikes (reference only, not submission code): [`../archive/README.md`](../../archive/README.md)
