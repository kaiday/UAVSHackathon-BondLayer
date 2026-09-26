# BondLayer Q&A: evidence, version boundaries and claims to check

Companion to [the answer bank](PRODUCT-QA-GUIDE.md) and [quick rehearsal sheet](QA-QUICK-START.md).

## Review basis

This review used the working tree on **13 September 2026**, not only committed documentation. `HEAD` was observed as `2906803` during review, with substantial existing uncommitted work. Other integration work changed files while they were being read, including live model ranking, membership and shopping insights. Git also reported unmerged paths during that integration. This document does not certify the final submission revision.

The preparation files were added separately from the application implementation. Findings below describe the source observed during review. Recheck version-sensitive statements against the actual submitted/demo build before memorizing them.

Evidence labels:

- **Implemented / source reviewed:** the mechanism was inspected in code.
- **Tested:** specific focused tests passed; scope and commands are below.
- **Historical:** recorded benchmark or earlier design, not a measurement of the evolving live build.
- **Proposed:** business strategy or production work still to validate.

## Evidence index

### E1. Product boundary, protocol and intent matching

- [Merchant server](../../bondlayer/src/bondlayer/ucp/server.py): `create_app`, `catalog_search`, `catalog_lookup`, `_respond`.
- [Capability negotiation](../../bondlayer/src/bondlayer/ucp/capabilities.py): `merchant_capabilities`, `parse_agent_header`, `negotiate`.
- [Merchant intent endpoint](../../bondlayer/src/bondlayer/ucp/intent.py): `intent_propose`, `verified_records`.
- [Resolver](../../bondlayer/src/bondlayer/interpreter/resolver.py): `resolve_detailed`, `resolve`.
- [Lexical similarity](../../bondlayer/src/bondlayer/interpreter/similarity.py): `TfidfIndex`.

**Supported statement:** merchant-side publication and justified proposals, with optional negotiated benefit and intent capabilities. Typed attribute checks and TF-IDF lexical similarity are present. The ordinary catalogue `q` filter is substring matching.

**Boundary:** protocol compatibility is implemented against the repository's draft interpretation; external platform conformance was not independently tested in this review. Comments calling future matching “embeddings” do not establish an embedding implementation.

### E2. Catalogue onboarding and persistence

- [Onboarding API](../../bondlayer/src/bondlayer/ucp/onboard.py).
- [CSV adapter](../../bondlayer/src/bondlayer/adapters/catalog.py).
- [Upload storage](../../bondlayer/src/bondlayer/ucp/storage.py): `load_uploads`, `save_upload`, `validate_id`.
- [Onboarding wizard](../../bondlayer/app/src/components/onboarding-wizard.tsx).
- [Upload tests](../../bondlayer/tests/test_upload_onboarding.py).

**Supported statement:** preview and publication, supported normalization, row diagnostics, saved merchant profiles/catalogues and restart restoration. `save_upload` atomically replaces a file containing the profile and catalogue text. Product data is served from process-local memory after parsing.

**Boundary:** atomic file replacement is not a distributed transaction or multi-instance cache-coherence system. CSV upload is not a live Shopify/PIM/ERP connector. Readiness is a weighted data-quality indicator, not a conversion predictor or literal percentage of usable rows.

### E3. Policy extraction, approval and publication

- [AI policy converter](../../bondlayer/src/bondlayer/policy_ai.py): `OpenAIPolicyConverter.drafts_for`.
- [Policy lifecycle](../../bondlayer/src/bondlayer/policy.py): `PolicyStore`, `PolicyOnboardingService`.
- [Policy endpoints](../../bondlayer/src/bondlayer/ucp/policy_onboard.py).
- [Persistent benefits](../../bondlayer/src/bondlayer/ucp/benefits.py): `service`, `publish`, `restore`.
- [Live-workflow contract tests](../../bondlayer/tests/test_live_ai_workflow.py).

**Supported statement:** source passages are enumerated, the model selects passage IDs and known catalogue identities, and the server copies the original source span. The draft retains conditions and begins with no monetary ceiling. Human review precedes signing/publication. Published records and keys persist.

**Observed limits:** at most 60,000 document characters, 40 extracted records and a known-SKU list capped at 1,000 for the extraction prompt. These are relevant when asked about large policy/catalogue coverage.

**Boundary:** passage validity does not validate semantic entailment of every fact. A model can select the right paragraph and still get the number, exception or classification wrong. Human edits can also introduce errors. Do not say “unsupported facts are impossible.”

### E4. Cryptographic record guarantees

- [Canonical representation](../../bondlayer/src/bondlayer/records/canonical.py): `canonical_record`.
- [ES256 signer](../../bondlayer/src/bondlayer/records/signing.py): `sign`, `verify`, `from_jwk`, `private_key_pem`.
- [Public profile](../../bondlayer/src/bondlayer/ucp/profile.py).
- [Signing tests](../../bondlayer/tests/test_records.py).

**Supported statement:** detached ES256 signatures use P-256/SHA-256, encoded as base64url of a 64-byte `R || S` value. Canonical payload includes record identity, type, facts, conditions, issuer, dates, ceiling and source span. Verification rejects malformed signatures, mismatched keys/issuers, future-issued and expired records.

**Boundary:** this is the project's canonical representation, not a demonstrated implementation of every external canonicalization standard. A trusted merchant-to-key association is a prerequisite. Signatures do not prove factual truth, legal enforceability or fulfilment. Private PEM keys are stored unencrypted locally (`NoEncryption()`); gitignore is not key encryption or an authorization mechanism.

### E5. Deterministic valuation and its exact limits

- [Valuation](../../bondlayer/src/bondlayer/valuation/effective_cost.py): `_gating`, `_scope_of`, `DeterministicValuation.effective_cost`.
- [Composition](../../bondlayer/src/bondlayer/agent/composition.py): `run_request`, `realisable_credit`.
- [Reference policy](../../bondlayer/src/bondlayer/valuation/reference_policy.py).
- [Invariant tests](../../bondlayer/tests/test_invariants.py).

**Supported statement:** verifier, merchant/product binding, supported eligibility conditions, duplicate-record handling, per-type shopper budgets, Decimal arithmetic and a composition-level nonnegative effective-cost floor.

**Boundary:** free-text conditions are preserved but the original `_gating` mechanism only executes token-shaped conditions. It is not a general policy interpreter. Per-type budgets are not a complete cross-type promotion-stacking engine. Eligibility integration changed during review; inspect the final call's `satisfied_conditions` and merchant identity handling.

**Precise anti-inflation statement:** credit is bounded by the shopper cap. Increasing a ceiling from $10 to $20 can change credit when the cap is $40. Increasing it from $50 to $5,000 cannot raise that type above a $40 cap. Tests with already-saturated caps do not prove the stronger universal claim.

### E6. Current live buyer and AI boundaries

- [Buyer entry points](../../buyer-agent/src/agent/main.py): `_handle_query`, `handle_chat`.
- [Buyer model ranking](../../buyer-agent/src/agent/rank.py): `parse_intent`, `_offer_payload`, `rank_offers`, `apply_ranking`.
- [Buyer model transport](../../buyer-agent/src/agent/llm.py): `complete_json`, `_complete`, `transcript_payload`.
- [Shared OpenAI client](../../bondlayer/src/bondlayer/ai.py): `structured`, `mode`, `AIError`.
- [Intent decode](../../bondlayer/src/bondlayer/interpreter/openai.py): `decode`.
- [Merchant interpretation wrapper](../../bondlayer/src/bondlayer/agent/merchant_decode.py).
- [Live-mode integration tests](../../buyer-agent/tests/test_openai_integration.py).

**Supported statement in the later inspected source:** live mode decodes once for its search, calls the shared composition with hard-constraint enforcement, then obtains a model ranking. `apply_ranking` reorders the known `(merchant, sku_id)` offers and appends any omitted known offers. Checkout follows the reordered winner. Rules mode retains reference arithmetic.

**Model output restrictions:** unknown/duplicate offer identities are ignored; a response selecting no known offer errors. The implementation does not independently prove that every free-text `decisive_terms` or `reasoning` claim is entailed by a verified fact.

**Payload issue worth understanding:** `_offer_payload` constructs `attached_terms` from citation `why` strings. It does not carry the full `record.fact`, original conditions or source span. A record's 60-day return window or 24-month warranty can therefore disappear into a generic “verified and citable” message. The strings can also contain `min(merchant $…, shopper $…)`, despite explicit `credited` and `effective_cost` fields being omitted. Input order is already the reference order, which may anchor model output. Do not claim the model sees all raw terms and no arithmetic influence.

**Failure behavior:** shared provider calls use structured schemas, a 45-second timeout and one retry; errors are explicit. A live comparison may use buyer decoding, ranking, per-merchant decoding and a conversation-routing call. “Two calls total” is not generally true. No per-query cost or latency benchmark was established here.

### E7. Checkout and bundling

- [Checkout endpoint](../../bondlayer/src/bondlayer/ucp/checkout.py): `CheckoutRequest`, `judge`, `order_id`, `checkout`.
- [Buyer close loop](../../bondlayer/src/bondlayer/agent/close_loop.py): `checkout_body`, `close_loop`.
- [Bundle composition](../../bondlayer/src/bondlayer/bundle/compose.py).
- [Checkout tests](../../bondlayer/tests/test_checkout_route.py).

**Supported statement:** known items are confirmed at current catalogue prices; published stock is checked when available; cited records are judged for publication, signature, expiry and applicability. Extra checkout input fields are forbidden. Existing signed record envelopes can accompany the confirmation.

**Boundaries:**

- No money moves; response status is `confirmed_awaiting_payment`.
- Inventory is not reserved or decremented; there is no durable order ledger.
- Honouring a record can remain subject to conditions; the verdict does not execute every eligibility or return condition.
- No complete tax, delivery, payment, cancellation or return-management flow.
- No submitted-price/catalogue-version precondition proving quote parity.
- `order_id` is the first 16 hex characters of a content hash over merchant, line items and honoured record IDs, not a newly signed order. Price and full benefit content are not included.
- The demonstration close loop selects one winning SKU, not necessarily an entire displayed bundle.
- The recipe-based bundler is not universal product compatibility validation.

### E8. Activity, insights and observed outcomes

- [Activity persistence](../../bondlayer/src/bondlayer/activity.py): `save_request`, `reports`.
- [Insights aggregation](../../bondlayer/src/bondlayer/insights.py): `capture_observation`, `build_insights`.
- [Insights endpoint](../../bondlayer/src/bondlayer/ucp/insights.py).
- [Request endpoints](../../bondlayer/src/bondlayer/ucp/onboard.py).

**Supported statement:** actual demo comparisons are saved locally. Later insights code filters dated live reports, aggregates merchant observations and preserves unknown outcomes. Reports are limited to the latest 500 loaded by the activity reader.

**Boundary:** counts are saved runs, not unique people or a census of store traffic. Both comparison panes count as separate observations. Confirmation is not payment. A loss reason is observed evidence or a model/reference comparison outcome, not causal proof of lost revenue.

**Deployment issue:** cross-merchant report files and unauthenticated local console APIs are part of the demo. The UCP message boundary does not by itself protect the wider deployment's analytics. Independent agents must supply feedback before an external merchant can know their final selection.

### E9. Identity, tenancy and security readiness

- [Identity route](../../bondlayer/src/bondlayer/ucp/identity.py): `identity_link`.
- [Merchant membership lookup](../../bondlayer/src/bondlayer/ucp/membership.py): `resolve_shopper`.
- [Merchant server](../../bondlayer/src/bondlayer/ucp/server.py).
- [Benefits key storage](../../bondlayer/src/bondlayer/ucp/benefits.py).

**Supported statement:** the identity route derives status and tier from a merchant roster rather than taking an asserted tier as the answer. Catalogue behavior can use the resolved ID.

**Boundary:** accepting a shopper ID is not authentication of the person controlling that account. No credential exchange or session is established by this route. Do not call it a complete OAuth/account-linking solution. Production needs authenticated ownership, authorization, tenant isolation, rate limits, protected keys and scoped data retention. These are concrete gaps, not a claim that a security review has passed.

### E10. Challenge fit and historical evaluation

- [FPT problem statement](../FPT-Problem-Statement-Final.pdf), pages 2–3: merchant-side decoding, matching, justified proposals and API transaction; intention accuracy first, then architecture, then business value.
- [Rulebook](../Hackathon-Rulebook-2026-Final-Updated-1.pdf), pages 6–7: 10-minute pitch, 5-minute Q&A; final-round Q&A defence worth 25 points. The Gala demo uses the submitted Round 2 product.
- [Evaluation report](../../bondlayer/docs/eval-results.md), headline and decode-method sections.
- [Historical requests](../../bondlayer/data/eval/requests.json).
- [Pitch outline](PITCH-OUTLINE.md), historical scripts and older drill cards.

| Historical metric | Recorded result | Correct interpretation |
|---|---|---|
| SERVICE + VALUES answerability | 15/18 versus 0/18 | Additional evidence coverage in this ablation. |
| Citation verification | 154/154 | All cited records pass the verifier; not independent truth or relevance validation. |
| Hard precision | 0.875 mean over 30 | Returned proposals versus the frozen gold, subject to documented ambiguity and bundle labels. |
| Gold recall | 0.991 mean over 30 | Gold coverage in the historical setup. |
| Decode precision / recall | 0.914 / 0.972 | Rules-parser token/kind matching, not current model understanding accuracy. |
| Perfect decodes | 22/30 | Perfect under the stated scoring method. |

The report records generation at `90de308`; README history records re-verification at `339a7ed`. Treat those as historical provenance, not this review's current live results. The focused `test_eval.py` checks passed here, but the report-writing evaluation command was not rerun to replace historical artifacts.

The gold was frozen before the benefit feed, with a documented later gold correction. This improves auditability but does not make the 30 synthetic examples representative of all retailers. A baseline with no record input cannot answer from records; compare with richer competing baselines before claiming market superiority.

### E11. Highest-priority wording and implementation findings

| Tempting claim | Why it fails | Defensible wording |
|---|---|---|
| “The LLM never decides ranking.” | Later `main.py` explicitly invokes `rank.apply_ranking`. | “The live demo uses model ranking; reference mode uses deterministic effective cost.” |
| “Unverified claims cannot change any ranking.” | This holds for deterministic monetary credit, but the live ranker sees unverified entries and relies on an instruction to ignore them. | “They receive zero deterministic credit. Live-model resistance to influence needs separate evaluation.” |
| “The model sees all benefit terms, with no arithmetic.” | `rank._offer_payload` passes citation summaries, omits raw fact detail and can expose arithmetic through `why`. | “The current ranker sees a reduced term summary; inspect its actual prompt before claiming full semantic comparison.” |
| “A signature proves the merchant's claim.” | It proves integrity relative to a key, not truth or business identity on its own. | “Signed and attributable to the trusted issuer.” |
| “Increasing a ceiling can never improve rank.” | Below-cap increases can raise credit. | “Credit cannot exceed the shopper's per-type cap.” |
| “We verify all policy conditions.” | Free text is retained, not generally executed; checkout verdicts may be conditional. | “We check supported conditions and expose the remaining terms.” |
| “There is a statutory 12-month warranty.” | Current rank prompt uses this example; Australian consumer guarantees can outlast a manufacturer's warranty. | “Compare actual added coverage against applicable consumer rights.” |
| “We authenticate membership.” | The new route looks up an ID without proving ownership. | “We demonstrate merchant-roster lookup.” |
| “The merchant never learns the shopper's intent.” | Intent matching sends the sentence; base search can reveal budget; identity adds an ID. | “We minimize fields according to the selected route; explicit valuation weights are not normal UCP fields.” |
| “No competitor has warranty/loyalty metadata.” | Public standards already include warranties and membership-related data. | “Our demonstrated focus is the review-and-sign publishing workflow.” |
| “We deliver 83% more sales.” | 83% is 15/18 synthetic clause answerability. | “We answered 15 of 18 service-and-values clauses in the historical test.” |
| “A confirmed order proves purchase.” | No payment, stock reservation or durable order flow. | “API checkout confirmation; payment is outside this prototype.” |
| “The graph proves the current architecture.” | Extraction preceded later working-tree changes and has unresolved graph edges. | “The graph is a navigation aid; implementation claims were checked in source.” |

**Suggested team priorities before a live rehearsal:** align all presenters on ranking mode; inspect the rank prompt's actual benefit facts and legal wording; align bundle/trace/insight descriptions with the final winner; confirm the selected demo revision is runnable. These are review findings, not a record of fixes performed.

### E12. Verification performed in this preparation session

**79 merchant-side tests passed** using the repository environment. Run from `bondlayer/`:

```powershell
$env:PYTHONUTF8 = '1'
$env:BONDLAYER_AI_MODE = 'rules'
& '..\.venv\Scripts\python.exe' -m pytest -q tests/test_records.py tests/test_invariants.py tests/test_upload_onboarding.py tests/test_live_ai_workflow.py tests/test_checkout_route.py tests/test_eval.py
```

**17 buyer-side tests passed**. Run from `buyer-agent/`:

```powershell
$env:PYTHONUTF8 = '1'
$env:BONDLAYER_AI_MODE = 'rules'
& '..\.venv\Scripts\python.exe' -m pytest -q tests/test_openai_integration.py tests/test_query.py tests/test_onboarded_merchants.py
```

Both runs emitted a dependency deprecation warning from Starlette/AnyIO. Tests of live-mode behavior stubbed provider transport. No paid OpenAI requests were made for this review. This is **96 focused passing tests**, not a claim that every test, current merge, frontend build, production integration or model-quality evaluation passed.

## External sources checked

Public pages retrieved during this preparation on 13 September 2026:

- **S1:** [schema.org: MerchantReturnPolicy](https://schema.org/MerchantReturnPolicy). Represents return windows, fees, methods, conditions and membership-tier applicability. Counters the claim that ordinary structured standards cannot represent returns.
- **S2:** [schema.org: WarrantyPromise](https://schema.org/WarrantyPromise). Represents warranty duration and scope; can attach to an offer. Counters the claim that no warranty schema exists.
- **S3:** [Talon.One: Introducing the Unified Incentives Protocol](https://www.talon.one/blog/introducing-the-unified-incentives-protocol). The vendor describes platform-agnostic incentive standards and an initial UCP loyalty extension. This establishes the vendor's documented positioning, not independently verified performance or proof of every claimed implementation detail.
- **S4:** [Consumer Affairs Victoria: Expired warranty](https://www.consumer.vic.gov.au/consumers-and-businesses/products-and-services/refunds-repairs-and-returns/warranties/expired-warranty). Explains that consumer remedies may apply after warranty expiry; its example is a $6,000 TV failing after two years despite a 12-month manufacturer's warranty. Do not treat a warranty end date as the end of all consumer guarantees.

The README's wider market statistics and every competitor's full current feature set were not independently validated here. Use only the level of claim these sources support.

## Supporting repository map

A local graph was generated in [graphify-out](../../graphify-out/GRAPH_REPORT.md), with an [interactive HTML view](../../graphify-out/graph.html) and raw graph JSON. It contains 2,217 nodes and 4,802 edges from the initial scan.

Its extraction diagnostic reported **533 dangling-endpoint edges and 296 undirected same-endpoint collapsed edges**. It also predates some concurrent code changes. Use it to find related components, not as a substitute for source verification. Host-agent token usage was unavailable from the harness; extraction cost cannot honestly be reported as zero.

The graph tool's synthetic context-size benchmark estimated 22.0× fewer tokens per graph query than its naive corpus baseline. That is a tooling estimate, **not a BondLayer product performance or cost metric**.
