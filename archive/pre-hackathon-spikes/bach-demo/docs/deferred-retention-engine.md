# Deferred: the Retention Decision Engine

**Status: cut from the build, kept for later experimentation (`DECISIONS.md` D6).**

This is the deck's "wow moment" — the merchant, on learning it is losing,
answering with a bounded, signed, expiring counter-offer. It was cut because
it has no counterpart in `round1/bondlayer-summary.md`, which is the plan.
Nothing here is implemented. The design is recorded so it can be picked up
without re-deriving it.

---

## Why it was cut

Features 1 and 2 are a **publishing** layer. The merchant declares things, the
agent verifies them, and the merchant never learns it was compared. That
property is worth more than it looks: it means BondLayer has no real-time
dependency, no per-comparison latency budget, and nothing to say about who was
shopping.

A retention engine changes what the product *is*. It makes BondLayer a
participant in the decision, which brings:

- **A second protocol flow** — request/response at decision time, with a
  latency budget the publishing path does not have.
- **A privacy story that must be defended** rather than simply being absent.
- **A merchant-side policy engine** with margin and budget floors, plus a
  dashboard for offers made, accepted and rejected.
- **A regulatory surface.** Offers keyed to a customer's disclosed status edge
  toward personalised pricing. Australia's Privacy Act automated-decision
  transparency obligations commence 10 December 2026.

It is roughly as much work as everything else combined, and it is the piece
most likely to draw a hostile question we do not otherwise have to answer.

---

## The design, if it comes back

### Flow

1. The agent has ranked, and the member's preferred merchant is losing.
2. The agent sends a retention request over a second vendor extension,
   `org.bondlayer.retention_request`, extending `dev.ucp.shopping.cart`.
3. The merchant's engine decides, within hard floors, whether to answer.
4. If it answers, it returns a `retention_offer` benefit record — signed,
   bounded, short-expiry, nonce'd — which is valued through exactly the same
   path as every other benefit. No special case.
5. The agent re-ranks. The offer wins or it does not.

### What the request may contain

```json
{
  "gap_bucket": "10-15%",
  "category": "outerwear",
  "tier": "Gold",
  "nonce": "..."
}
```

**And nothing else.** Not the competitor's name, not the competitor's price,
not the shopper's history, not the item they are comparing against. A bucket,
a category, a tier.

This is the load-bearing privacy decision. If the merchant learns the
competitor and the exact price, BondLayer becomes a price-surveillance channel
between competitors, which is both a competition-law problem and a reason no
merchant would join a network where rivals learn their prices.

### Floors (all deterministic, none learned)

| Floor | Purpose |
|---|---|
| Margin floor | Never offer below unit margin. |
| Periodic budget floor | Cap total discount issued per period. |
| Per-member frequency cap | Stop training members to always trigger an offer. |
| Category exclusions | Some lines never discount. |
| Expiry | Offers are short-lived and single-use, enforced by nonce. |

### Where learning could go — and where it must not

A contextual bandit choosing *within* the rule space (which of the permitted
offer sizes to make, given category and gap bucket) is defensible: the rules
bound the action space, the model only picks inside it.

A model must never set the floors, approve the offer, or compute the
valuation. Same principle as everywhere else in this design.

---

## Experiments worth running when it comes back

1. **Does the counter-offer actually flip a ranking**, or does the premium
   tolerance in the customer's policy exclude the merchant before the offer is
   even valued? (Plausible failure: the offer arrives too late to matter,
   because exclusion happens on *list* price.) This is the first thing to test,
   and if it fails the whole feature is decorative.
2. **Offer efficiency versus blanket discounting** — the pilot's actual
   question. Needs a holdout.
3. **Does gap-bucket disclosure leak more than it looks?** Repeated requests
   across a session may let a merchant triangulate a competitor's price even
   from buckets. Worth an adversarial look before this ships anywhere real.
4. **Member gaming.** If members learn that comparing triggers a discount,
   comparison behaviour itself becomes a discount lever.
