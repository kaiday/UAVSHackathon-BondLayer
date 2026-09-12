# `feat/bach-records-signing` — Thanh Bach Ly (Software Engineer)

**Phase 2, then Phase 3.** Verification and valuation sit *behind* the intent
layer — they make the interpreter's citations trustworthy. Components 3, 4 and 7
of the Round 1 §5.2 table.

You are not blocked by the Phase 0 gate. Canonical serialisation, signing and
the invariant tests need no catalogue. **Write the three invariant tests first**
— they are what the pitch stands on.

## Write these three tests before anything else

`tests/test_invariants.py`:

1. **A tampered record fails verification.** Mutate one byte of a signed
   record's payload; `verify()` returns False.
2. **An unsigned record credits zero.** It is displayed, never valued.
3. **Inflating `value_ceiling_aud` to $9,999 does not change the ranking.**
   Because credited value is `min(merchant_ceiling, shopper_policy_value)`, a
   merchant cannot buy rank by declaring a bigger number.

Test 3 is the one that survives the Q&A. The obvious attack on our design is
"what stops a merchant claiming their warranty is worth ten thousand dollars" —
and the answer should be a test that runs on screen, not a paragraph.

## Scope

### Canonical JSON + object signing — `src/bondlayer/records/`

Deterministic byte output for a `BenefitRecord`. A signature over
non-canonical JSON is worthless, so this comes before the crypto.

**ES256** detached signature per record. The proposal says ES256 with
`signing_keys[]` in the UCP profile — **do not drift to Ed25519.** Hand the
public key to Nguyen to publish; do not publish it yourself.

Object-level, not transport-level. That distinction is the §2.4 "Verification"
argument: UCP's own RFC 9421 message signatures are ephemeral and authenticate a
response in flight, producing no durable artefact. Ours survives the response
that carried it, so an agent can cache it, re-verify it later, and cite it when
justifying a ranking. If you are asked at the Gala why we did not just use UCP
message signing, that is the answer.

**Plant one unsigned "$50 agent bonus" record in the demo data** and let it
visibly earn nothing. That single moment is the strongest thing in the pitch —
it turns an abstract claim about trust into something a judge watches happen.

### Valuation library — `src/bondlayer/valuation/`

`effective_cost(sku, records, policy) -> EffectiveCost`.

`credited = min(merchant_ceiling, shopper_policy_value)`, zero if unverified.

**No model call anywhere in this file.** §4.2 of the proposal commits to this:
effective cost is deterministic arithmetic over verified records, reproducible
and auditable rather than a model's opinion. Keep it that way, and keep the
working — return the `CreditedBenefit` breakdown, not just the total. Minh's
console log renders it and the agent cites it.

The proposal offers this library open source so the arithmetic is independently
auditable rather than merchant-controlled. Write it as if someone hostile will
read it, because that is the point of shipping it.

### Loyalty (Phase 3)

Member recognition through linked identity, enrolment behind an explicit consent
gate, and records re-asserted at checkout through UCP's loyalty extension — so
the number the agent ranked on is the number the shopper pays (§4.1, scope
discipline). Values at discovery are **indicative, not binding**; say so, since
UCP requires eligibility enforcement at checkout against binding transaction
data.

## Interfaces

You own `Signer` and `ValuationLibrary`. Both are already declared in
`types.py`, so Nguyen and Minh wire to the protocol at 10:20 and get your real
implementation when it lands.

## Done when

The three invariants pass, the planted unsigned record earns zero on screen, and
`EffectiveCost` comes back with its arithmetic exposed.

---

## Added from the Round 2 alignment analysis

### Close the API loop (gap 7) — newly yours, Phase 3

Step 5 of the problem statement's five-step walkthrough is *"closing the loop
through a seamless, API-driven transaction."* Today it is a status flag.

It pairs with your Phase 3 work: re-asserting records at checkout through UCP's
loyalty extension is already yours, and the same call just needs to settle
rather than mark. Make it **idempotent** and make it **confirm explicitly** —
create and confirm are separate steps, and replaying a confirmation must not
double-credit a benefit.

Scope honestly: **no real payment flow.** A simulated settlement is enough and
is inside the stated boundaries. Do not let it grow.

### Values claims (gap 5) — nothing new for you, and that is the point

`BenefitType` now carries `sustainability`, `ethical_sourcing`, `durability`,
`repairability`, and `value_ceiling_aud` is optional. A values claim is just a
`BenefitRecord` with `value_ceiling_aud = None`.

**Do not special-case them.** They sign and verify through your existing path,
and they contribute exactly zero to effective cost because there is no ceiling
to take a minimum against. The analysis rates this the best effort-to-score gap
precisely because your machinery already covers it.

One consequence worth a test: a *signed* values claim and an *unsigned* one both
contribute zero dollars — but only the signed one may be cited. Verification and
valuation are separate questions, and your invariants should say so.

### Open: ES256 or Ed25519

The submitted docx says **ES256** with `signing_keys[]`; the handover's canonical
text and locked stack say **Ed25519 / PyNaCl**. These disagree and it is not
settled. **Ask Ford before you write the signing code** — it is the one open
question that blocks you.
