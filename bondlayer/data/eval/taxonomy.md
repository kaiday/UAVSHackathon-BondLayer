# Intent taxonomy

What a multi-constraint shopping request actually contains, and how the four
clause kinds are told apart. This is the analysis the interpreter codes against
and the evaluation set is labelled with.

Written 12/09/2026, before the enriched feed exists.

---

## The four kinds

| Kind | Example clause | Answered by | Filter or rank |
|---|---|---|---|
| `HARD` | "under $1,500" · "at least 16GB RAM" | catalogue attribute | **filter** — violating it disqualifies the SKU |
| `SOFT` | "good enough for design work" · "light enough to carry daily" | catalogue attributes, interpreted | **rank** — better or worse, never disqualifying |
| `SERVICE` | "I can return it easily" · "covered if it breaks in year two" | **benefit record** — no catalogue attribute answers this | rank, and cite |
| `VALUES` | "a brand that actually repairs things" · "only from ethical brands" | **benefit record** — no catalogue attribute answers this | rank, and cite |

## Why the split is the product

The top two rows are what any catalogue can answer. Price, RAM and weight are
columns in a merchandising export; a competent keyword search plus a numeric
filter handles them, and every team at this hackathon will handle them.

**The bottom two rows are the argument.** No product export has a column for
"can I return this easily" or "does this brand repair things". Those facts live
in prose — returns policies, warranty terms, sustainability statements — which
is exactly the unstructured text an agent cannot read or weigh against price.

So a request containing a `SERVICE` or `VALUES` clause is one where a plain
catalogue **must** either guess or ignore the clause, and a merchant publishing
typed benefit records can answer it with a citation. That is the entire
difference the demo has to show.

A useful way to say it in the pitch: *rows one and two decide which products are
eligible; rows three and four decide which merchant wins.*

## How the two record-answered kinds differ

`SERVICE` and `VALUES` both resolve against benefit records, but they behave
differently in the arithmetic:

- **`SERVICE` records are priced.** A 60-day return window or 36 months of
  warranty carries a `value_ceiling_aud`, and the agent credits
  `min(ceiling, shopper's own policy value)` toward effective cost.
- **`VALUES` records are validated but never priced.** `value_ceiling_aud` is
  `None`. A signed `repairability` record can be cited as satisfying "a brand
  that actually repairs things" and contributes **exactly zero dollars**.

This is deliberate. Ethics do not convert to dollars, and pretending otherwise
would be the kind of fake precision that loses a Q&A. What signing buys here is
not value but *attributability*: a verified durability claim is a different
object from an unverifiable green adjective, even though both cost nothing.

## Three states a record can be in

Every citation carries one of these, and the distinction matters more than the
dollar figure:

| State | Cited? | Credited? |
|---|---|---|
| Signed, priced | yes | yes — up to the ceiling, capped by shopper policy |
| Signed, unpriced | yes | no — $0, by design |
| Unsigned | **no** | no |

Rows two and three both credit nothing. Only one of them is evidence.

## Decomposition rules

1. **One clause, one constraint.** "Under $1,500 and light" is two constraints,
   not one. The evaluation set is labelled this way.
2. **A clause keeps its kind even when unsatisfiable.** If no merchant answers
   "must be repairable", that is a `VALUES` constraint reported in
   `unsatisfied` — not a constraint that silently disappears.
3. **Budget is `HARD` unless hedged.** "Around $1,500" and "ideally under
   $1,500" are `SOFT`; "under $1,500" and "no more than $1,500" are `HARD`.
   The evaluation set contains both forms on purpose.
4. **Never hard-fail on ambiguity.** Per the workshop steer, contradictory or
   vague intent returns a best-understanding interpretation with the assumption
   stated — not an error.
5. **Use-case clauses are `SOFT`, not `HARD`.** "For video editing" implies
   specifications but names none. Resolve it to attributes and say which ones
   you inferred.

## Bundle intents

Some requests describe an outcome rather than a product — "everything I need to
start a podcast". These decompose the same way, but the gold answer is a **set**
of SKUs rather than one, and the bundle carries its own rationale for why the
items belong together.

Marked `"bundle": true` in the evaluation set.
