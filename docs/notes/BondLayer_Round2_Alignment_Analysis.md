# BondLayer — Round 2 Alignment Analysis

**UAVS Hackathon 2026 · FPT Australasia — "The B2A Shift: Adapting Retail for AI Shopping Agents"**

Assessment of whether the Round 1 project aligns with the full Round 2 problem statement.

| | |
|---|---|
| **Date of analysis** | 12 September 2026 (Round 2, Day 1) |
| **Sources read** | `FPT-Problem-Statement-Final.pdf` (3pp) · `FPT_Round1_Challenge_Brief.pdf` (1p) · `Hackathon-Rulebook-2026-Final-Updated-1.pdf` (11pp) · `BondLayer_PROJECT_HANDOVER.md` · repo: `bach-demo/` (BondLayer spike) + `demo/` (AgentBridge spike) |
| **Verdict** | Aligned on the challenge. Strong on judging priorities 2 and 3. **Thin on priority 1, which carries the most weight.** |

---

## 1. Three facts that frame everything

### 1.1 It is the same challenge — no pivot needed

`FPT-Problem-Statement-Final` is the **full 3-page version** of the one-page `FPT_Round1_Challenge_Brief` the Round 1 proposal was written against. Same title, same challenge question, same owner, same domain, same merchant-side framing.

What is **new** in the Final version, and absent from the Round 1 teaser:

- Three illustrative directions (semantic intention-matching; values-based SEO for agents; dynamic B2A negotiation)
- An explicit in-scope / out-of-scope table
- A five-step "what a good solution looks like" walkthrough
- **Weighted evaluation priorities** — these did not exist in the Round 1 brief and are the single most important addition

### 1.2 Round 2 Day 1 is today — and no prior code may be used

Rulebook, §b *Code and product regulations*:

> All code must be written during the Hackathon period (Day 1 & Day 2). **Using code written before 09:00 on 12/09/2026 is strictly prohibited.**

Schedule: Day 1 — 12/09, 09:00–17:00 AEST (build MVP) · Day 2 — 13/09, 09:00–17:00 AEST (refine, test, UX, documentation).

Therefore **neither `demo/` (AgentBridge) nor `bach-demo/` (BondLayer) may be copied into the submission.** `bach-demo/README.md` states this itself at the top. Their value today is the **specification, schema, synthetic data, prompts and demo script** — the artefacts the rules permit as pre-work — not the Python.

Permitted (per rulebook + handover §8): open-source libraries, public APIs, pre-trained models, common boilerplate, and pre-prepared specs / declared synthetic datasets / demo scripts / task splits.

### 1.3 Two different rubrics are in play

**Rulebook — Round 2 (100 pts, selects top 10 for the Gala):**

| Criterion | Score |
|---|---|
| 1. User experience | 20 |
| 2. Technical quality | 25 |
| 3. Deployability and scalability | 20 |
| 4. Market strategy | 25 |
| 5. Adaptation and upgrade | 10 |

**Problem statement — Gala Pitching Night priorities, in order of weight:**

1. **Intention Accuracy & Semantic Matching** — how intelligently the merchant's system decodes the nuanced needs of the human behind the agent, going beyond basic keyword or spec matching
2. **Technical Architecture** — viability and scalability; effective use of APIs, dynamic bundling, and LLM-to-LLM communication
3. **Business Value & Conversion** — how well it helps a traditional product company win the sale by proving to the agent that its product is the best fit

> **Note on presentation (verbatim from the statement):** visual polish of human-facing dashboards is a **lower** priority than the logic of the machine-to-machine interaction.

The FPT priorities enter the Round 2 score chiefly through criterion 5, *Adaptation and upgrade* — "how well the team incorporated the full case study and Problem Setter input."

**Rulebook — Round 3 Gala (100 pts, final ranking):** Pitch quality 30 · Live product demo 25 · Q&A defence 25 · Deployment potential 20.

---

## 2. Where BondLayer aligns — genuinely strongly

| Problem statement asks for | BondLayer has | Evidence in repo |
|---|---|---|
| Merchant-side only; building a consumer-facing AI shopping assistant is **out of scope** | Nailed, and defensible as a deliberate design stance | `/evidence` architecture tab: *"Where is the BondLayer agent? There isn't one, by design."* |
| Machine-readable data structuring | The strongest asset — catalogue adapter, typed benefit records, ontology, Ed25519 signing | `ingest/catalog_adapter.py`, `schema.py`, `signing.py` |
| *"What friction does a machine encounter on a website built for humans?"* | Answered literally — messy merchandising exports normalised into conformant UCP | `ingest/remediation.py`, `data/merchants/*/catalog_export.csv` |
| Step 4: *"not just a list of SKUs, but a logical justification of why"* | Deterministic ledger plus a faithfulness-checked explanation. Better than most teams will field | `agent/trv.py`, `EXPLAIN_SYSTEM` in `agent/shopping_agent.py` |
| Step 5: closing the loop via API-driven transaction | **Partial** — `identity_linking` implemented, checkout is a status flag | `ucp/server.py` |
| API-based checkout flows (in scope) | UCP-shaped endpoints with real capability negotiation | `ucp/server.py`, `ucp/capabilities.py` |
| Priority 2 — Technical architecture | Real capability negotiation, Ed25519, 14 conformance checks, invariants enforced as tests | `ucp/conformance.py`, `tests/test_invariants.py` |
| Priority 3 — Business value and conversion | Visibility console, before/after flip, loss reasons. Also feeds Market strategy (25 pts) | `visibility.py`, `app/web/` |
| Risk of *"hallucinated product claims"* (named in the statement's problem framing) | The unsigned-claim penalty is a sharp, demonstrable answer | `tests/test_invariants.py` property 2 |

**Two enforced properties remain a differentiator** and map cleanly onto the statement's concern about misinterpreted and hallucinated claims:

1. A merchant can never improve its own position by inflating a number (declared figures act only as a ceiling).
2. A bigger unsigned claim costs the merchant more (unverified claims are never valued and are penalised in proportion to the claim).

---

## 3. Where it does not align

### 3.1 Priority #1 — the highest-weighted criterion — is the thinnest area

> *"Intention Accuracy & Semantic Matching. How intelligently the merchant's system decodes the nuanced needs of the human behind the agent, going beyond basic keyword or spec matching."*

**a) Intent decoding is a valuation-policy extractor, not an intent decoder.**

`bach-demo/src/bondlayer/agent/shopping_agent.py:38` (`INTENT_SYSTEM`) returns four fields:

```
query · budget_aud · fit_risk_aud · max_loyalty_premium_pct
```

That decodes *how price-sensitive this shopper is*. It does not decode "beginner-friendly podcasting gear," lifestyle context, or personal values — which is what the statement's worked example and step 1 ("deep human intention, lifestyle context, and personal values") actually ask for.

**b) Semantic matching is absent.**

`bach-demo/src/bondlayer/ucp/server.py:110`:

```python
terms = [t for t in q.lower().split() if len(t) > 2]
matches = [o for o in self.offers
           if not terms or any(t in (o.title + " " + o.brand).lower() for t in terms)]
```

Substring keyword match on title and brand. This is precisely the thing criterion 1 says to go beyond.

**c) The demo scenario cannot demonstrate matching at all.**

All three merchants sell the *same* jacket — barcode `9312345678907` appears in all three `catalog_export.csv` files. The scenario is a price-versus-value comparison: an excellent vehicle for verification and valuation, and a null vehicle for intent matching, because there is nothing to match.

Handover assumption **A1** promised a synthetic catalogue of **60–100 SKUs with near-duplicates and attribute noise "to stress semantic matching."** The spike carries 2–3 SKUs per merchant.

**d) The roadmap defers the top-weighted criterion.**

Handover §6 Phase 3 defers embedding-plus-attribute matching to post-hackathon; Phase 4 defers the 100+ multi-constraint evaluation set to post-hackathon. Both are the substance of priority 1.

### 3.2 Dynamic bundling is missing

Named twice in the statement — in the in-scope list, and inside criterion 2 ("effective use of APIs, **dynamic bundling**, and LLM-to-LLM communication"). Illustrative direction 1 also ends on it: *"pitches the ideal bundle based on that intent."* Nothing in either spike bundles.

### 3.3 Values-based matching is unmodelled — but is a cheap, high-scoring win

Illustrative direction 2 asks for sustainability, ethical sourcing and long-term durability to be surfaced and structured, so "only buy from ethical brands" can be matched **and validated**.

The current benefit ontology is entirely monetary and service-based: `member_price · points_earn · free_returns · warranty · trade_in_credit · delivery`. Values do not convert to dollars, so they fall outside the valuation model.

**But the signing machinery is exactly the right answer to this direction.** A verified ethical claim versus unverifiable greenwashing is the same mechanism already built and already tested — applied to a claim type that is displayed and validated rather than priced. This is the lowest-cost, highest-alignment extension available.

### 3.4 The negotiation protocol was deliberately dropped, and the statement re-legitimises it

Illustrative direction 3 describes exactly the retention/counter-offer engine removed in handover decision-log item 2. `bach-demo/docs/deferred-retention-engine.md` documents how to pick it back up.

It is an **illustrative example, not a requirement**. Reversing that call is Ford's decision, not a technical one — decision-log item 2 says do not silently reverse it.

### 3.5 Minor: vertical drift in the spike

The Round 1 proposal switched the vertical to **consumer electronics** (decision-log item 3: all new material must use electronics examples). `bach-demo/` is outdoor jackets — pre-switch material. Any catalogue authored today should be electronics.

---

## 4. Tension to manage: UX points versus the Problem Setter's steer

| Source | Says |
|---|---|
| Rulebook R2 criterion 1 | User experience — 20 points — "intuitive, easy-to-use interface" |
| Problem statement | "Visual polish of human-facing dashboards is a **lower** priority than the logic of the machine-to-machine interaction" |
| Handover §2, workshop steer (UAVS-NSW 2026) | "Algorithm over UI — a simple API / basic interface suffices" |

**Resolution:** the visibility console must be **legible and functional**, not beautiful. It earns UX points by clearly identifying and meeting the target user's needs (e-commerce and loyalty leads), which is what criterion 1 actually describes. Do not spend Day 2 hours on visual polish; spend them on the matching logic and the demo's machine-to-machine narrative.

---

## 5. Verdict and recommended reframe

**Aligned on the challenge, and strong on priorities 2 and 3 — but the headline demo currently proves the thing the judges weight *third*, not first.**

Nothing needs to be scrapped. The gap is **additive**: an intent layer and a catalogue worth matching against, sitting *in front of* the verification and valuation engine already de-risked in `bach-demo/`.

**One-sentence reframe for the pitch:**

> Decode the intent, match the catalogue semantically, then prove with signatures why our match is the one you can trust.

Mapped to the judging priorities:

| Priority | Weight | What carries it |
|---|---|---|
| 1. Intention accuracy and semantic matching | Highest | **New** — multi-constraint intent schema, embedding-plus-attribute matching, an electronics catalogue with near-duplicates, a published evaluation set |
| 2. Technical architecture | Second | **Existing moat** — UCP capability negotiation, Ed25519, deterministic valuation, conformance tests. Add dynamic bundling |
| 3. Business value and conversion | Third | **Existing** — visibility console, before/after flip, loss reasons |

This also preserves the team's own "plug / pitch" framing (decision-log item 5): feature 1 still gets you into the race, feature 2 still helps you win it — matching is what decides *which race you are in*.

---

## 6. Gap list, ranked by score impact

| # | Gap | Maps to | Cost | Priority |
|---|---|---|---|---|
| 1 | Multi-constraint intent schema — lifestyle, values, use-case, constraints — replacing the four-field policy extractor | Priority 1 | Medium | **Critical** |
| 2 | Semantic catalogue matching — embeddings plus attribute filters, replacing substring match | Priority 1 | Medium | **Critical** |
| 3 | Electronics catalogue, 60–100 SKUs, near-duplicates and attribute noise (handover A1) | Priority 1 | Low–Medium | **Critical** — without it there is nothing to match |
| 4 | Dynamic bundling — propose a bundle against decoded intent, not a SKU list | Priorities 1 and 2 | Medium | High |
| 5 | Values-based claims as a signed, validated (not priced) record type | Direction 2, Priority 1 | **Low** — reuses existing signing | High — best effort-to-score ratio |
| 6 | Multi-constraint evaluation set with reported match accuracy | Priority 1, Technical quality | Low | High — the only way to *evidence* priority 1 |
| 7 | Close the API loop — checkout beyond a status flag | Step 5 | Low | Medium |
| 8 | Negotiation / counter-offer protocol | Direction 3 | High | Optional — requires Ford to reverse decision-log item 2 |
| 9 | Electronics examples throughout, retiring jacket material | Adaptation (10 pts) | Low | Medium |

---

## 7. Open items carried over from the handover

Still outstanding and now urgent:

1. **Team name** — still undecided; needed for the team-info block and the pitch title.
2. **Merchant ↔ agent JSON contract spec** — handover §8 calls this "the single most important integration point," status *not yet written*. Permitted as a pre-hackathon document.
3. **Intent-accuracy evaluation set (100+ requests)** — promised in proposal §6 Phase 4; not written. Now also the primary evidence for judging priority 1.
4. **Synthetic electronics catalogue and three merchant manifests** — permitted as declared pre-hackathon data.
5. **Q&A rehearsal** per handover §9 — especially Q2 (Talon.One UIP), deliberately omitted from the written proposal.

---

## 8. Verification notes

- The two problem-statement PDFs in `UOW/UAVS/` are byte-identical (`md5 36db90ef…`); the four rulebook copies are identical in size and content. No version conflict.
- `bach-demo/README.md` cites Round 2 as 05–06/09 with a 05/09 code cutoff. Those dates are **stale** — the rulebook and handover both give 12–13/09 with a 09:00 12/09 cutoff. The *rule* is unchanged in shape: no pre-existing code.
- Handover §2 records the Round 2 rubric as "UX 20 · technical 25 · deployability 20 · market 25 · adaptation 10" — this matches the rulebook exactly, confirmed against pp. 192–220.
