# `feat/nha-eval-data` — Thanh Nha Phan (PM / lead)

**Phase 0. This branch is a gate.** Nothing from Phase 1 merges to `round2/dev`
until the analysis here is landed and readable. Target: **12:00, Day 1.**

## Why it gates

Assumption A2 in our Round 1 proposal states the evaluation set was frozen
*before* the enriched feed existed. The commit timestamp on this branch is the
only proof of that claim. If the interpreter lands first, we quietly invalidate
our own headline result — and it is the kind of thing a sharp judge asks about
in the 5-minute Q&A.

It gates for a second reason: nobody downstream can build intent matching
against a catalogue that does not exist yet. This branch is the substrate.

## Deliverables

### 1. Intent taxonomy — `data/eval/taxonomy.md`

The analysis everyone else codes against. What a multi-constraint request
actually contains, and how the four clause kinds are told apart:

| Kind | Example clause | Answered by |
|---|---|---|
| `HARD` | "under $1,500" | catalogue attribute, filterable |
| `SOFT` | "good enough for design work" | catalogue attributes, ranked not filtered |
| `SERVICE` | "I can return it easily" | benefit record — no catalogue attribute answers this |
| `VALUES` | "a brand that actually repairs things" | benefit record + policy facts |

The `SERVICE` and `VALUES` rows are the whole argument for BondLayer: they are
the constraints a normal catalogue **cannot** answer. Make that visible in the
taxonomy document, because it is the slide.

### 2. Evaluation set — `data/eval/requests.json` (FROZEN)

30 multi-constraint requests with gold answers. Each entry:

- the utterance, as a shopper would say it
- its decomposition into typed constraints
- the gold SKU set
- which constraint each expected citation should resolve against

Commit it in one commit, say `freeze: 30-request evaluation set` in the message,
and do not touch it again. Hieu tunes the interpreter against it; if it moves
after he starts, the numbers mean nothing.

Spread the difficulty: some requests fully satisfiable, some with one constraint
deliberately unsatisfiable (the interpreter must flag it honestly rather than
silently drop it), some with near-duplicate SKUs where only a benefit record
breaks the tie.

### 3. Catalogue — `data/catalog/electronics.csv`

60–100 SKUs: phones, laptops, accessories, appliances, warranty add-ons.
Consumer electronics, per §2.2 of the proposal.

Plant the mess deliberately — inconsistent units, missing attributes,
near-duplicate titles, price formats that differ. A clean catalogue makes the
adapter and the interpreter look better than they are, and Nguyen needs
something real to normalise.

### 4. Policy prose — `data/policies/*.md`

Returns, warranty, loyalty tiers, trade-in, delivery thresholds. Written as
actual retailer prose, with conditions, thresholds and exceptions buried in
sentences — that is what Hieu's converter has to extract from. Do not write it
as a table; a table is the answer, not the input.

## Then, after the gate

- **15:30–16:00 Problem Setter window.** You lead. Bring the §3.2 open
  questions. Write down the answers and make sure something visibly changes as a
  result — Round 2 scores "Adaptation & upgrade" at 10 points for exactly this.
- **Market strategy (25 points, equal-highest).** Segment, competitive advantage
  vs UCP Identity Linking and Talon.One UIP, GTM roadmap, the §4.3 cost model.
  Most of it exists in the Round 1 PDF; your job is getting it into the README
  and the deck, where the Round 2 judges will actually look.
- **Keep the clock.** Call the 12:00 integration, the 14:30 fallback decision,
  and tomorrow's 12:00 feature freeze out loud.

## Done when

Four artefacts are on this branch, the eval set is frozen in its own commit, and
you have told the team in the channel that the gate is open.

---

## Added from the Round 2 alignment analysis

### The demo scenario has to change — this is the important one

Analysis §3.1(c): all three merchants in the old spike sell the **same jacket**,
barcode `9312345678907`, in all three catalogue exports. That is an excellent
vehicle for verification and valuation and a **null vehicle for intent
matching** — there is nothing to match.

Rebuilding that scenario would demonstrate the criterion judged *third* and not
the one judged *first*. So the merchants need **different, comparable-but-not-
identical products**, such that matching decides something before valuation
does.

Handover §8 assumes **three** merchant profiles; the current plan has two
(control + BondLayer). Three makes ranking a ranking rather than a coin flip.
Your call, since it is your data — but tell Nguyen the count before he wires the
server.

### Values claims in the policy prose (gap 5)

The ontology now carries `sustainability`, `ethical_sourcing`, `durability`,
`repairability` as claims that are **validated but never priced**.

Author them into the policy documents, and put one **unsigned greenwashing
claim** in the control merchant's data. That is the demo moment: a verified
durability claim beats an unverifiable green adjective, using the same signing
story already being told about money — at almost no build cost.

### Electronics throughout (gap 9)

Decision-log item 3 switched the vertical footwear → consumer electronics, and
all new material must use electronics examples. This is about the deck, the
README and anything spoken — the old jacket spike is not submission code, so it
is not the problem. Anything a judge reads or hears is.

### Q&A rehearsal (open item 5) — yours to schedule

Handover §9 has ten questions with rehearsed answers and per-person assignments
(Ford 1 & 5 · Manh 3 & 8 · Bach 2 & 9 · Chan 7 & 10 · Hieu 4 & 6). Round 3 Q&A
is **25 points**.

**Q2 is the one to drill** — Talon.One UIP was deliberately removed from the
written proposal, so the answer exists only as rehearsal. Slot it into Day 2
15:00–16:30 alongside the demo run-throughs.

Also confirm the "Chan" ↔ Minh Truong mapping in those assignments — the
handover roster and the submitted team block use different names.

### Say 30, not 100+

Proposal §6 Phase 4 promised an evaluation set of 100+ multi-constraint
requests. We ship 30. Say "30, frozen before the enriched feed existed" — a
smaller honest number with a method behind it beats a larger one that cannot be
defended in Q&A.
