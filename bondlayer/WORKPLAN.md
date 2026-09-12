# BondLayer — Round 2 work split

**Clean room.** Every file in `bondlayer/` is written on 12–13/09/2026, inside the
competition window. Nothing is copied from `bach-demo/` or `demo/`. The design
source of truth is the submitted Round 1 proposal (§5.2 component table); those
two older folders are not submission code and must not be imported from.

**Shared contract:** `src/bondlayer/types.py`. Everyone imports it. Changing a
field means telling the team in the channel first — five people depend on it.

---

## Who owns what

| Owner | Role | Components (Round 1 §5.2) | Deliverable by 17:00 Day 1 |
|---|---|---|---|
| **Hoang Manh Nguyen** | Software Engineer | 1 Catalogue adapter · 6 UCP capability negotiation & extension | A UCP server that answers `catalog.search` / `catalog.lookup`, publishes `/.well-known/ucp`, negotiates the benefit extension, and degrades to plain UCP when the agent doesn't declare support |
| **Thanh Bach Ly** | Software Engineer | 3 Benefit record schema · 4 Object signing & key publication · 7 Valuation library | ES256 object signing over canonical record JSON, `signing_keys[]` in the profile, and deterministic `effective_cost()` with the arithmetic exposed |
| **Minh Hieu Tran** | ML Engineer | 5 Constraint interpreter · 2 Policy converter | Multi-constraint parse → resolve → cited justification; LLM drafts typed records from prose with a quoted source span and a human approval gate |
| **Ha Anh Minh Truong** | UX/UI Designer | 8 Merchant visibility console · demo surface | The two-pane comparison screen (control merchant vs BondLayer merchant) and the console's four figures |
| **Thanh Nha Phan** | Product Manager / lead | Evaluation set · synthetic catalogue · control merchant · deck · Problem Setter window | 30 frozen multi-constraint requests with gold answers, 60–100 SKU catalogue, and the pitch narrative |

---

## Critical path

```
Bach: schema + signing ──┐
                          ├─→ Hieu: interpreter ──→ Nguyen: UCP serves it ──→ Minh: console renders it
Nha: catalogue + eval ───┘                                                     ↑
                                                          Bach: valuation ─────┘
```

Nobody is blocked at the start: `types.py` already defines every seam, so all
five can code against stubs from minute one and integrate at 12:00.

---

## Day 1 — Monday 12/09, now → 17:00

| Time | What |
|---|---|
| **10:00–10:20** | Read this file. Confirm contracts in `types.py`. Nha reads the demo script aloud so all five hear the same story. |
| 10:20–12:00 | Parallel build against stubs. **Nha freezes the 30-request eval set and commits it before any enriched feed exists** — assumption A2 in the proposal depends on this being true, and a judge can check the commit timestamp. |
| **12:00–12:30** | First integration attempt. Deliberately early — find the seams before lunch, not after. |
| 13:00–14:30 | Constraint interpreter over real catalogue + records. Console on live data. Control merchant served through the *same* code path (A2). |
| **14:30–15:30** | Vertical slice, all hands: intent in → SKUs matched → signed records returned → effective cost → ranking → console out. |
| **15:30–16:00** | **Problem Setter window.** Nha leads, brings the §3.2 open questions. Whatever they answer, write it down and act on it visibly — Round 2 scores "Adaptation & upgrade" at 10 points for exactly this. |
| 16:00–17:00 | Harden or extend, decided by what actually works at 16:00. Push. Write down tomorrow's scope. |

**14:30 fallback:** if policy extraction quality is weak, drop to a curated
record set and keep the constraint interpreter + agent comparison as the
demonstrated result. Decide at 14:30, not at 16:30.

## Day 2 — Tuesday 13/09, 09:00 → 17:00

| Time | What |
|---|---|
| 09:15–11:00 | Console UX pass · one-command setup script · README + architecture docs |
| 11:00–12:00 | Evaluation run on the frozen set: control vs BondLayer. **Every number in the pitch comes from here.** |
| **12:00** | Feature freeze. Nothing new enters the product. |
| 13:00–15:00 | Clean-machine test from a fresh clone. Technical documentation done. Pitch built against real results. |
| 15:00–16:30 | Seed demo state, rehearse twice, record a backup video, final commit. |
| 16:30–17:00 | Submit with buffer. Hard deadline 17:00 — late submissions are not accepted. |

Venue wifi is shared by twenty teams. The demo runs from seeded state, not live calls.

---

## What we are judged on

FPT's stated order of weight: **(1) intention accuracy & semantic matching,
(2) technical architecture, (3) business value & conversion.** Their note:
*"visual polish of human-facing dashboards is a lower priority than the logic
of the machine-to-machine interaction."*

So the demo leads with the hard query, not with the console:

> *"A laptop under $1,500 I can return easily if it turns out not to suit my
> work, from a brand that actually repairs things."*

Hard price filter · soft performance constraint · service constraint · values
constraint. One cited record per constraint. A higher list price legitimately
wins on effective cost. The console then explains the loss to the merchant.

Round 2 scoring: UX 20 · Technical quality 25 · Deployability 20 ·
**Market strategy 25** · Adaptation & upgrade 10. Market strategy is
equal-highest and is usually where strong technical teams drop points — Nha
owns getting it into the README and the deck, not just the Round 1 PDF.

---

## Not attempted in 16 hours

Real payment flows · production authentication · live merchant integration ·
protocol certification. Say this out loud in the pitch; scoping deliberately
reads better than scoping accidentally.

---

## Branching

Integration branch is **`round2/dev`**. Nobody commits to it directly; it moves
by pull request only. `main` stays clean until the final submission merge.

| Owner | Branch |
|---|---|
| Nguyen | `feat/nguyen-ucp-head` |
| Bach | `feat/bach-records-signing` |
| Hieu | `feat/hieu-interpreter` |
| Minh | `feat/minh-console` |
| Nha | `feat/nha-eval-data` |

```bash
git fetch origin
git checkout round2/dev && git pull
git checkout feat/<yours>
```

**Rules for today:**

- **Commit small and often.** The commit trail is our proof the code was written
  inside the window. One big push at 16:00 looks exactly like pre-written code,
  which is a disqualification condition — so don't do that.
- **Never edit `src/bondlayer/types.py` on a feature branch.** It is the seam
  five people share. A change goes to the channel first, then straight onto
  `round2/dev` as its own commit, then everyone rebases.
- **Open a PR into `round2/dev` as soon as your stub runs**, not when your
  feature is finished. The 12:00 integration needs five branches that already
  merge cleanly, even if three of them still return fixtures.
- Stay inside your own directory. Directories were assigned so that five people
  can work for two hours without touching the same file.
