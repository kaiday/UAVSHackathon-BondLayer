# Gap coverage — from the Round 2 alignment analysis

Every gap in `BondLayer_Round2_Alignment_Analysis.md` §6, plus the open items in
its §7, mapped to an owner and a branch. This is the checklist for "did we
actually cover what the analysis found".

**Team name: BondLayer.** Settled 12/09. Closes handover §11 item 1 — it is the
pitch title and the team-info block.

---

## Ranked gaps (analysis §6)

| # | Gap | Priority | Owner | Branch | State |
|---|---|---|---|---|---|
| 1 | Multi-constraint intent schema — lifestyle, values, use-case — replacing the four-field policy extractor | **Critical** | Hieu | `feat/hieu-interpreter` | Phase 1, core scope |
| 2 | Semantic catalogue matching — embeddings + attribute filters, **replacing substring match** | **Critical** | Hieu | `feat/hieu-interpreter` | Phase 1, **made explicit — see below** |
| 3 | Electronics catalogue, 60–100 SKUs, near-duplicates, attribute noise | **Critical** | Nha | `feat/nha-eval-data` | Phase 0 gate |
| 4 | **Dynamic bundling** — propose a bundle against decoded intent | High | **Nguyen** + Minh (render) | `feat/nguyen-ucp-head`, `feat/minh-console` | **newly assigned** |
| 5 | **Values claims** as signed, validated (not priced) records | High — best effort-to-score ratio | **Bach + Hieu + Nha + Minh** | four branches | **schema landed `2043cac`** |
| 6 | Multi-constraint evaluation set with reported match accuracy | High | Nha | `feat/nha-eval-data` | Phase 0 gate |
| 7 | **Close the API loop** — checkout beyond a status flag | Medium | **Bach** | `feat/bach-records-signing` | **newly assigned**, Phase 3 |
| 8 | Negotiation / counter-offer protocol | Optional | — | — | **Ford's call, not a technical one.** Reverses decision-log item 2; the analysis says do not silently reverse it. Default: stays dropped. |
| 9 | **Electronics examples throughout**, retiring jacket material | Medium | **Nha** | `feat/nha-eval-data` | **newly assigned** |

## Open items (analysis §7 / handover §11)

| # | Item | Owner | State |
|---|---|---|---|
| 1 | Team name | Ford | **Done — BondLayer** |
| 2 | Merchant ↔ agent JSON contract — *"the single most important integration point"* | Nguyen + Bach | **Substantially discharged** by `src/bondlayer/types.py`. Ontology names aligned to handover §8. |
| 3 | Intent-accuracy evaluation set | Nha | Phase 0 gate — 30 requests, not the 100+ of proposal Phase 4; say so rather than overclaim |
| 4 | Synthetic electronics catalogue + merchant manifests | Nha | Phase 0 gate — **see manifest count below** |
| 5 | **Q&A rehearsal**, especially Q2 (Talon.One UIP) | **Nha to schedule** | **newly assigned**, Day 2 15:00–16:30 |

---

## The four newly assigned items, in detail

### Gap 4 — Dynamic bundling → Nguyen

Named twice in the problem statement: in the in-scope list, and inside
evaluation criterion 2 (*"effective use of APIs, **dynamic bundling**, and
LLM-to-LLM communication"*). Illustrative direction 1 ends on it — the merchant
*"pitches the ideal bundle based on that intent."*

`Bundle` is now in `types.py`. It takes Hieu's matched `Proposal`s as input and
composes them; **it does not re-do the matching.** That seam keeps Hieu's branch
from growing — his is already the heaviest — and puts bundling where the
response is actually shaped.

Phase 1 stretch: land the UCP head and the adapter first. A bundle of one is a
valid degenerate case, so this can ship partially.

### Gap 5 — Values claims → Bach, Hieu and Nha together

The analysis calls this *"the lowest-cost, highest-alignment extension
available"*, and the reason is that it reuses machinery that already exists.
The schema landed in `2043cac`; the remaining work is small and split three
ways:

- **Bach** — nothing new. Values claims are `BenefitRecord`s with
  `value_ceiling_aud = None`; they sign and verify through the existing path
  and contribute exactly zero to effective cost. Just don't special-case them.
- **Hieu** — resolve `ConstraintKind.VALUES` against them. *"From a brand that
  actually repairs things"* cites a signed `repairability` record.
- **Nha** — author them into the policy prose and put one **unsigned**
  greenwashing claim in the control merchant's data.
- **Minh** — render three distinct states: signed-and-priced (credited),
  signed-and-unpriced (cited, $0), unsigned (displayed, never cited). The last
  two both credit nothing, and the screen must still show that one is trusted
  evidence and the other is not.

That last detail is the demo moment: a verified durability claim beats
unverifiable greenwashing, using the same signing story already being told about
money. It costs almost nothing and answers illustrative direction 2 directly.

### Gap 7 — Close the API loop → Bach

Step 5 of the five-step walkthrough is *"closing the loop through a seamless,
API-driven transaction."* Currently a status flag. Pairs naturally with Bach's
Phase 3 work, since re-asserting records at checkout through UCP's loyalty
extension is already his — the same call just needs to settle rather than mark.

Scope honestly: **no real payment flow**, per the boundaries. A simulated
settlement that is idempotent and confirms explicitly is enough.

### Gap 9 — Electronics throughout → Nha

Decision-log item 3 switched the vertical footwear → consumer electronics, and
all new material must use electronics examples. `bach-demo` is pre-switch
outdoor-jacket material and is not submission code, so this is about the deck,
the README and anything spoken — not the old spike.

---

## Two corrections to the plan the analysis forced

### Semantic matching must actually be semantic

Analysis §3.1(b) found the spike matching by substring on title and brand —
*"precisely the thing criterion 1 says to go beyond."* Hieu's brief said
"resolve against catalogue attributes", which is not explicit enough to prevent
rebuilding the same thing. It now says **embeddings plus attribute filters**,
with exact model/GTIN as the MVP fallback per handover §8.

### The demo scenario has to change

Analysis §3.1(c): all three spike merchants sell the *same jacket* — barcode
`9312345678907` in all three exports. That scenario is an excellent vehicle for
verification and valuation and **a null vehicle for intent matching, because
there is nothing to match.**

Nha's catalogue must give the merchants **different, comparable-but-not-identical
products**, so that matching decides something before valuation does. Otherwise
we have rebuilt a demo that proves the criterion judged third and not the one
judged first.

Handover §8 assumes **three merchant profiles**; the current plan has two
(control + BondLayer). Three is better — it makes ranking a ranking rather than
a coin flip. Nha's call, since it is her data to author.

---

## What we are deliberately not covering

- **Gap 8, negotiation protocol.** High cost, and it reverses a logged decision.
  Ford decides; default is that it stays dropped.
- **The 100+ request evaluation set** promised in proposal §6 Phase 4. We ship
  30. Say "30, frozen before the feed existed" — a smaller honest number with a
  method beats a larger one we cannot stand behind in Q&A.
