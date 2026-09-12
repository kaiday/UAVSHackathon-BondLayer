# BondLayer — Round 2 work split

**Clean room.** Every file in `bondlayer/` is written on 12–13/09/2026, inside the
competition window. Nothing is copied from `bach-demo/` or `demo/`. The design
source of truth is the submitted Round 1 proposal (§5.2 component table).

**Team name: BondLayer.** Settled 12/09 — pitch title and team-info block.

**Gap coverage:** `GAPS.md` maps every gap in the Round 2 alignment analysis to an owner.

**Shared contract:** `src/bondlayer/types.py`. Everyone imports it. Changing a
field means telling the team in the channel first — five people depend on it.

---

## What we deliver

Three surfaces over one core:

| Surface | What it is | Whose |
|---|---|---|
| **User chat** | The buyer-agent stand-in. A shopper states a need in natural language; the simulated agent turns it into a structured UCP request. **This is the test harness, not our product** — FPT put consumer-facing shopping assistants out of scope, so it is labelled and pitched as the agent stand-in (assumption A2). | Minh |
| **Merchant dashboard** | The merchant side. Per agent request: fields exposed, legible share of the real offer, verified value credited, value withheld by the wire — and why we lost. | Minh |
| **Console log** | The AI chain of thought. Constraints parsed, records cited per constraint, effective-cost arithmetic, ranking decision. **This is the one FPT weights highest** — it makes the machine-to-machine logic visible. | Minh + Hieu |

---

## Build order

The value layer is worthless without something worth matching against first. So
we build front to back, not back to front.

### Phase 0 — GATE · Nha · analysis visible before anything else moves

Nothing in Phase 1 merges to `round2/dev` until the analysis is landed and
readable on `feat/nha-eval-data`:

- Intent taxonomy: what a multi-constraint request actually contains, and how
  hard / soft / service / values clauses are told apart
- **30-request evaluation set with gold answers, frozen and committed**
- Synthetic catalogue, 60–100 SKUs, with deliberate attribute noise and
  near-duplicates
- Policy / loyalty / warranty prose for the converter to read

This is a gate for a reason: assumption A2 in the proposal claims the eval set
was frozen *before* the enriched feed existed, and the commit timestamp is the
only proof of that. Building the interpreter first would quietly invalidate our
own headline claim.

### Phase 1 — Intent layer + catalogue worth matching against

Hieu (interpreter) and Nguyen (catalogue + UCP head), in parallel.

**Proves:** a complex multi-constraint query goes in; matched SKUs come out with
one cited justification per constraint, and an honest list of what could not be
satisfied. This alone answers FPT's #1 criterion, and the chat UI + console log
make it visible.

If we shipped only Phase 1, we would still have a defensible demo. That is the
point of putting it first.

### Phase 2 — Verification + valuation

Bach. Signed benefit records, ES256 object signing, deterministic effective
cost. **Proves:** the claims the interpreter cites are trustworthy and bounded —
an unsigned record earns nothing, and inflating a ceiling cannot buy rank.

### Phase 3 — Loyalty

Member recognition through linked identity, consented enrolment, records
re-asserted at checkout through UCP's loyalty extension. The dashboard's money
figures become real here.

---

## Who owns what

| Owner | Role | Branch | Scope | Phase |
|---|---|---|---|---|
| **Thanh Nha Phan** | PM / lead | `feat/nha-eval-data` | Intent taxonomy, eval set, catalogue, policy docs, deck, Problem Setter window | **0 — gate** |
| **Minh Hieu Tran** | ML | `feat/hieu-interpreter` | Constraint interpreter, then policy converter | 1, then 2 |
| **Hoang Manh Nguyen** | SE | `feat/nguyen-ucp-head` | Catalogue adapter, UCP profile, capability negotiation, extension | 1 |
| **Thanh Bach Ly** | SE | `feat/bach-records-signing` | Record schema, ES256 object signing, valuation library, loyalty | 2, then 3 |
| **Ha Anh Minh Truong** | UX | `feat/minh-console` | Chat UI + console log (Phase 1), dashboard (Phase 2–3) | 1, then 2–3 |

## Critical path

```
Nha: taxonomy + catalogue + eval set  ── GATE ──┐
                                                ├─→ Hieu: interpreter ──┐
                                                └─→ Nguyen: UCP serves ──┤
                                                                         ├─→ Minh: chat + console log
                                    Bach: signing + valuation ──────────┘        then dashboard
```

Bach is not idle during Phase 0/1: he writes the three invariant tests and the
canonical-JSON serialiser, both of which need no catalogue.

---

## Day 1 — Monday 12/09

| Time | What |
|---|---|
| **10:00–10:20** | Read this file and your brief. Confirm `types.py`. Nha reads the demo script aloud so all five hear the same story. |
| 10:20–**12:00** | **Nha lands the gate.** Everyone else builds against stubs and fixtures on their own branch. Bach writes invariants. |
| **12:00–12:30** | First integration. Deliberately early — find the seams before lunch, not after. All five branches must already merge cleanly, even if three still return fixtures. |
| 13:00–14:30 | Phase 1 on real data: interpreter over the real catalogue, UCP serving it, chat + console log on live output. |
| **14:30–15:30** | Vertical slice, all hands: intent in → SKUs matched → cited justification → signed records → effective cost → ranking → dashboard out. |
| **15:30–16:00** | **Problem Setter window.** Nha leads with the §3.2 open questions. Write down what they say and act on it visibly — Round 2 scores "Adaptation & upgrade" 10 points for exactly this. |
| 16:00–17:00 | Harden or extend, decided by what actually works at 16:00. Push. Write down tomorrow's scope. |

**14:30 fallback:** if policy extraction is weak, drop to a curated record set
and keep the interpreter + comparison as the demonstrated result. Decide at
14:30, not at 16:30.

## Day 2 — Tuesday 13/09

| Time | What |
|---|---|
| 09:15–11:00 | Surfaces UX pass · one-command setup script · README + architecture docs |
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
*"visual polish of human-facing dashboards is a lower priority than the logic of
the machine-to-machine interaction."* That is why the console log outranks the
dashboard in our build order, and why Phase 1 comes before Phase 2.

The demo query:

> *"A laptop under $1,500 I can return easily if it turns out not to suit my
> work, from a brand that actually repairs things."*

Hard price filter · soft performance constraint · service constraint · values
constraint. One cited record per constraint. A higher list price legitimately
wins on effective cost. The dashboard then explains the loss to the merchant.

Round 2 scoring: UX 20 · Technical quality 25 · Deployability 20 ·
**Market strategy 25** · Adaptation & upgrade 10. Market strategy is
equal-highest and is where strong technical teams drop points — Nha owns getting
it into the README and the deck, not just the Round 1 PDF.

---

## Branching

Integration branch is **`round2/dev`**. Nobody commits to it directly; it moves
by pull request only. `main` stays clean until the final submission merge.

```
git fetch origin
git checkout round2/dev && git pull
git checkout feat/<yours>
```

Each branch carries its own scope note in `bondlayer/branches/<owner>.md`.

**Rules for today:**

- **Commit small and often.** The commit trail is our proof the code was written
  inside the window. One big push at 16:00 looks exactly like pre-written code,
  which is a disqualification condition — so don't do that.
- **Never edit `src/bondlayer/types.py` on a feature branch.** It is the seam
  five people share. A change goes to the channel first, then straight onto
  `round2/dev` as its own commit, then everyone rebases.
- **Open a PR into `round2/dev` as soon as your stub runs**, not when your
  feature is finished.
- Stay inside your own directory. Directories were assigned so five people can
  work for two hours without touching the same file.

---

## Not attempted in 16 hours

Real payment flows · production authentication · live merchant integration ·
protocol certification. Say this out loud in the pitch; scoping deliberately
reads better than scoping accidentally.
