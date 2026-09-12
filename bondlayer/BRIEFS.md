# Individual briefs — Day 1

Read your own section. Everything imports `src/bondlayer/types.py`.
Commit small and often: the commit trail is our evidence that the code was
written inside the window.

---

## Nguyen — UCP head (components 1, 6)

**Build:** `src/bondlayer/ucp/` — the server an agent actually talks to.

- `/.well-known/ucp` profile: capabilities list + `signing_keys[]` (Bach gives
  you the key material; publish it, don't generate it).
- `catalog.search` and `catalog.lookup` returning conformant UCP objects.
- Capability negotiation: the agent declares what it supports, you serve the
  **intersection**. If it doesn't declare the benefit extension, it gets plain
  UCP with **no special-case branch** — that graceful degradation is a claim in
  the proposal (§5.3) and someone will ask you to prove it.
- `src/bondlayer/adapters/catalog.py`: Nha's CSV export → `list[Sku]`.
  Normalise the attribute noise and near-duplicates she plants deliberately.

**Interfaces you own:** `CatalogAdapter`.
**You consume:** `SignedRecord` from Bach, `Proposal` from Hieu.

**Done when:** an agent with the extension and an agent without it both get a
valid response from the same code path, and the control merchant is served by
the same server with the enrichment switched off.

---

## Bach — records, signing, valuation (components 3, 4, 7)

**Build:** `src/bondlayer/records/` and `src/bondlayer/valuation/`.

- Canonical JSON serialisation of a `BenefitRecord` — deterministic byte output,
  because a signature over non-canonical JSON is worthless.
- **ES256** detached signature per record (the proposal says ES256 and
  `signing_keys[]`; don't drift to Ed25519). Publish the public key to Nguyen.
- `verify()` — and the rule that matters: **unsigned or expired records are
  displayed but valued at zero.** Plant one unsigned "$50 agent bonus" record in
  the demo data and let it visibly earn nothing. That single moment is the
  strongest thing in our pitch.
- `effective_cost()`: `credited = min(merchant_ceiling, shopper_policy_value)`.
  Deterministic arithmetic, no model call anywhere in this file. Return the
  working, not just the number — the console and the agent both cite it.

**Interfaces you own:** `Signer`, `ValuationLibrary`.

**Done when:** `pytest` proves (a) a tampered record fails verification,
(b) an unsigned record credits 0, (c) inflating `value_ceiling_aud` to $9,999
does not change the ranking.

*Write those three tests first.* They're the invariants the pitch stands on.

---

## Hieu — constraint interpreter + policy converter (components 5, 2)

**This is the #1 judged criterion. It gets the most of your day.**

**Build:** `src/bondlayer/interpreter/` first, `src/bondlayer/converter/` second.

*Interpreter:*
- `parse()`: utterance → `list[Constraint]`, each tagged HARD / SOFT / SERVICE /
  VALUES. The demo query has one of each on purpose.
- `resolve()`: each constraint against catalogue attributes **and** benefit
  facts, returning one `ResolvedConstraint` with a cited `record_id` or
  `attribute` and a one-line `note`. That note is the justification text the
  agent shows — write it to be read by a judge.
- Flag what you **can't** satisfy. Honest `unsatisfied` beats silent omission,
  and FPT explicitly asked for justification over a SKU list.

*Converter (after the interpreter runs end to end):*
- LLM drafts `BenefitRecord`s from prose policy docs. **Every draft must quote
  its `source_span`**, and nothing publishes without human approval. The
  approval gate is a feature, not friction — say so in the demo.

**Metrics for the pitch:** constraint-satisfaction rate and citation precision
against Nha's frozen 30-request set. Extraction precision + share approved
unedited for the converter.

**If extraction is weak at 14:30:** stop, take the curated record set, keep the
interpreter. Agreed in advance so it's not a defeat on the day.

---

## Minh — console + demo surface (component 8)

**Build:** `app/` — the screen we actually pitch from.

Two panes, one switch: **control merchant vs BondLayer merchant**, same query,
same code path, visibly different outcome. The switch is the demo.

Console shows exactly four figures per agent request (proposal §5.2):
1. fields exposed
2. share of the real offer that was legible
3. verified value the agent could credit
4. benefits withheld by the wire

Plus **why it lost** — that's the line an e-commerce lead buys.

**Read the room on polish:** FPT said dashboard polish ranks *below*
machine-to-machine logic. So make the *reasoning* legible — show the cited
records and the effective-cost arithmetic on screen — before you make it pretty.
Round 2 still scores UX at 20, so it does need to be clean and consistent, just
not at the expense of the logic being visible.

**Done when:** it runs from seeded state with no network call.

---

## Nha — evaluation, data, narrative, Problem Setter

**Before 12:00, in this order:**

1. **Freeze the 30-request evaluation set** with gold answers and commit it
   *before* the enriched feed exists. Assumption A2 in our proposal says the
   eval set was frozen first; the commit timestamp is the proof. This is the
   one task today with a deadline that isn't about time management.
2. Synthetic catalogue, 60–100 SKUs across phones, laptops, accessories,
   appliances, warranty add-ons. Plant attribute noise and near-duplicates —
   a clean catalogue makes the interpreter look better than it is.
3. Policy / loyalty / warranty prose docs for Hieu's converter to read.

**Then:**
- Own the **15:30–16:00 Problem Setter window**. Bring the §3.2 open questions.
  Write down what they say and make sure it visibly changes something — Round 2
  scores "Adaptation & upgrade" 10 points for incorporating their input.
- Pitch narrative and deck skeleton. **Market strategy is 25 points** — segment,
  competitive advantage vs UCP Identity Linking and Talon.One UIP, GTM roadmap,
  the cost model from §4.3. Most of this already exists in the Round 1 PDF; your
  job is getting it into the README and the deck.
- Keep the clock. Call the 12:00 integration, the 14:30 fallback decision, and
  tomorrow's 12:00 feature freeze out loud.
