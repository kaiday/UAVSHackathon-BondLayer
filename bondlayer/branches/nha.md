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
