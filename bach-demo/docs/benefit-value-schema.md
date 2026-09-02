# `org.bondlayer.benefit_value` — schema v0.1

A UCP vendor extension. Reference implementation: `src/bondlayer/schema.py`.

> **This document is the deliverable that survives.** The code in `demo/` is a
> throwaway spike that cannot be used in Round 2 (see `DECISIONS.md` D0). A
> written specification is explicitly permitted pre-hackathon work, and this is
> it.

---

## What it attaches to

```json
{
  "org.bondlayer.benefit_value": [
    {
      "version": "2026-08-30",
      "extends": "dev.ucp.shopping.catalog.lookup",
      "spec":   "https://bondlayer.example/spec/benefit_value",
      "schema": "https://bondlayer.example/schemas/benefit_value.json",
      "signing_public_key": "<base64 ed25519>",
      "signing_algorithm": "ed25519"
    }
  ]
}
```

It extends **catalog**, not checkout. UCP's own loyalty extension
(`dev.uip.shopping.loyalty`) attaches to checkout, so its data arrives after
the shopper has already picked a merchant. We attach the same class of data to
the capability the agent reads *while comparing*. See `ucp-findings.md`.

A merchant may declare the extension **without** publishing a key. Its records
then arrive unsigned, are displayed, and are never valued. That case has to be
representable — it is what an adversary looks like.

---

## The record

```json
{
  "id": "alpine-free-returns",
  "type": "free_returns",
  "title": "Free returns within 60 days, return postage paid",
  "facts": {
    "return_window_days": 60,
    "return_shipping_paid": true
  },
  "declared_bound_aud": null,
  "conditions": {
    "requires_membership": false,
    "requires_tier": null,
    "min_order_aud": 0,
    "excludes_sale_items": false
  },
  "issuer": "alpine",
  "issued_at": "2026-08-30T09:00:00Z",
  "expires_at": "2027-12-31T00:00:00Z",
  "signature": "<base64 ed25519 over the canonical form>"
}
```

| Field | Meaning |
|---|---|
| `type` | One of the seven ontology types below. |
| `title` | Human-readable. **Displayed, never valued.** |
| `facts` | Verifiable statements in explicit units. This is what gets valued. |
| `declared_bound_aud` | A **ceiling**, never a floor. See "The invariant". |
| `conditions` | Eligibility, published so it can be tested *before* checkout. |
| `expires_at` | Past expiry, the record fails verification entirely. |
| `signature` | Ed25519 over the canonical JSON, `signature` excluded. |

**Canonical form:** `json.dumps(record_without_signature, sort_keys=True,
separators=(",", ":"))`. Field order, whitespace and float formatting must not
be able to change the digest.

---

## The ontology (v0.1)

| Type | Facts it carries | How it is valued |
|---|---|---|
| `points_earn` | `points_per_aud`, `redemption_points_per_aud`, `points_expire_months` | Derived from the published **rate** and the item price, then × the customer's confidence. |
| `member_price` | `discount_pct`, `discount_aud` | Lower of the two, cross-checked against each other. |
| `free_returns` | `return_window_days`, `return_shipping_paid` | The customer's own fit-risk value; halved if the window is under 30 days. |
| `free_shipping` | `free_over_aud` | The customer's own delivery cost assumption, if the threshold is met. |
| `warranty_extension` | `warranty_months`, `statutory_baseline_months` | Years *beyond the statutory baseline* × the customer's per-year value. |
| `tier_progression` | `units_to_next_tier`, `next_tier` | The customer's own tier value × forecast confidence. **Provisional.** |
| `retention_offer` | `discount_aud` | Defined but produced by nothing — the retention engine is deferred (D6). |

### Naming rule

Every fact name states its unit: `_days`, `_months`, `_aud`, `_pct`, `_paid`.
This is not tidiness. The primary demo path is an LLM agent that has **never
seen this schema** and must interpret a record from field names alone (D8).
`return_window_days: 60` is self-describing; `rw: 60` is not.

---

## The invariant

> **A merchant can never improve its own position by inflating a number.**

Mechanically:

1. Value is derived from `facts` under the **customer's** policy — never from
   `declared_bound_aud`.
2. The declared bound is then applied as `min(policy_value, declared_bound)`.

So raising a bound raises a ceiling that is never reached; lowering it only
costs the merchant. Enforced by
`tests/test_invariants.py::test_inflating_a_declared_bound_cannot_help_the_merchant`.

**This test earned its keep immediately.** The first implementation derived
`points_earn` and `tier_progression` value *from* the declared bound, so
inflating bounds by 2× cut the adjusted cost from $155.26 to $150.48 — the
central claim was false and the test caught it. Both types now derive from
published rates or from customer parameters instead. If you change valuation
logic, run this test; the pitch depends on it being green.

### Companion rule for unsigned claims

Unverified claims are never valued, and are penalised in proportion to the
notional value of what they ask you to believe, capped by policy. Without the
penalty, a merchant spamming unverifiable claims lands in exactly the same
position as an honest merchant claiming nothing — lying would be free.

Together: **inflate a signed number and it is ignored; make a big unsigned
claim and it counts against you.**

---

## Degradation

With `org.bondlayer.benefit_value` absent from the negotiated capability set,
the catalog response contains no extension block and no member context — it is
byte-identical to plain UCP. This is required behaviour, and it is also what
makes the demo's "before" honest: the baseline is this same product with the
extension pruned by ordinary negotiation, not a strawman built to lose.

---

## Open issues for v0.2

1. **Key distribution.** Publishing the key in the capability declaration means
   fetching a party's key from the party you are verifying. It stops tampering
   and forgery-by-third-party; it does not stop a merchant lying under a valid
   key. Needs a registry, a CA, or key transparency.
2. **Catalog cacheability.** Member context makes catalog responses per-member.
   Mitigated by gating on identity linking, not solved.
3. **Condition expressiveness.** `Conditions` currently covers membership,
   tier, minimum order and sale exclusion. Real T&Cs have far more (category
   exclusions, date windows, channel restrictions). Expanding this is the main
   v0.2 work.
4. **No revocation.** A signed record is valid until it expires. There is no
   way to withdraw one early.
5. **Currency is assumed AUD throughout.** Should carry an explicit currency
   and follow UCP's minor-units integer convention rather than floats.
