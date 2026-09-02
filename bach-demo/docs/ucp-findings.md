# UCP spec findings (verified live, 30/08/2026)

Researched because the pitch's load-bearing claim is *"an extension of UCP,
never a rival protocol"*, and that claim is worth exactly as much as the wire
format behind it.

**Three of these contradict the team deck. All three matter.**

---

## Finding 1 — The namespace in the deck is wrong

| | |
|---|---|
| Deck says | `dev.ucp.common.loyalty` |
| Actually is | `dev.uip.shopping.loyalty` |
| Version | `2026-01-23` |
| Schema ID | `https://uip.dev/schemas/ucp/shopping/loyalty.json` |
| Spec | `https://uip.dev/specification/ucp/loyalty.html` |

Note the domain: the loyalty extension is published on **uip.dev**, not
ucp.dev. `dev.ucp.*` is *"reserved exclusively for capabilities governed by the
UCP Tech Council"* — which is precisely why our own extension must be
`org.bondlayer.*`.

**Action: fix this before it reaches the seven pages.**

---

## Finding 2 — The gap is larger than the deck claims, in our favour

The deck says tier benefits are *"display strings only — e.g. 'Early access to
sales'"*. That understates it. In the actual spec, `Tier` is:

```json
{ "id": "tier_silver", "name": "Silver" }
```

That is the entire object. **There is no benefit field at all** — not even a
human-readable string. What the spec does model:

| Object | Fields |
|---|---|
| `Loyalty` | `memberships[]`, `programs[]`, `earnings[]` |
| `Membership` | `type` (`profile` \| `card`), `id` |
| `Program` | `id`, `name`, `membership` (JSONPath ref), `wallets[]` (min 1) |
| `Wallet` | `id`, `unit` (e.g. `points`, `USD`), `balances`, `earnings?`, `tier?` |
| `Earning` | `title`, `target` (`session` \| `items` \| `bundle`), `amount` (minor units), `wallet` (JSONPath), `active_from?`, `allocations[]?` |
| `Allocation` | `path`, `amount` |
| `TierInfo` | `current`, `next?`, `units_to_next?` |
| `AmountBreakdown` | `active`, `pending`, `total` — all integers, minor units |

Redemption mechanics are explicitly **not modelled** — only earning,
allocation and balance state.

So the accurate framing is not *"UCP transports strings we cannot value"*. It is:

> **UCP transports a balance and a tier name, and nothing at all about what
> that tier is actually worth.**

Stronger, and checkable by any judge who opens the spec.

---

## Finding 3 — The structural one: loyalty attaches to *checkout*

`dev.uip.shopping.loyalty` extends **`dev.ucp.shopping.checkout`**. The
`loyalty` object appears in the *checkout* response.

Comparison-time product and offer data lives in different capabilities
entirely:

- `dev.ucp.shopping.catalog.search`
- `dev.ucp.shopping.catalog.lookup`

Which means **UCP surfaces loyalty only once the shopper has already chosen the
merchant.** By the time the loyalty object exists, the comparison is over.

This is the spec-level confirmation of the whole thesis, and it is why
`org.bondlayer.benefit_value` extends the *catalog* capabilities (see
`DECISIONS.md` D3):

> The loyalty extension attaches to checkout. We attach the same class of data
> to catalog, because catalog is where the agent actually decides.

---

## Base capabilities (for reference)

| Capability | Purpose |
|---|---|
| `dev.ucp.shopping.catalog.search` | Search across a business catalog |
| `dev.ucp.shopping.catalog.lookup` | Retrieve a product by ID |
| `dev.ucp.shopping.cart` | Pre-checkout cart management |
| `dev.ucp.shopping.checkout` | Initiates and completes purchase sessions |
| `dev.ucp.shopping.order` | Order lifecycle events |
| `dev.ucp.shopping.permalink` | Shareable links to pre-populated carts/products |
| `dev.ucp.common.identity_linking` | OAuth-based account linking |
| `dev.ucp.common.location.search` / `.lookup` | Physical stores, pickup, amenities |

We implement `catalog.search`, `catalog.lookup` and `identity_linking`.
Cart, checkout, order and payments are stubbed — BondLayer never touches them.

---

## Capability negotiation (implemented in `ucp/capabilities.py`)

UCP uses a **server-selects** model. The business intersects its own declared
capabilities with those the platform advertises via the `UCP-Agent` header:

1. **Name intersection** — only capabilities both parties declare proceed.
2. **Version selection** — highest mutual version by date; if there is no
   common version, the capability is excluded.
3. **Extension pruning** — extensions are dropped if none of their parent
   capabilities survived the intersection; repeat until stable.

The business echoes the active capability set in every response, so the
platform always knows what is live.

This mechanism is *why the demo's before/after is honest* (D5): the "before"
run is simply an agent that does not declare `org.bondlayer.benefit_value`, so
negotiation prunes it and the merchant returns plain UCP. We are not switching
to a different code path to make the baseline lose — the protocol does it.

## Extension declaration format (verbatim from the spec)

```json
{
  "dev.ucp.shopping.fulfillment": [
    {
      "version": "draft",
      "extends": "dev.ucp.shopping.checkout",
      "spec": "https://ucp.dev/draft/specification/shopping/extensions/fulfillment",
      "schema": "https://ucp.dev/draft/schemas/shopping/fulfillment.json"
    }
  ]
}
```

Extensions use reverse-domain naming, declare a parent via `extends`, and
compose onto base schemas with JSON Schema `allOf`. Any vendor may define
capabilities under its own domain without UCP approval; they activate only when
both parties declare them.

Ours therefore declares:

```json
{
  "org.bondlayer.benefit_value": [
    {
      "version": "2026-08-30",
      "extends": "dev.ucp.shopping.catalog.lookup",
      "spec": "https://bondlayer.example/spec/benefit_value",
      "schema": "https://bondlayer.example/schemas/benefit_value.json"
    }
  ]
}
```

---

## Sources

- [UCP Loyalty Extension Specification (uip.dev)](https://uip.dev/specification/ucp/loyalty.html)
- [UCP Core Concepts (ucp.dev)](https://ucp.dev/documentation/core-concepts/)
- [UCP specification overview (ucp.dev)](http://ucp.dev/2026-04-08/specification/overview/)
- [Universal-Commerce-Protocol/ucp on GitHub](https://github.com/universal-commerce-protocol/ucp)
- [Building the Universal Commerce Protocol — Shopify Engineering](https://shopify.engineering/ucp)
