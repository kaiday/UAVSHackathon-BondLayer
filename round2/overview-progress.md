# Overview progress — Day 1

*Revised 12/09 13:05 AEST. Supersedes the 11:10 version. Every status claim re-checked
against `origin/*` rather than restated.*

> ## Two things at once
>
> **Code is landing.** Nguyen shipped 1,443 lines at 12:47–12:57; Hieu shipped the intent
> parser at 12:59. `round2/dev` moved to `4e20af6`. That is the day turning around.
>
> **And the architecture changed.** `round2/system-architecture.md` re-cuts the product
> into **two applications and three owners**. It does not match the five-owner split in
> `WORKPLAN.md` that everyone is currently working from, and it leaves the top-weighted
> judged criterion without an explicit owner. **§3 lists four questions that need answers
> before 14:30.**
>
> **Bach and Minh have pushed no code** and Bach now owns the harder of the two apps.

---

## 1. Where the repo actually stands

| Branch | Ahead | What has landed | Last push |
|---|---|---|---|
| `feat/nguyen-ucp-head` | 9 | **1,443 lines.** `adapters/catalog.py` (457) · `ucp/profile.py` · `ucp/capabilities.py` · `ucp/server.py` · `ucp/onboard.py` · `tests/test_catalog.py` (144) · `tests/test_ucp.py` (178) | **12:57** |
| `feat/hieu-interpreter` | 6 | **346 lines.** `interpreter/parser.py` (169) · `interpreter/resolver.py` (stub) · `tests/test_interpreter.py`. Parses R01 | **12:59** |
| `feat/nha-eval-data` | 1 | `docs/stage1-agent-ready-catalog.md` — **unmerged, see §4.1** | 12:32 |
| `feat/bach-records-signing` | 5 | scope note only — **no code** | 10:52 |
| `feat/minh-console` | 5 | scope note only — **no code** | 10:52 |

`round2/dev` head: `4e20af6` (12:47) *"Package layout: bondlayer importable, pytest finds src"*.

**On `round2/dev`:** `types.py` (232 lines — 13 frozen dataclasses/enums, **5** protocols) ·
30 frozen eval requests · `electronics.csv` — **148 SKUs · 62 model keys · 53 shared across
merchants · 10 missing GTINs** · three policy docs + `manifests.json`
(`voltway` bondlayer · `citycircuit` control · `northgear` competitor).

### Integration hazard, right now

**Hieu's branch is behind `round2/dev`.** His last merge was 10:52; the package-layout
commit landed at 12:47. His branch is missing `pyproject.toml`, so *"pytest finds src"* is
not true on his checkout. Nguyen merged it at 12:47 and is clean. **Hieu: merge
`round2/dev` before your next push**, or the first integration attempt fails on imports
rather than on logic.

---

## 2. The architecture we are building

From `round2/system-architecture.md`. Two applications over three data models.

### Data models

`Catalogs` (product detail) · `Policy` (text) · `Promotions` (**undefined in the doc — see
§3.4**).

### Dashboard — the merchant app

The app the merchant uses most. Manages catalog, policy and promotions.

- **Onboarding by upload** — catalog as CSV, policy and promotions as txt
- **Intelligent suggestions** on catalog and policy
- **Analytics page — demo only, no data populated.** Label it as such *on the screen*, not
  just in the script. An unlabelled empty analytics page reads to a judge as a broken
  feature rather than a deliberate boundary

### Demo Chat App — the integration proof

> *"The onboarding step can be demoed easily via dashboard GUI. However, UCP integration is
> harder to demo. Thus we need this demo chat app."*

- A **mock shopping agent** whose system prompt is **neutral** and mirrors a real agent's
  decision strategy — it must have no knowledge of us
- A **BondLayer on/off switch**, showing the layer's effect on the merchant's ranking
- **Detail logs as evidence:** UCP integration, loyalty layer, policies applied, user
  identity fetched via UCP

### Assignment

| Owner | Scope |
|---|---|
| **Manh** | Dashboard |
| **Hieu** | RAG for dashboard intelligence, and DAO |
| **Bach** | Demo Chat App — including UCP integration and the loyalty layer |

---

## 3. Four questions the new split raises — answer before 14:30

These are not objections. The two-app cut is clearer than the five-surface one and it
matches what Nguyen has already built. But it changes ownership under people mid-flight,
and four things are genuinely unresolved.

### 3.1 Who owns intent matching — the #1 judged criterion?

FPT weights **intention accuracy and semantic matching first**, ahead of architecture and
conversion. In the new split it is named nowhere: Hieu has "RAG for dashboard intelligence
and DAO", which is the *merchant-side* suggestion engine, not shopper-intent decoding.

Meanwhile Hieu has spent the morning building exactly that — `interpreter/parser.py`,
pushed 12:59. **Either the architecture doc is silent on work that is already underway, or
Hieu is off-plan.** Those need different fixes, and the whole pitch rests on the answer.

### 3.2 Bach now owns the heavier app, from zero

He has no code at 13:05, and the new split gives him the Demo Chat App **plus** UCP
integration **plus** the loyalty layer. Nguyen has already shipped a UCP head — profile,
capabilities, server, negotiation, control parity.

**Recommendation: Bach consumes Nguyen's UCP head, he does not rebuild it.** Otherwise two
people implement the same protocol surface on Day 1 and neither finishes. His own branch's
signing and valuation work — the trust invariants — is still his and still unstarted.

### 3.3 Nha and Minh have no assignment

Nha's Phase 0 landed and she owns the 25-point market-strategy work, the Problem Setter
window and the Q&A rehearsal — none of which appear in a doc about applications, and all of
which still need doing. Minh's three surfaces are absorbed into the two apps, which is
sensible, but **the person is not.** A UX owner with no named surface on Day 1 is wasted
capacity, and the dashboard is a UX-heavy app with 20 points attached.

### 3.4 `Promotions` is declared and undefined

It is listed as a data model with no description, and it does not exist in `types.py`,
which models value as `BenefitRecord` with a `BenefitType` ontology. Either promotions
*are* `BenefitRecord`s and the name should go, or they are a new type and someone must
define the shape — **on `round2/dev`, channel first**, per the rule below.

### Branch names now lie

`feat/nguyen-ucp-head` is becoming the dashboard. `feat/bach-records-signing` is becoming
the chat app. `feat/hieu-interpreter` is becoming RAG + DAO. Renaming branches at 13:00
costs more than it saves — **leave them, and put the mapping in the README**, or a `git
checkout` under time pressure sends someone to the wrong place.

---

## 4. Corrections that still stand

### 4.1 Nha's Stage 1 spec is unmerged, and it resolves the signing question

`bondlayer/docs/stage1-agent-ready-catalog.md`, pushed 12:32, still only on
`feat/nha-eval-data`. **Merge it.** It is the sharpest document in the repo and it settles
what this morning's version called the one hard blocker:

> **ES256 (P-256/SHA-256) is mandatory.** All implementations MUST verify it. Do not reach
> for Ed25519 — the Round 1 proposal said Ed25519, the spec says ES256, **and the spec wins.**

Verified against `ucp.dev/2026-04-08/specification/signatures/`. **Bach is unblocked — this
is not waiting on Ford.** Two riders:

- Keys publish in `/.well-known/ucp` under `signing_keys[]` in **JWK format** (RFC 7517):
  `kid`, `kty: "EC"`, curve, `x`, `y`. `kid` resolves there; no match → `key_not_found`.
- **Before Bach reads the wrong source:** a widely-cited vendor blog claims
  `/.well-known/jwks.json` is the canonical trust store and `signing_keys[]` is merely
  informational. **ucp.dev does not say that.** Build against ucp.dev.

Pitch it as an **adaptation** — we read the spec and changed — not as a correction. That
scores under Adaptation (10).

### 4.2 The unsigned greenwashing claim is in **northgear**, not citycircuit

`GAPS.md` gap 5 and `branches/minh.md` both say *"the control merchant's data."* The landed
data and the Stage 1 spec both put it in `northgear.planted_unsigned` — *"Australia's most
sustainable electronics retailer"* — and that is right:

- `citycircuit.expect_records` is `[]`, with `_why_empty`: the control publishes a plain
  feed, *"That is the status quo, not a strawman."* A control that publishes an unsigned
  claim has stopped being a control.
- northgear's entry says why: *"R12 must not be won by this."* R12 is *"I want the most
  sustainable phone you sell."*

**Fix the wording in `GAPS.md` and `branches/minh.md`. Do not move the record.**

### 4.3 `types.py` has pending additions, and nobody may make them on a branch

`WORKPLAN.md`: *"a change goes to the channel first, then straight onto `round2/dev` as its
own commit, then everyone rebases."* Batch these into **one** commit:

| # | Addition | For | Why |
|---|---|---|---|
| 1 | `Sku`: `gtin`, `model_key`, `variant_parent`, `availability` | Manh, Hieu | Stage 1 §9. The CSV already has these columns; burying identity in `attributes` breaks matching and the readiness score. `None` is a legitimate, scored state |
| 2 | `ReadinessReport` | Manh | Stage 1 §4 — the dashboard's suggestion surface needs a shape |
| 3 | `Promotions`, or a ruling that it is `BenefitRecord` | Manh, Bach | §3.4 |
| 4 | **`Bundler` protocol** | Manh | `Bundle` exists as a dataclass; the seam that produces one does not |

---

## 5. Technical task breakdown

Re-cut against the two-application architecture. Each task names its dependency and a
testable *done when*. ✅ = already landed.

Legend: 🔴 critical path · 🟡 needed for the demo · 🟢 stretch, cut at 14:30

### Dashboard — Manh · `feat/nguyen-ucp-head`

| ID | Task | Dep | Done when |
|---|---|---|---|
| D1 ✅ | `adapters/catalog.py` — CSV → `Sku`, normalising the planted noise | — | **Landed 12:52.** Keep the repair count: *"repaired N malformed attributes across 148 SKUs"* is a slide, and the remediation log is the literal answer to FPT's question about what friction a machine meets on a human feed |
| D2 ✅ | UCP head — profile, capabilities, server, negotiation, **control parity** | — | **Landed 12:57.** Control parity is the single most important correctness property in the repo: the control is the same server with enrichment off. If it were a different implementation the comparison proves nothing |
| D3 ✅ | `ucp/onboard.py` — onboarding endpoints | — | **Landed 12:53.** This is the JSON the dashboard GUI renders |
| D4 🔴 | Dashboard GUI: upload catalog CSV, policy txt, promotions txt | D3 | A merchant export with deliberate noise ingests with **zero manual edits**, and every repair shows in the log |
| D5 🔴 | Render the remediation log — every repair with before, after, and the rule that fired | D1, D4 | Per the Problem Setter's note, **the log matters more than the bars looking good** |
| D6 🟡 | Catalog / policy / promotions management views | D4, §3.4 | A merchant can see and correct what was ingested |
| D7 🟡 | Intelligent-suggestion surface — renders Hieu's output | H2 | Names the **worst offenders by SKU id**. A list of twelve broken SKUs is actionable; "attribute completeness 78%" is not |
| D8 🟡 | Readiness score — five dimensions **reported separately, never averaged** | §4.3 #2 | Identity · attribute completeness · semantic density · policy coverage · verifiability. One blended score hides the specific fixable problem |
| D9 🟡 | Analytics page — **visibly labelled demo-only, no data** | D4 | A judge reads it as a deliberate boundary, not a broken feature |
| D10 🟢 | Dynamic bundling (gap 4) — compose `Proposal`s into a `Bundle` | §4.3 #4 | Named twice in the problem statement. `rationale` says why items belong *together*. **A bundle of one is a valid degenerate case**, so it ships partially and still counts |

### Dashboard intelligence — Hieu · `feat/hieu-interpreter`

| ID | Task | Dep | Done when |
|---|---|---|---|
| H0 🔴 | **Merge `round2/dev` before your next push** | — | You are missing `pyproject.toml` from 12:47; pytest will not find `src` on your checkout (§1) |
| H1 ✅ | `interpreter/parser.py` — intent parse, R01 | — | **Landed 12:59.** Extend to all 30 eval requests |
| H2 🔴 | RAG over policy + catalog → improvement suggestions | D3 | Suggestions quote the text they came from. **A suggestion with no quotable source is not shown** |
| H3 🔴 | DAO layer for catalogs, policy, promotions | §3.4 | One place owns persistence; the two apps do not each invent it |
| H4 🔴 | **Settle §3.1**, then either finish the interpreter or hand it over | §3.1 | Whoever owns it, one person does, and they know by 14:30 |
| H5 🟡 | Policy → draft `BenefitRecord`s, **every draft quoting `source_span`**, nothing published without a human approval click | H2 | **Demo the approval gate as a feature.** A draft with no quotable span is rejected, not published |
| H6 🟡 | **Compare the quote loosely, the fact strictly** | H5 | Normalise markdown, whitespace and currency before comparing spans. *The spike rejected all ten drafts because the document wrote `**$12.95**` and the model quoted `$12.95`.* The check is for fabrication, not formatting — do not re-ship that bug |
| H7 🟡 | Matching is **embeddings + attribute filters, not substring** (gap 2, Critical) | H4 | The 53 shared `model_key`s are the test case. Exact model/GTIN is the **declared MVP fallback**, not the plan |
| H8 🟡 | Every resolved constraint carries a cited `evidence_record_id` **or** `evidence_attribute` **plus** a readable note; `unsatisfied` populated honestly | H4 | **FPT asked for justification prose, not a SKU list.** The eval set contains requests engineered to catch silent drops |

### Demo Chat App — Bach · `feat/bach-records-signing`

**Nothing has landed. This is the critical path now.**

| ID | Task | Dep | Done when |
|---|---|---|---|
| B1 🔴 | **`tests/test_invariants.py` before any other code.** (1) tampered record fails verify; (2) unsigned record credits zero; (3) inflating `value_ceiling_aud` to $9,999 does not change ranking | — | Red, then green. **Test 3 is the one that survives Q&A** — the obvious attack is *"what stops a merchant claiming a $10,000 warranty"*, and the answer should be a test running on screen, not a paragraph |
| B2 🔴 | Canonical JSON serialiser + round-trip test — **before the crypto** | — | Sorted keys, no insignificant whitespace, integers for minor units, UTF-8, no trailing newline. A signature over non-canonical JSON is worthless |
| B3 🔴 | **ES256** detached per-record signature — settled, §4.1 | B2 | **Object-level, not RFC 9421 transport-level.** Asked at the Gala why not UCP message signing: theirs is ephemeral and authenticates a response in flight; ours survives the response, so an agent can cache it, re-verify it later and cite it. Hand the key to Manh as JWK — **do not publish it yourself** |
| B4 🔴 | **Consume Manh's UCP head — do not rebuild it** (§3.2) | D2 | The chat app talks to the running server. Two protocol implementations on Day 1 means neither finishes |
| B5 🔴 | Mock shopping agent with a **neutral** system prompt | B4 | It mirrors a real agent's decision strategy and **has no knowledge of our system.** That neutrality is what makes the before/after admissible evidence |
| B6 🔴 | **The BondLayer on/off switch** | B4, D2 | Same query, same code path, visibly different ranking. **The "off" run is an agent that simply does not declare `org.bondlayer.benefit_value`, so negotiation prunes it — we never switch code paths to make the baseline lose.** This is the moment the pitch turns |
| B7 🟡 | Detail logs: UCP negotiation · loyalty layer · policies applied · identity fetched via UCP | B4 | Reads as a chain of thought, not a log dump. **This is the surface FPT weights highest** — *visual polish of human-facing dashboards is lower priority than the logic of the machine-to-machine interaction* |
| B8 🟡 | `valuation/`: `effective_cost()`, `credited = min(ceiling, shopper_policy_value)`, zero if unverified. **No model call in this file** | B3 | Returns the `CreditedBenefit` breakdown, not just a total. Write it as if someone hostile will read it, because that is the point of shipping it open |
| B9 🟡 | **Three visually distinct record states** in the log: signed+priced → cited and credited · signed+unpriced → cited, visibly **$0** · unsigned → displayed, **never cited** | B7, B8 | Rows 2 and 3 both credit nothing and a viewer still sees instantly that one is trusted evidence and the other is not. **This is the demo moment** |
| B10 🟡 | Plant the unsigned **"$50 agent bonus"** record | B1 | It visibly earns nothing on screen |
| B11 🟡 | Loyalty layer: identity via UCP, consent-gated enrolment, records re-asserted at checkout | B8 | Values at discovery are **indicative, not binding** — say so; UCP enforces eligibility at checkout |
| B12 🟢 | Close the API loop (gap 7) — checkout settles rather than sets a status flag | B11 | **Idempotent** and explicitly confirmed; replaying a confirmation must not double-credit. **No real payment flow** |

### Unassigned — needs an owner today (§3.3)

| ID | Task | Done when |
|---|---|---|
| U1 🔴 | **Market strategy into README + deck** — 25 pts, equal-highest, and where strong technical teams drop points | It exists in writing, not only in the Round 1 PDF |
| U2 🔴 | **15:30–16:00 Problem Setter window** — lead with the §3.2 open questions | Something visibly changes afterwards (10 pts, Adaptation) |
| U3 🟡 | Evaluation run on the frozen set: constraint-satisfaction rate and citation precision, against `citycircuit` as baseline | **Every number in the pitch comes from here.** Day 2 11:00–12:00 |
| U4 🟡 | Q&A rehearsal; drill **Q2 (Talon.One / UIP)** | That answer exists only as rehearsal, nowhere in writing |
| U5 🟡 | Retire jacket material; electronics examples throughout (gap 9) | No footwear examples in deck or README |
| U6 🟡 | **Citation discipline** (Stage 1 §10) — no vendor-blog figure on a slide | If spoken: *"industry estimates suggest, and we have not verified this"* |

---

## 6. The clock

| Time | What | Owner |
|---|---|---|
| **13:30** | Integration checkpoint. Hieu merges `round2/dev` (H0). Bach opens a PR even if it is a stub | all |
| **14:30** | **Three decisions, out loud.** (1) §3.1 — who owns intent matching. (2) §3.3 — what Nha and Minh are doing. (3) Fallback: if policy extraction is weak, drop to a curated record set and keep the interpreter and the comparison as the demonstrated result | Nha |
| 14:30–15:30 | Vertical slice, all hands: intent in → matched → cited → signed → effective cost → ranked → dashboard out | all |
| 15:30–16:00 | Problem Setter window | Nha |
| 16:00–17:00 | Harden or extend, decided by what actually works at 16:00. Push. Write down tomorrow's scope | all |

Day 2: 09:15–11:00 UX + docs · 11:00–12:00 **evaluation run on the frozen set** ·
**12:00 freeze** · 13:00–15:00 clean-clone test · 15:00–16:30 seed, rehearse twice, record
a backup video · 16:30 submit with buffer. **Hard deadline 17:00.**

Everything runs from **seeded state, zero network calls** — venue wifi is shared by twenty
teams and a live call will fail on stage.

---

## 7. Risks, ranked

1. **Bach owns the heavier app and has written nothing at 13:05.** Everything the pitch
   turns on — the switch, the logs, the invariants — is on his branch.
2. **The #1 judged criterion has no named owner in the new architecture** (§3.1), while the
   person who was building it has shipped a parser that the new doc does not mention.
3. **Two people could implement UCP.** Nguyen has a working head; the new split gives UCP
   integration to Bach. Resolve by consumption, not by rebuilding (§3.2).
4. **Hieu's branch cannot import `src`** until he merges `round2/dev` — an import failure
   will masquerade as a logic failure at the checkpoint.
5. **Market strategy (25 pts) still has no artefact** and, under the new split, no owner.
6. **Commit small and often.** A single large 16:00 push looks exactly like pre-written
   code, which is a **disqualification condition**.

## 8. Deliberately not attempted

Real payment flows · production authentication · live merchant integration · protocol
certification · the 100+ request eval set from proposal §6 Phase 4 (**we ship 30, frozen
before the feed existed** — a smaller honest number with a method beats a larger one we
cannot stand behind in Q&A) · the negotiation / counter-offer protocol (gap 8 — Ford's
call, default is that it stays dropped).

Say this out loud in the pitch. **Scoping deliberately reads better than scoping accidentally.**
