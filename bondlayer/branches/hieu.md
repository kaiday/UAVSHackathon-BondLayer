# `feat/hieu-interpreter` — Minh Hieu Tran (ML Engineer)

**Phase 1, then Phase 2. This is the #1 judged criterion and it gets most of
your day.**

FPT ranked *intention accuracy and semantic matching* first, ahead of
architecture and ahead of business value. Everything else we build is in service
of this branch being good.

## Scope

`src/bondlayer/interpreter/` first. `src/bondlayer/converter/` only once the
interpreter runs end to end.

### Constraint interpreter (Phase 1 — primary)

**`parse(utterance) -> list[Constraint]`**

Decompose a natural-language request into typed clauses, tagged `HARD` / `SOFT`
/ `SERVICE` / `VALUES` per Nha's taxonomy in `data/eval/taxonomy.md`. The demo
query carries one of each on purpose:

> *"A laptop under $1,500 I can return easily if it turns out not to suit my
> work, from a brand that actually repairs things."*

`HARD` price · `SOFT` performance · `SERVICE` returns · `VALUES` repairability.
The last two are the interesting ones: **no catalogue attribute answers them.**
Only a benefit record does. That gap is the entire product thesis, so make it
legible in your output rather than burying it.

**`resolve(constraints, skus, records) -> list[Proposal]`**

Each constraint against catalogue attributes *and* benefit facts. Return one
`ResolvedConstraint` per constraint carrying either a cited `evidence_record_id`
or an `evidence_attribute`, plus a one-line `note`.

That `note` is the justification text a human reads. FPT asked for *"a logical
justification of why these products match"*, explicitly **not a list of SKUs**.
Write those notes as if a judge will read them aloud, because one will.

**Flag what you cannot satisfy.** Populate `Proposal.unsatisfied` honestly. An
interpreter that admits it could not answer a clause is worth more than one that
silently drops it, and Nha's eval set contains requests designed to catch
exactly that.

### Policy converter (Phase 2 — secondary)

An LLM drafts `BenefitRecord`s from the prose in `data/policies/`.

- **Every draft must quote its `source_span`.** The field exists on
  `BenefitRecord` for this; a draft without one does not publish.
- Nothing publishes without human approval. The approval gate is a feature —
  demo it as one. "A language model read our warranty policy and a human
  approved 14 of 16 drafts" is a better story than silent extraction.

## Metrics you own

From the frozen 30-request set — these numbers go in the pitch:

- **constraint-satisfaction rate** — of all constraints across all requests, how
  many resolved correctly against gold
- **citation precision** — of the citations returned, how many point at a record
  or attribute that genuinely answers that clause
- converter: **extraction precision**, and **share of drafts approved unedited**

Report them against the control merchant too. A number without a baseline is not
a result.

## Working against the gate

Nha's catalogue and eval set land around 12:00. Until then, build `parse()`
against hand-written fixtures of your own — parsing needs no catalogue. Have
`resolve()` stubbed behind the `ConstraintInterpreter` protocol so Nguyen can
wire the UCP head to it before your logic is real.

## Fallback, agreed in advance

If extraction quality is weak at **14:30**, stop the converter, take a curated
record set from Nha, and keep the interpreter as the demonstrated result. That
is a planned branch of the plan, not a failure on the day.

## Done when

The demo query goes in and comes back with matched SKUs, one cited justification
per constraint, an honest `unsatisfied` list, and the whole chain of thought
visible in Minh's console log.
