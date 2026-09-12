# `feat/nguyen-ucp-head` — Hoang Manh Nguyen (Software Engineer)

**Phase 1.** The catalogue an agent can actually reach, and the protocol surface
it reaches it through. Components 1 and 6 of the Round 1 §5.2 table.

The pitch line this branch has to make true: *an agent shops the protocol, not
the website, so a retailer outside it isn't outranked — it's invisible.*

## Scope

### Catalogue adapter — `src/bondlayer/adapters/catalog.py`

Nha's `data/catalog/electronics.csv` → `list[Sku]`.

She plants attribute noise, inconsistent units, missing fields and
near-duplicate titles on purpose. Normalising that mess **is** the deliverable,
not a chore before it: "adoption starts from files the retailer already has" is
the §5.1 adoption story, and a demo that only works on a hand-cleaned CSV does
not support it.

Keep a count of what you had to fix. "The adapter repaired 31 malformed
attributes across 74 SKUs" is a slide.

Implements the `CatalogAdapter` protocol.

### UCP head — `src/bondlayer/ucp/`

**`/.well-known/ucp` profile.** Capabilities list plus `signing_keys[]`. Bach
gives you the key material — publish it, don't generate it. This is the key
discovery mechanism the whole verification story depends on, so it has to be
reachable and correct.

**`catalog.search` and `catalog.lookup`**, returning conformant UCP catalogue
objects. `catalog.lookup` is the call that carries the benefit extension,
because it is the call an agent already makes while comparing merchants.

**Capability negotiation.** The agent declares what it supports; you serve the
**intersection**. If it does not declare the benefit extension it gets plain
UCP, through **no special-case branch** — the graceful-degradation claim in §5.3
says "ordinary capability negotiation serves its plain UCP with no special-case
code path", and someone will ask you to prove it. Make it structurally true, not
conditionally true.

**Control merchant.** The same server, same code path, enrichment switched off.
Assumption A2 requires both merchants be served identically so that the only
variable is the data exposed. If the control is a different implementation, the
comparison proves nothing and the result is worthless. This is the single most
important correctness property on your branch.

## Interfaces

You **own** `CatalogAdapter`.
You **consume** `Proposal` from Hieu and `SignedRecord` from Bach — both behind
protocols in `types.py`, so wire to stubs at 10:20 and swap in real
implementations as they land.

## Working against the gate

The catalogue arrives ~12:00. Until then build the UCP head against a
ten-row fixture CSV of your own making. Profile, negotiation and routing need no
real data, and they are the parts that must already work when the catalogue
shows up.

## Done when

- An agent **with** the extension and an agent **without** it both get a valid
  response from the same code path
- The control merchant is served by the same server with enrichment off
- `/.well-known/ucp` resolves and its `signing_keys[]` verifies one of Bach's
  records end to end
- It runs from seeded state with no network call — venue wifi is shared by
  twenty teams

---

## Added from the Round 2 alignment analysis

### Dynamic bundling (gap 4) — newly yours

Named twice in the problem statement: in the in-scope list, and inside
evaluation criterion 2 (*"effective use of APIs, **dynamic bundling**, and
LLM-to-LLM communication"*). Illustrative direction 1 ends on it — an agent asks
for "beginner-friendly podcasting gear" and the merchant *"pitches the ideal
bundle based on that intent."* It had no owner until now.

`Bundle` is in `types.py`. It takes Hieu's matched `Proposal`s and composes
them — **it does not re-do the matching.** That seam matters: his branch is
already the heaviest, and bundling belongs where the response is shaped.

`rationale` says why these items belong *together*. Why each one matched is
already in its `ResolvedConstraint` notes; don't restate it.

**Phase 1 stretch, not Phase 1 core.** Land the UCP head, the profile and the
adapter first. A bundle of one is a valid degenerate case, so this can ship
partially and still count.

### Merchant manifests

Handover §8 assumes **three** merchant profiles served from JSON manifests; the
current plan has two (control + BondLayer). Three makes ranking a ranking rather
than a coin flip. Nha authors the data — agree the count with her before you
wire the server, so you build the right number of profiles once.
