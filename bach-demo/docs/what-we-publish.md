# What we publish to UCP, and why it moves ranking

*Written 02/09/2026, from a walkthrough of the demo code. This is an
explainer, not a spec — the normative documents are
[`benefit-value-schema.md`](benefit-value-schema.md) and
[`ucp-findings.md`](ucp-findings.md). Every claim below names the file it
came from, so it can be re-derived rather than trusted.*

Two questions came up that the README answers only in pieces:

1. What information do we actually hand the agent, and why does each part of
   it change a ranking?
2. How does the merchant know the shopper's membership tier?

---

## 1. The two layers on the wire

### Layer 1 — plain UCP (every merchant already has this)

`catalog.search` / `catalog.lookup` return what any UCP merchant returns: id,
title, price, availability, specs. That is `plain_ucp_declaration()`
(`src/bondlayer/ucp/capabilities.py:59`) — what Peak publishes, and what the
"before" run sees.

On these facts alone **Alpine deserves to lose**: $199 against Peak's $179.
Keeping that true is what makes the before/after honest (D5).

### Layer 2 — `org.bondlayer.benefit_value`

Declared as `extends: catalog.lookup` (`capabilities.py:43`), so it rides on a
lookup the agent already makes, and ordinary server-selects negotiation prunes
it when the agent does not ask for it. No special "make the baseline lose"
code path exists.

Each record (`src/bondlayer/schema.py:97`) carries:

| field | purpose |
|---|---|
| `type` | one of 7 ontology values — `member_price`, `free_returns`, `free_shipping`, `warranty_extension`, `points_earn`, `tier_progression`, `retention_offer` |
| `title` | human string — **displayed, never valued** |
| `facts` | verifiable statements in explicit units: `return_window_days: 60`, `return_label_fee_waived_aud: 9.95`, `standard_delivery_fee_aud: 12.95`, `points_per_aud: 2` |
| `declared_bound_aud` | a **ceiling** on what the benefit may be valued at |
| `conditions` | `requires_membership`, `requires_tier`, `min_order_aud`, `excludes_sale_items` — published *before* checkout |
| `issuer` / `issued_at` / `expires_at` | provenance and freshness |
| `signature` | Ed25519 over the canonical JSON. Absent ⇒ never valued |

Plus `dev.ucp.common.identity_linking`, which supplies the member context —
see part 2.

### Why each choice moves the ranking

**Facts in explicit units, not marketing copy.** Alpine's six benefits turn
$199 list into roughly $155–189 effective cost. That delta *is* the ranking
change. An agent can subtract a $9.95 waived return label and a $12.95
delivery fee; it cannot subtract "great returns policy".

**Money attached to every benefit.** `demo_data.py:90` records this the hard
way: in the first real recorded run three benefits published no dollar figure,
the model read them as feature bullets, and it ranked Peak in *both*
conditions. Self-describing field names (D8) exist for the same reason — an
agent that has never seen this schema must parse it from names and units
alone, so no codes and no enums-as-integers.

**Conditions published up front.** UCP's own loyalty extension evaluates
conditions merchant-side at checkout, by which point the comparison is over
(`ucp-findings.md`, finding 3). Publishing eligibility at lookup time is what
makes a benefit creditable *during* ranking instead of a surprise at the till.

**The declared bound is a ceiling, never a floor.** Value is derived from the
facts under the *customer's* policy, then clamped. Inflating the bound raises
a ceiling that is never reached — enforced by `tests/test_invariants.py`, and
that test caught the first implementation getting it backwards (README,
property 1).

**Signature or nothing.** Ridgeway declares the extension but publishes no key
(`demo_data.py:140`), so its "2 year warranty" arrives unsigned: displayed,
valued at zero, and *penalised* in proportion to the size of the claim. Under
a plain value-at-zero rule a merchant spamming unverifiable claims would land
exactly where an honest merchant claiming nothing lands — lying would be free.

### The claim, in its narrow and defensible form

> Publishing signed, priced, structured benefit data does not make a
> price-ranking agent change its mind. It makes an agent that is *already*
> reasoning about total cost able to credit you for what you actually offer —
> and it denies that credit to competitors who publish nothing or publish it
> unsigned.

This is why the headline metric is the **information gap** (`visibility.py`:
9 → 96 fields visible, 0 → 6 benefits legible, $0 → $41.74 creditable), not
the recommendation flip. The flip is the payoff; the gap is the proof. Do not
say "any LLM agent flips" (D9.14).

---

## 2. How the tier is known

**BondLayer does not work it out. The merchant already knows, and the agent
supplies the handle.** Tier is never inferred, guessed or profiled.

1. **The agent declares `dev.ucp.common.identity_linking`** in its
   `UCP-Agent` header. Without it, none of the following happens.
2. **The agent passes `member_id` as a query param** on `catalog.search` /
   `catalog.lookup` (`agent/shopping_agent.py:142`), gated on both a
   `member_id` being present *and* the extension having been negotiated.
3. **The merchant looks it up in its own loyalty database.**
   `MerchantService` holds a `members` map (`ucp/server.py:42`); the demo
   seeds one Gold member, `member-4417` (`demo_data.py:37`, `:204`). In
   production this is the merchant's existing CRM/loyalty table — data the
   merchant has always had and has never published in a form an agent could
   read.
4. **The response carries a `MemberContext` block** (`schema.py:151`) beside
   the benefits: `tier`, `program_name`, `points_active`, `points_pending`,
   `units_to_next_tier`, `next_tier`.
5. **The agent tests the conditions itself.** `Conditions.unmet_by()`
   (`schema.py:80`) compares each benefit's `requires_tier` against the
   returned `member.tier` and returns readable reasons when it does not apply
   — *"requires Gold tier; member is Silver"*. That is why Alpine's 5% member
   price is credited as $9.95 rather than silently dropped or optimistically
   assumed.

### Three points worth stating before a judge finds them

**`/ucp/identity/link` is a stand-in for OAuth.** `ucp/server.py:137` takes a
`member_id` and returns the linked state, 404 if not a member. The real flow
is a consented OAuth handshake between shopper and merchant; the demo skips
the ceremony because the linked state is what matters. The trust model is the
same as any account link a shopper already performs today.

**With no linked member the catalog response is byte-identical to plain UCP**
(`schema.py:157`). No member, no `MemberContext`, no member-gated benefits
valued. The shopper opts in; the merchant learns nothing about a shopper who
does not.

**The timing is the entire point.** UCP puts member state in the *checkout*
response (`dev.uip.shopping.loyalty`) — after the comparison has been decided.
BondLayer surfaces it at catalog time, during comparison, because that is the
only place it can change an outcome (D3).

**Known cost:** per-member responses genuinely damage catalog cacheability.
Recorded as known weakness 4 in the README, not hidden.
