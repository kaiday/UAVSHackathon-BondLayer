# Overview progress — Day 1

*Revised 12/09 ~11:50 AEST. Supersedes the 11:10 version. Every status claim below was
re-checked against `origin/round2/dev` rather than restated.*

> **The 12:00 integration checkpoint is ~10 minutes away and four of five branches
> contain no code.** Read §3 first. Everything else can wait until after the checkpoint.

---

## 1. Where the repo actually stands

| Branch | Ahead of `round2/dev` | Contents | Verified |
|---|---|---|---|
| `feat/nha-eval-data` | 0 — fully merged | Phase 0 landed 10:49–10:52 | ✅ |
| `feat/hieu-interpreter` | 5 | `branches/hieu.md` only — no code | ✅ |
| `feat/nguyen-ucp-head` | 5 | `branches/nguyen.md` only — no code | ✅ |
| `feat/bach-records-signing` | 5 | `branches/bach.md` only — no code | ✅ |
| `feat/minh-console` | 5 | `branches/minh.md` only — no code | ✅ |

**The gate is open** (`b5281f5`, 10:52). On `round2/dev` you have:

- `src/bondlayer/types.py` — 232 lines. **13 frozen dataclasses/enums and 5 protocols**
  (`CatalogAdapter`, `PolicyConverter`, `Signer`, `ConstraintInterpreter`,
  `ValuationLibrary`). *The earlier "6 protocols" was wrong — see §3.2, the missing
  one is load-bearing.*
- `data/eval/requests.json` — 30 requests, frozen, with `freeze_rule` and gold SKUs
- `data/catalog/electronics.csv` — 148 SKUs across `VOL-` / `CIT-` / `NOR-`
- `data/policies/` — three policy docs + `manifests.json`

**Merchant count is settled at three** — `voltway` (bondlayer), `citycircuit` (control),
`northgear` (competitor). This closes the open question in both Nguyen's and Minh's
scope notes; neither needs to ask Nha before wiring.

Everything downstream of the gate is unstarted. Day 1, with a 17:00 Day-2 deadline.

---

## 2. Three corrections to the written plan

These are drifts between the planning docs and the data that actually landed. Fix the
docs, not the data.

### 2.1 The unsigned greenwashing claim is in **northgear**, not citycircuit

`GAPS.md` gap 5 and `branches/minh.md` both say *"the control merchant's data."* The
landed data puts it in `manifests.json → northgear.planted_unsigned`, and that placement
is correct:

- `citycircuit.expect_records` is `[]`, with `_why_empty`: the control publishes a plain
  feed, *"That is the status quo, not a strawman."* A control that publishes an unsigned
  claim has stopped being a control.
- The northgear entry carries its own reason: *"R12 must not be won by this."* R12 is
  *"I want the most sustainable phone you sell"* — the claim sits exactly where the eval
  set needs it to.

**Action:** correct the wording in `GAPS.md` and `branches/minh.md`. Do not move the
record. Nobody should act on the old wording.

### 2.2 Semantic matching means embeddings, and that has to stay visible

`GAPS.md` gap 2 is Critical and exists *specifically* because a vaguer brief would let us
rebuild substring matching — the analysis found the spike matching on title and brand,
*"precisely the thing criterion 1 says to go beyond."* It is on `branches/hieu.md:92` and
it belongs at the top of Hieu's task list, not in the tail of a scope note. See T-H1.

### 2.3 The ES256 / Ed25519 conflict blocks **two** branches, not one

| Source | Says |
|---|---|
| `branches/bach.md` | ES256, *"do not drift to Ed25519"* |
| `WORKPLAN.md` Phase 2 | ES256 |
| Handover §8, locked stack | PyNaCl / Ed25519 |
| Alignment analysis §2 | credits Ed25519 as the existing asset |

Bach cannot sign, **and Nguyen cannot finalise `/.well-known/ucp`'s `signing_keys[]`**,
until Ford rules. Both branches are on the critical path.

---

## 3. Blockers — clear these before anything else

### 3.1 ES256 or Ed25519 — Ford's call, blocking Bach + Nguyen

The only unresolved decision on the critical path. Ask now, in the channel, not in a
standup. Default if Ford is unreachable by 12:15: **Ed25519/PyNaCl**, because it is the
locked stack and the one the spike proved — and log the deviation from the submitted docx
rather than stalling.

### 3.2 There is no `Bundler` protocol in `types.py` — blocking Nguyen's gap 4

`Bundle` exists as a dataclass. The seam that produces one does not. `WORKPLAN.md`
forbids editing `types.py` on a feature branch: *"a change goes to the channel first, then
straight onto `round2/dev` as its own commit, then everyone rebases."* So this is a
two-minute change with a mandated process, and it has to happen before Nguyen reaches
bundling. See T-N5.

### 3.3 Nobody has pushed code and the checkpoint is now

The rule in `WORKPLAN.md` is **"open a PR into `round2/dev` as soon as your stub runs"** —
not when the feature is done. Stubs at 12:00 are worth more than features at 16:00, and a
single large 16:00 push looks exactly like pre-written code, which is a disqualification
condition. Push a failing stub rather than nothing.

---

## 4. Technical task breakdown

Re-cut from the branch notes into ordered, independently-pushable units. Each task names
its file, its dependency, and what "done" means. **T-x1 for every owner is a stub that
compiles and is pushable by 12:00.**

Legend: 🔴 critical path · 🟡 needed for the demo · 🟢 stretch

### Nha — `feat/nha-eval-data` · Phase 0 complete, now PM

Her build work is landed. What remains is the 25-point half of the scoreboard.

| ID | Task | Dep | Done when |
|---|---|---|---|
| T-A1 🔴 | Get Ford's ruling on §3.1 and post it in the channel | — | Bach and Nguyen both unblocked |
| T-A2 🔴 | Fix the citycircuit→northgear wording in `GAPS.md` + `branches/minh.md` (§2.1) | — | Committed on `round2/dev` |
| T-A3 🔴 | Call the clock out loud: **12:00** integration · **14:30** fallback decision · Day 2 **12:00** freeze | — | Each called at the time, not after |
| T-A4 🟡 | **Market strategy into README + deck** — 25 pts, equal-highest, and where strong technical teams drop points | — | It exists in writing, not just the Round 1 PDF |
| T-A5 🟡 | Retire jacket material from all spoken/written output; electronics examples throughout (gap 9) | — | Deck + README carry no footwear/jacket examples |
| T-A6 🟡 | **15:30–16:00 Problem Setter window** — lead with the §3.2 open questions | — | Something visibly changes afterwards (10 pts, Adaptation) |
| T-A7 🟡 | Schedule the Q&A rehearsal; drill **Q2 (Talon.One / UIP)** | — | Day 2 15:00–16:30 booked. This answer exists only as rehearsal, nowhere in writing |
| T-A8 🟢 | Carry the positioning line into the deck: *"In a room full of agents, we are building the thing agents read"* | T-A4 | It is in the pitch, not only in `docs/solution-bondlayer-summary.md` |

### Hieu — `feat/hieu-interpreter` · Phase 1 · heaviest branch, #1 judged criterion

`src/bondlayer/interpreter/` runs end to end **before** `converter/` opens.

| ID | Task | Dep | Done when |
|---|---|---|---|
| T-H1 🔴 | **Matching is embeddings + attribute filters, not substring** (gap 2). Exact model/GTIN is the declared MVP fallback per handover §8 — a fallback, not the plan | gate | Near-duplicates in the catalogue are resolved by similarity, and you can say on stage why substring fails on them |
| T-H2 🔴 | Constraint parse: utterance → `list[Constraint]` across HARD / SOFT / SERVICE / VALUES | gate | The 30-request eval set parses without exception |
| T-H3 🔴 | `ConstraintInterpreter` stub returning fixture `Proposal`s — **push by 12:00** | — | Nguyen and Minh can import and wire |
| T-H4 🔴 | Every `ResolvedConstraint` carries a cited `evidence_record_id` **or** `evidence_attribute` **plus** a human-readable `note` | T-H2 | No resolved constraint has an empty note. FPT asked for justification prose, not a SKU list |
| T-H5 🔴 | Populate `Proposal.unsatisfied` honestly | T-H2 | The eval requests engineered to catch silent drops do catch them |
| T-H6 🟡 | Resolve `ConstraintKind.VALUES` against `value_ceiling_aud = None` records (gap 5) | T-H4, T-B4 | *"From a brand that actually repairs things"* cites a signed `repairability` record. Cite them exactly like any other — only valuation cares about the ceiling |
| T-H7 🟡 | **The pitch numbers:** constraint-satisfaction rate + citation precision, both against `citycircuit` as baseline | T-H2–H5 | Numbers come from the frozen set, reproducible on Day 2 11:00–12:00 |
| T-H8 🟢 | Phase 2 `converter/`: every draft quotes `source_span`; nothing publishes without human approval | T-H1–H5 done | **Demo the approval gate as a feature**, not a limitation |

**Not his:** bundling (Nguyen's, T-N5).

### Nguyen — `feat/nguyen-ucp-head` · Phase 1

| ID | Task | Dep | Done when |
|---|---|---|---|
| T-N1 🔴 | `/.well-known/ucp` profile + routing, against a 10-row fixture CSV of your own — **push by 12:00** | — | Resolves and returns a capability list |
| T-N2 🔴 | `adapters/catalog.py` → `CatalogAdapter` over the 148-SKU CSV. **The noise is the deliverable** | gate | Normalises the planted noise, units and near-duplicate titles. Keep the repair count — *"repaired N malformed attributes across 148 SKUs"* is a slide |
| T-N3 🔴 | **Capability negotiation — serve the intersection, with no special-case branch** | T-N1 | An agent with the extension and an agent without it get valid responses **from the same code path**. Someone will ask you to prove it; make it structurally true, not conditionally true |
| T-N4 🔴 | Three merchant profiles from `manifests.json`; **the control is the same server with enrichment off** | T-N2 | This is the single most important correctness property on the branch — if the control is a different implementation, the comparison proves nothing |
| T-N5 🟡 | `catalog.lookup` carries the benefit extension; `signing_keys[]` publishes **Bach's** key — never generate one | T-N3, §3.1 | A record of Bach's verifies end to end against the published key |
| T-N6 🟢 | **Dynamic bundling** (gap 4) — compose Hieu's `Proposal`s into a `Bundle`. Needs the `Bundler` protocol on `round2/dev` first (§3.2) | T-N5, T-H4 | `rationale` says why items belong *together* — not why each matched, that is already in the notes. **A bundle of one is a valid degenerate case**, so this can ship partially and still count |

**Constraint on every task:** runs from seeded state, zero network calls. Venue wifi is
shared by twenty teams.

### Bach — `feat/bach-records-signing` · Phase 2, then 3 · not gated, start cold

| ID | Task | Dep | Done when |
|---|---|---|---|
| T-B1 🔴 | **`tests/test_invariants.py` before any other code.** (1) a tampered record fails verify; (2) an unsigned record credits zero; (3) inflating `value_ceiling_aud` to $9,999 does not change ranking | — | All three run red, then green. **Test 3 is the one that survives Q&A** — the obvious attack is *"what stops a merchant claiming a $10,000 warranty"*, and the answer should be a test running on screen, not a paragraph |
| T-B2 🔴 | Canonical JSON serialiser in `records/` — **before the crypto** | — | Deterministic bytes for a `BenefitRecord`. A signature over non-canonical JSON is worthless |
| T-B3 🔴 | Detached per-record object signing, algorithm per §3.1 | T-B2, §3.1 | **Object-level, not RFC 9421 transport-level.** If asked at the Gala why not UCP message signing: theirs is ephemeral and authenticates a response in flight; ours survives the response, so an agent can cache it, re-verify later, and cite it |
| T-B4 🟡 | `valuation/`: `effective_cost()`, `credited = min(ceiling, shopper_policy_value)`, zero if unverified. **No model call anywhere in this file** | T-B3 | Returns the `CreditedBenefit` breakdown, not just a total — Minh renders the working and the agent cites it. Write it as if someone hostile will read it, because that is the point of shipping it open |
| T-B5 🟡 | Values claims are `BenefitRecord`s with `value_ceiling_aud = None` — **do not special-case them** (gap 5) | T-B3 | They sign and verify through the existing path and contribute exactly zero. One extra invariant: a *signed* and an *unsigned* values claim both credit $0, but **only the signed one may be cited.** Verification and valuation are separate questions |
| T-B6 🟡 | Plant the unsigned **"$50 agent bonus"** record in the demo data | T-B1 | It visibly earns nothing on screen. That single moment is the strongest thing in the pitch |
| T-B7 🟢 | Phase 3 loyalty: member recognition via linked identity, consent-gated enrolment, records re-asserted at checkout | T-B4 | Values at discovery are **indicative, not binding** — say so; UCP requires eligibility enforcement at checkout |
| T-B8 🟢 | **Close the API loop** (gap 7) — checkout settles rather than sets a status flag | T-B7 | **Idempotent** and explicitly confirmed; create and confirm are separate steps, and replaying a confirmation must not double-credit. **No real payment flow** — a simulated settlement is inside the stated boundaries. Do not let it grow |

Day 2 09:15–11:00 is his polish pass.

### Minh — `feat/minh-console` · Phase 1, then 2–3

*Omitted from the previous version. He owns three surfaces, one of which
`WORKPLAN.md` calls **"the one FPT weights highest."***

| ID | Task | Dep | Done when |
|---|---|---|---|
| T-M1 🔴 | **Console log first** — the AI chain of thought, built against `Proposal` / `EffectiveCost` / `RequestReport` fixtures. Push a stub by 12:00 | — | Renders constraints parsed → records cited → arithmetic → ranking as a readable trace, not a log dump |
| T-M2 🔴 | Keep the `← no catalogue attribute answers this` markers on SERVICE and VALUES constraints | T-M1 | **That marker is the product thesis rendered on screen. Do not let it get designed away** |
| T-M3 🔴 | User chat, **labelled in the UI as the buyer-agent stand-in** | T-M1 | FPT put consumer-facing shopping assistants out of scope. Same pixels either way; the label is what keeps us in scope. A judge reading the screen must never think we built a shopping assistant |
| T-M4 🟡 | **Three visually distinct record states** (gap 5): signed+priced → cited and credited · signed+unpriced → cited, visibly **$0** · unsigned → displayed, **never cited** | T-B5, T-H6 | Rows 2 and 3 both credit nothing and a viewer still sees instantly that one is trusted evidence and the other is not. **This is the demo moment** |
| T-M5 🟡 | **The control/BondLayer toggle as the centrepiece** — two panes, one switch, same query, same code path | T-N4 | It is the moment the pitch turns. Design it as the centrepiece, not a control |
| T-M6 🟡 | Merchant dashboard: exactly four figures per request — fields exposed · legible share of the real offer · verified value credited · value withheld by the wire — **plus why we lost** | T-B4 | *Why we lost* is the line an e-commerce lead actually buys: the retailer learns from a lost comparison rather than only from a lost sale |
| T-M7 🟢 | Render a `Bundle` **as a set**, not three stacked search results (gap 4) | T-N6 | Combined price, the bundle's own `rationale`, each item keeping its cited notes underneath. If a bundle looks like a list on screen, we answered the criterion on the wire and lost it in the demo |
| T-M8 🟡 | Three-way ranking layout — the merchant count is settled at three (§1), toggle sits **on top of** the ranking rather than replacing it | T-N4 | Laid out for three now, not re-laid-out at 15:00 |

**Day 1 is for making it true, not pretty.** Day 2 09:15–11:00 is the UX pass. Round 2
still scores UX at 20 — clean and consistent, never at the cost of the logic being visible.

---

## 5. The clock

| Time | What | Owner |
|---|---|---|
| **12:00** | First integration. All five branches merge cleanly **even if three still return fixtures** | all |
| 13:00–14:30 | Phase 1 on real data | Hieu, Nguyen, Minh |
| 14:30–15:30 | Vertical slice, all hands: intent in → matched → cited → signed → effective cost → ranked → dashboard out | all |
| **14:30** | **Fallback decision.** If policy extraction is weak, drop to a curated record set and keep interpreter + comparison as the demonstrated result. **Decide at 14:30, not 16:30** | Nha |
| 15:30–16:00 | Problem Setter window | Nha |
| 16:00–17:00 | Harden or extend, decided by what actually works at 16:00. Push. Write down tomorrow's scope | all |

Day 2: 09:15–11:00 UX + docs · 11:00–12:00 **evaluation run on the frozen set — every
number in the pitch comes from here** · **12:00 freeze** · 13:00–15:00 clean-clone test ·
15:00–16:30 seed, rehearse twice, record a backup video · 16:30 submit with buffer.

---

## 6. Risks, ranked

1. **Four branches with no code at the checkpoint.** The 12:00 integration is the plan's
   entire early-warning mechanism, and it only works if people push stubs.
2. **§3.1 unresolved past 12:15** — two branches idle on a decision nobody has made.
3. **Hieu's branch is the heaviest and carries the top-weighted criterion.** Bundling was
   moved to Nguyen for exactly this reason; resist moving anything else onto him.
4. **Market strategy (25 pts) has no artefact yet.** It is equal-highest with technical
   quality and it is currently a Round 1 PDF.

## 7. Deliberately not attempted

Real payment flows · production authentication · live merchant integration · protocol
certification · the 100+ request eval set from proposal §6 Phase 4 (**we ship 30, frozen
before the feed existed** — a smaller honest number with a method beats a larger one we
cannot stand behind) · the negotiation/counter-offer protocol (gap 8 — Ford's call,
default is that it stays dropped).

Say this out loud in the pitch. Scoping deliberately reads better than scoping accidentally.
