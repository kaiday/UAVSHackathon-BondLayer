# A2A findings (researched live, 01/09/2026)

Researched because the team decided to pursue agent-to-agent, and because
`docs/ucp-findings.md` — the 30/08 research — **never covered A2A at all**. It
looked only at REST catalog capabilities and the loyalty extension.

That gap matters, because the thing we were calling "the BondLayer agent" and
then talked ourselves out of turns out to be **a real, specified UCP concept**.

> **Correction to the 01/09 position.** I previously argued BondLayer should be
> a publishing layer and not an agent, on the grounds that "agent" was a label
> the code did not earn. That was right about the code and wrong about the
> standard. UCP has an official A2A extension whose stated purpose is *"a
> merchant's own autonomous agent negotiating directly with a shopper's agent
> using structured UCP data types."* The concept is not ours to invent or
> decline — it is in the spec, and the question is only what we build on it.

---

## Finding 1 — UCP already specifies merchant-side agents

Businesses **MAY** expose an A2A agent that supports UCP as an A2A Extension.
The merchant advertises it in its **A2A Agent Card**, not only in
`/.well-known/ucp`:

```json
{
  "extensions": [{
    "uri": "https://ucp.dev/2026-04-08/specification/reference",
    "description": "Business agent supporting UCP",
    "params": {
      "capabilities": {
        "dev.ucp.shopping.checkout": [{"version": "2026-04-08"}]
      }
    }
  }]
}
```

The shopping platform declares its side with a `UCP-Agent: profile=…` header —
the same header we already parse for capability negotiation, used for a second
purpose.

Discovery chains: `/.well-known/ucp` publishes a `services` entry whose A2A
endpoint points at the Agent Card, conventionally
`/.well-known/agent-card.json`.

**What this means for us:** our merchant service is already the right shape. It
needs an Agent Card and an A2A endpoint beside the REST one, not a rewrite.

---

## Finding 2 — The structural one, again: A2A binds to **checkout**, not catalog

| Capability | REST | MCP | A2A |
|---|:--:|:--:|:--:|
| `catalog` (search, lookup) | ✅ | ✅ | ❌ |
| `cart` | ✅ | ✅ | ❌ |
| `checkout` | ✅ | ✅ | **✅** |
| `order` | ✅ | ✅ | ❌ |

This is `ucp-findings.md` Finding 3 repeating itself in a new place. Loyalty
attaches to checkout, so its data arrives after the comparison is over — and now
**agent-to-agent conversation is also only bound to checkout.**

So a spec-conformant merchant agent can only start talking **once the shopping
agent is already at checkout with you.** If you lost the comparison, your agent
is never called. Out of the box, A2A gives you *retention and upsell*, not a way
to win.

**The load-bearing question this raises**, and we should find out rather than
assume: does a shopping agent open checkouts with *several* candidate merchants
to obtain true final prices — shipping, tax, member discounts — before choosing?
If yes, checkout-time A2A *is* the comparison moment and Finding 2 stops being a
problem. If no, checkout-time A2A can only defend a win we already have.

---

## Finding 3 — UCP anticipates negotiation but does not specify it

The A2A extension says platforms "must be capable of handling further
negotiation in the same session even after a task reaches a terminal state."

There is **no negotiation protocol** for terms or offers. No structure for "here
is what I could do for you", no bounded counter-offer, no way to say what a
concession is worth or when it expires. Negotiation is left as free-form
multi-turn messaging.

**This is the gap.** It is exactly the shape of the retention engine we designed
and deferred (`deferred-retention-engine.md`), and exactly the shape of
`benefit_value`. A vendor A2A extension that gives negotiation a *typed, signed,
bounded, expiring* structure is a real contribution to a real hole in a real
standard — not a hackathon invention.

---

## Finding 4 — Our signing is close to the standard, but not the standard

UCP and AP2 already solved key publication and signing, and we did it slightly
differently:

| | UCP / AP2 | BondLayer today |
|---|---|---|
| Key publication | `signing_keys` array of **JWKs** in `/.well-known/ucp` | `signing_public_key` inside the capability entry |
| Key reference | `kid` in the JWS header | none — one key per merchant |
| Signature format | **Detached JWS**, RFC 7515 Appendix F (`header..signature`) | custom envelope over our own field ordering |
| Canonicalisation | **JCS**, RFC 8785 | our own `model_dump` ordering |
| Algorithm | ES256 / ES384 / ES512 | Ed25519 |
| Coverage | payload excluding the `ap2` field | record excluding `signature` |

Our instinct (D9.8 — publish the key where the agent already looks) was right;
UCP standardised almost exactly that, and we should adopt their spelling.

Note `alg: EdDSA` is a valid JWS algorithm, so **we can keep Ed25519 and still
be JWS-shaped.** The expensive part is not the curve, it is JCS canonicalisation
and detached-JWS framing — and doing that makes our signatures verifiable by any
AP2-aware agent instead of only by our own library.

**This is the single highest-value conformance change available to us,** and it
is much cheaper than it looks.

---

## Finding 5 — the AP2 mandate pattern is a template we should copy

`dev.ucp.shopping.ap2_mandate` extends `dev.ucp.shopping.checkout` and carries a
merchant authorization as a detached JWS:

```json
{
  "id": "chk_abc123",
  "status": "ready_for_complete",
  "ap2": {
    "merchant_authorization": "eyJhbGciOiJFUzI1NiIsImtpZCI6Im1lcmNoYW50XzIwMjUifQ..<sig>"
  }
}
```

That is precisely the shape a signed BondLayer counter-offer should take:
extension of checkout, detached JWS, `kid` into the published key set, signature
covering the canonicalised payload minus its own field. **We should not invent a
third signing convention; we should copy this one.**

---

## What a BondLayer merchant agent would actually be

```
shopper
   │  natural language
   ▼
shopping agent  ─── REST/UCP catalog.search ──────►  merchant (compare)
   │                                                  signed benefit_value
   │  picks a candidate set
   ▼
A2A: message/send  ──────────────────────────────►  MERCHANT AGENT
     contextId, UCP-Agent: profile=…                 ├ answers questions about
   ◄────────  DataPart: a2a.ucp.checkout             │  its own published terms
   ◄────────  DataPart: org.bondlayer.offer          ├ computes eligibility
              (detached JWS, bounded, expiring)      └ may make ONE bounded,
                                                        signed counter-offer
```

Three things it can do that a REST endpoint cannot:

1. **Answer questions the catalogue cannot anticipate.** "Does the warranty
   cover the zip?" "Is the member price stackable with the sale?" Today those
   answers exist only in prose on a website. An agent can answer them *as the
   merchant*, and BondLayer can make the answer **signed**, which is the part
   nobody else offers.
2. **Compute eligibility per shopper.** A static catalogue must publish
   conditions and hope the agent evaluates them. An agent evaluates them itself
   and returns a determination it is willing to sign.
3. **Make a bounded counter-offer** — the deferred retention engine, with a real
   protocol home at last.

And the property we must not lose: **anything the merchant agent asserts is
signed, bounded and expiring**, valued through the same path as every other
benefit. Otherwise a merchant agent is just a chatbot that can say anything, and
the whole point of BondLayer is that a claim carries proof.

---

## What this costs, honestly

Everything in `deferred-retention-engine.md` still applies and none of it got
cheaper:

- A **second protocol flow** with a latency budget the publishing path does not
  have. A merchant agent that takes 30 s to answer loses the sale.
- A **privacy surface**: the merchant now learns it is being compared, and by
  whom. That was previously a property we could claim not to need.
- **Automated-decision transparency** under Australia's Privacy Act, commencing
  **10 December 2026** — inside any realistic deployment window.
- A **merchant-side policy engine** with margin and budget floors.

The mitigation that makes it defensible: the publishing layer stays the
foundation and works alone. The agent is an *optional capability* a merchant
switches on, exactly as UCP models it (`MAY expose an A2A agent`). A merchant
that never turns it on still gets everything the demo shows today.

---

## Sources

- A2A specification — https://a2a-protocol.org/latest/specification/
- UCP A2A extension — http://ucp.dev/2026-04-08/specification/checkout-a2a/
- UCP overview and discovery — http://ucp.dev/2026-04-08/specification/overview/
- UCP AP2 mandates extension — http://ucp.dev/2026-01-23/specification/ap2-mandates/
- AP2 specification — https://ap2-protocol.org/specification/
- Google Developers Blog, *Under the Hood: UCP* —
  https://developers.googleblog.com/under-the-hood-universal-commerce-protocol-ucp/
