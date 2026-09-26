# BondLayer product Q&A: four audiences, 60 questions

Prepared 13 September 2026. Start with [QA-QUICK-START.md](QA-QUICK-START.md). Source references such as **E3** point to [QA-EVIDENCE-NOTES.md](QA-EVIDENCE-NOTES.md).

These are spoken-answer drafts, not claims that every planned capability is implemented. Commercial proposals are labelled as proposals. The live buyer implementation changed during review: the current model-ranked client and the historical deterministic benchmark must be explained separately.

## A. Non-technical audience, no commerce background

### Q1. What is BondLayer, in ordinary language?

**Say:** “We help a shop explain its products and service benefits to AI shopping assistants. The shop uploads its product list and policies; BondLayer turns them into organized information that compatible assistants can inspect.”

**Example:** A laptop's price is in a spreadsheet; its return window is in a policy document. BondLayer helps put both into the comparison.

**Evidence:** E1–E3.

### Q2. What is a shopping agent, and what does B2A mean?

**Say:** “A shopping agent is software that searches and compares products for a person. B2A means business-to-agent: the retailer must explain its offer to the software acting for its customer, as well as to the customer directly.”

The human still sets the goal. Whether a real agent may spend money depends on the authority its user gives it. Our demonstration does not move money.

### Q3. What problem exists today?

**Say:** “Some useful facts are easy for software to read, such as price. Other facts are scattered across pages and policy documents, so comparison can miss them or interpret them inconsistently. A retailer with useful service benefits may therefore look less attractive than its complete offer deserves.”

Avoid claiming that all current agents only compare prices. The problem is inconsistent access to reliable, usable information.

### Q4. Who uses your product?

**Say:** “The main human user is the retailer's e-commerce team. They manage the catalogue and policies. Marketing leaders care about whether the offer is represented accurately, IT teams handle integration, and shopping agents are the machine consumers of the published information.”

The buyer chat page demonstrates the other end of the connection. The merchant service is the product. **Evidence:** E1, E10.

### Q5. How would a shop start using it?

**Say:** “Enter the business details, upload a CSV product spreadsheet, inspect the validation report and publish the accepted products. Then upload a policy document, review the extracted benefit drafts, approve them and publish the signed records.”

Current catalogue onboarding uses CSV. Policy uploads accept supported text documents and text-readable PDFs. A scanned image-only PDF is not the same thing as extractable text. **Evidence:** E2–E3.

### Q6. Does it replace a retailer's website?

**Say:** “It adds a machine-readable publishing surface around the retailer's information. The retailer can keep its customer-facing store and existing commerce systems. Connecting those systems for continuous updates is part of deployment.”

The prototype starts with file uploads; it does not demonstrate every platform connector.

### Q7. Can you guarantee our shop will be recommended?

**Say:** “No. We can help the agent understand the offer more completely. The shopper's requirements and the agent's comparison still determine the outcome. Sometimes the cheaper competitor is genuinely the better choice.”

This is a stronger long-term promise than guaranteed ranking: publish what is supportable, rather than sell preferential treatment.

### Q8. What is a signed benefit record?

**Say:** “It is a structured statement with a digital seal. An agent can check that it matches what the holder of a particular signing key issued and that the statement has not been changed.”

**Important follow-up:** It is not an independent inspection of the retailer. A correct signature can accompany an incorrect statement. **Evidence:** E4.

### Q9. Why must a human review the AI output?

**Say:** “Policies have exceptions, exclusions and wording that affects what customers actually receive. The AI produces a draft tied to source passages; the merchant checks it before publication. We want the merchant to approve its commitments, rather than let a model publish them automatically.”

Source anchoring is useful evidence, but it does not automatically prove that every extracted fact or omitted exception is correct. **Evidence:** E3.

### Q10. Does a lower effective cost mean I pay less at checkout?

**Say:** “No. Effective cost is a comparison aid that expresses how much certain benefits are worth under a shopper's policy. If a $1,000 product has $80 of credited benefit value, the comparison figure is $920; that does not create an $80 cash discount.”

The current live model-ranked buyer may choose an offer that is not the minimum effective-cost offer. Keep the comparison number separate from both the model decision and the amount payable. **Evidence:** E5–E6.

### Q11. What happens after the agent chooses an item?

**Say:** “Our demonstration sends the selected item to an API checkout endpoint. The merchant rechecks the cited benefits and returns a confirmation with the relevant records. It explicitly says payment is outside the prototype.”

That proves a confirmation interaction. It does not prove payment, delivery, a stock reservation or an enforceable dispute process. **Evidence:** E7.

### Q12. What is working, and what comes next?

**Say:** “The working prototype covers catalogue upload and validation, reviewed policy publication, signatures, agent queries and checkout confirmation. We also have a buyer demonstration and local activity views. The next step is a narrow retailer pilot, then authenticated access, live commerce-system integration and independent interoperability testing.”

If asked whether it works for their exact store: explain the supported file format, product category and policy scope first; do not promise an integration that has not been tested.

## B. Non-technical audience with commerce knowledge

### Q13. Who is the first customer, and who owns the budget?

**Say:** “Our initial customer hypothesis is a mid-market retailer, starting with electronics, that has useful service benefits and exportable data but limited agent-integration capacity. An e-commerce or digital-commerce leader would likely sponsor it, with marketing and IT involved. We still need interviews to establish the real budget owner and willingness to pay.”

Electronics is a sensible starting category because specifications, repairs, returns and warranties influence the choice. It is also where the current resolver and benchmark are concentrated.

### Q14. What measurable business outcome are you selling?

**Say:** “First, reduced work to publish usable product and policy information. Second, better coverage of the requirements an agent asks about. Third, a commercial hypothesis: better representation may improve qualified selections and purchases. We have demonstrated the first workflow and measured synthetic answerability; real conversion and retention effects need a pilot.”

Measure the funnel separately: successful publication → discoverable offers → requirements answered → agent selections → paid orders → margin and returns.

### Q15. What is the business model?

**Say:** “We propose a hosted merchant subscription, with tiers based on catalogue size and request usage. The merchant pays for the publishing and maintenance service. We have not validated a price or built billing into this prototype.”

A subscription also helps communicate that the service is not selling placement in the agent's ranking. Integration and support costs must be included in the economics.

### Q16. How would you calculate merchant ROI?

**Say:** “We would compare the incremental contribution from paid orders and verified staff time saved against the subscription, integration and additional benefit costs. More recommendations alone are not ROI, and revenue is not profit.”

Proposed calculation:

```text
Net incremental value
  = incremental order contribution
  + verified operating-cost savings
  - incremental benefit/returns costs not already included in contribution
  - subscription and integration costs
```

Define the accounting consistently so discount, delivery and return costs are not counted twice. Use a matched or randomized pilot where feasible, rather than treating every selected offer as an incremental sale.

### Q17. Why would this protect margin rather than cause another price war?

**Say:** “It gives an agent relevant reasons to choose a higher-priced offer when the shopper values the service difference. We are not automatically adding discounts. Whether that protects margin depends on the cost of providing the benefits and whether the resulting demand is incremental.”

A benefit that costs more than the contribution it attracts can still be bad business. The pilot should measure contribution after the associated service costs.

### Q18. Why not just improve schema.org markup or the product feed?

**Say:** “That is a credible option and should be part of the baseline. Schema.org already represents returns and warranties. Our proposed added value is the operational workflow: extracting policy drafts, obtaining merchant approval, attaching scope and source evidence, signing the records and publishing them for compatible agents.”

Do not say that no warranty or loyalty representation exists elsewhere. Standard mappings are an integration opportunity. **Evidence:** external sources S1–S2.

### Q19. How do you compare with Talon.One UIP or Shopify tooling?

**Say:** “Established platforms already work on agentic commerce and incentive discoverability. Talon.One describes UIP as platform-agnostic standards for loyalty and promotion information. Our starting point is a file-based merchant workflow and reviewed service-benefit records. We need to prove that this is useful alongside existing systems, rather than assume those systems cannot address the problem.”

**If pressed:** “We have not independently established a feature-by-feature security advantage over those vendors. Our differentiation claim is about the workflow we demonstrate.” **Evidence:** S3.

### Q20. Why would agents adopt your extension?

**Say:** “They gain structured evidence that can help answer shopper requirements, and the format is inspectable. Basic catalogue clients can still receive basic products. But the full benefit value depends on agent support, so partner integrations and interoperability tests are necessary.”

This is a real adoption dependency. Merchant data-quality benefits provide an initial use case; they do not eliminate the need for agent-side adoption.

### Q21. How do you get your first customers?

**Say:** “We propose one retail design partner through an integrator or e-commerce agency, ideally with an owner for catalogue and policy data. Start in shadow mode: process real exports and compare outputs without affecting purchasing. Expand only after the merchant finds the information accurate and useful.”

FPT's retail relationships are a proposed route to that pilot, not a signed distribution agreement.

### Q22. What does FPT gain?

**Say:** “Potentially a reusable accelerator for retail clients adopting agent-facing commerce: a repeatable catalogue-and-policy publishing workflow, plus an evidence model that integration teams can inspect. We would ask FPT to help validate the integration problem and identify the first client, not claim that partnership already exists.”

A concrete ask: one design partner, one business owner, one integration owner, and agreed success measures.

### Q23. What is your moat if the protocol is open?

**Say:** “The protocol alone is not a moat. A defensible business would need dependable connectors, policy-conversion quality, efficient merchant review, monitoring and trusted distribution. Those are capabilities to build and validate; the current prototype does not establish a proprietary network advantage.”

Any learning from merchant or shopper data also depends on rights, consent and actual access. A local demo log is not an industry-wide data asset.

### Q24. How do you keep policies, prices and stock up to date?

**Say:** “The prototype publishes uploaded snapshots. A merchant can replace its catalogue and republish reviewed benefits, and saved data is restored on restart. Production would need scheduled or event-driven updates from authoritative systems, freshness timestamps and a way to invalidate stale records.”

A valid signature does not make a price current. Expiry checks are useful, but they are not a full freshness or revocation system. **Evidence:** E2–E4, E7.

### Q25. Does the dashboard show sales conversion or lost revenue?

**Say:** “It shows observed local comparison activity and evidence gaps. The newer insights code counts saved runs, offer availability, reported selections and checkout confirmations. Those are not unique shoppers, all store traffic, paid orders or lost revenue.”

Selection information exists here because our demo agent saves it. An independent shopping platform would need to share appropriate feedback. **Evidence:** E8.

### Q26. How do you handle loyalty points and paid memberships?

**Say:** “A loyalty benefit is only valuable if the shopper can use it. Our deterministic valuation withholds recognized eligibility conditions until they are attested and limits credit under the shopper's policy. A production integration must establish membership and model fees, expiry, redemption thresholds and exclusions.”

Do not convert points to cash without a justified redemption rule. Do not treat a paid membership as free or spread its fee across future purchases that the shopper may never make. Current roster lookup is a demonstration, not proof of account ownership. **Evidence:** E5, E9.

### Q27. How do you separate real extra benefits from Australian consumer rights?

**Say:** “We should represent the actual added service, such as a change-of-mind return option or specific extra support, separately from rights the shopper already has. Consumer guarantees can apply after a manufacturer's warranty expires. We should not describe all statutory protection as a fixed 12 months or sell it back as a special perk.”

The current rank prompt contains a problematic “statutory 12” example. It is a source-review finding, not a defensible product claim. **Evidence:** E11, S4.

### Q28. What does the market-size number in the README prove?

**Say:** “It is an illustrative exposure calculation based on assumptions, not our total addressable market or forecast revenue. For example, 100,000 members × $400 spend × 37% equals $14.8 million, but that is not evidence that this amount will be lost or that BondLayer can recover it.”

For a business case, independently verify the underlying survey, identify reachable retailers, estimate adoption and pricing, and validate the problem in interviews. Do not multiply an illustrative risk figure into a revenue forecast.

## C. Technical audience without commerce specialization

### Q29. Walk me through the architecture.

**Say:** “There are two Python/FastAPI applications. The merchant service runs the catalogue, policy and protocol APIs and serves a statically exported Next.js console. The buyer demonstration discovers merchants, queries their catalogue, verifies records, applies matching and comparison, then calls checkout. Shared contracts and deterministic components live in the `bondlayer` package.”

```text
Merchant CSV → adapter → diagnostics → published catalogue
Merchant policy → AI draft → human review → signature → published benefits
                                     ↓
                          Merchant commerce API
                                     ↕
Shopper → buyer client → decode → fetch → verify/match → rank → confirmation
```

In current live mode, model ranking happens after the shared comparison step. **Evidence:** E1–E7.

### Q30. Where is AI actually used?

**Say:** “OpenAI is used to decode shopping language, extract policy drafts and answer merchant questions grounded in the report. The current live buyer also uses a model to rank known eligible offers and route conversation. CSV validation, signature verification and monetary calculations are ordinary code.”

Response IDs and usage metadata provide evidence of a call, not evidence that the model's interpretation was correct. **Evidence:** E3, E6.

### Q31. Is the final ranking deterministic?

**Say:** “It depends on the selected mode. The reference comparison sorts by effective cost, then shelf price. The current live buyer calls `rank_offers` and uses `apply_ranking` to reorder known offers; checkout follows that winner. Therefore live rankings may vary even while the arithmetic and signatures remain deterministic.”

This is one of the most important updates from the earlier pitch. Never cite reference-mode reproducibility as proof of live-model reproducibility. **Evidence:** E5–E6.

### Q32. How is matching more than a keyword search?

**Say:** “Natural-language decoding maps the request into hard requirements, soft preferences, service requirements and values preferences. The resolver checks typed attributes and relevant records. Product-name matching also uses normalized lexical tokens and TF-IDF cosine similarity.”

The catalogue `q` route itself is shallow substring search. The reviewed implementation does not use a learned embedding model or a production vector database. **Evidence:** E1, E6.

### Q33. How do you prevent hallucinations?

**Say:** “We constrain structured outputs, tie intent clauses to source text, restrict policy identities to known catalogue values, preserve source passages and require approval. The downstream checks operate on actual products and signatures. Those reduce specific failure modes; they do not prove that a model never misinterprets text or invents reasoning.”

For example, a valid quote can be paired with an incorrect numeric interpretation. Human review and evaluation remain necessary. **Evidence:** E3, E6, E11.

### Q34. What happens when a requirement cannot be answered?

**Say:** “The resolver records missing evidence and unsatisfied requirements rather than inventing a policy. Recognized hard constraints filter products in the live path. Service and values clauses can remain unsatisfied on a returned proposal, so we must show the per-offer justification.”

A reported unmet preference is not automatically a global prohibition on recommending the offer. Unsupported hard-clause mappings also need careful handling; do not promise an arbitrary-constraint solver. **Evidence:** E1, E6.

### Q35. Why use digital signatures rather than just HTTPS?

**Say:** “HTTPS protects a connection. An object signature lets an agent retain a particular benefit record and recheck its contents after that connection ends. Both still need a trustworthy association between the merchant and the key.”

The code uses ES256: ECDSA with P-256 and SHA-256, over a stable JSON representation. It is not a blockchain. **Evidence:** E4.

### Q36. What data is signed?

**Say:** “The benefit's identifier, product binding, type, facts, conditions, issuer, timestamps, monetary ceiling and source span are canonicalized and signed. The signature is detached from the object. The verifier checks the key and issuer binding, timestamps and signature.”

That signature does not cover every catalogue product, the model's explanation or the complete order response. Do not describe the whole transaction as cryptographically signed. **Evidence:** E4, E7.

### Q37. How do you trust the public key?

**Say:** “The demonstration obtains public keys from merchant profiles and binds them to the expected issuer. Production still needs authenticated merchant onboarding and trustworthy domain-to-key distribution, plus rotation and revocation. Verifying bytes against a self-published key alone does not prove a real business identity.”

Private keys currently persist locally; they are not backed by a managed key service. **Evidence:** E4, E9.

### Q38. How does capability negotiation work?

**Say:** “The server intersects declared capability names, chooses a mutually supported version and removes extensions without a surviving parent capability. The response includes the active set. The same response builder serves basic products or adds the negotiated benefit extension.”

`org.bondlayer.benefit_value` carries benefits; `org.bondlayer.intent_match` enables merchant-side interpretation. The repository targets a dated UCP draft and has not demonstrated certification with all external clients. **Evidence:** E1.

### Q39. Why decode intent on both sides?

**Say:** “The merchant endpoint demonstrates that the merchant can receive a shopper sentence, interpret it and return justified proposals. The buyer retains independent comparison. In this demo, merchant proposals are shown alongside the buyer's result and do not set the final cross-merchant order.”

It is a useful boundary demonstration, but repeated decoding costs latency and calls. A production integration should decide which route adds value for its agent. **Evidence:** E6.

### Q40. What happens when OpenAI is unavailable?

**Say:** “Live-mode provider failures are surfaced as errors. They are not silently replaced with fake model answers. Explicit rules mode is available for the reference behavior; AI-only merchant assistance and extraction report that they require OpenAI.”

Already published catalogue data and deterministic verification do not require a model call. A live buyer comparison can still fail if its required decode or ranking call fails. **Evidence:** E3, E6.

### Q41. Where is state stored, and can it scale?

**Say:** “Published profiles and catalogue source are stored on disk and parsed products are served from process memory. Policy drafts use local storage including SQLite, signed benefits and keys persist locally, and comparison reports are local JSON. This is adequate for a local demonstration, not evidence of multi-instance production scale.”

Scaling needs shared authoritative storage, indexes, coordinated cache refresh, background ingestion, bounded model inputs and load measurements. Start with expected merchant count, products per merchant and request rate; do not promise a throughput number that was never measured. **Evidence:** E2–E4, E8.

### Q42. What tests have you actually run?

**Say:** “During this review, 79 focused merchant tests and 17 focused buyer tests passed. They covered signing, valuation invariants, onboarding persistence, policy publication, checkout, historical evaluation and live-mode wiring with stubbed model transport.”

These are targeted checks of the inspected working snapshot, not a full security audit, a load test or a live-provider accuracy evaluation. The exact commands are in the evidence notes. **Evidence:** E12.

### Q43. Is the model just wrapping a deterministic answer?

**Say:** “That described the earlier explanation-only buyer. The current live client can choose a different known offer and the checkout follows it; an integration test pins that behavior. The merchant service's contribution remains the structured, reviewed information and verification workflow that any suitable buyer can consume.”

The ranking payload still needs review: it uses citation summaries rather than the complete benefit facts, and those summaries can contain arithmetic. Avoid claiming complete information or perfect separation based only on prompt comments. **Evidence:** E6, E11.

### Q44. How do you handle prompt injection and access control?

**Say:** “The model instructions treat uploaded text as data, structured outputs restrict the shape, policy publication requires review, and known-offer checks reject invented offer identities. Those are limited controls. We have not proven resistance to adversarial text, and production merchant authentication and tenant authorization are not implemented.”

In particular, the current live ranker sees entries marked unverified and is instructed to ignore them; that is not the same as a deterministic guarantee that they cannot influence the model. **Evidence:** E6, E9, E11.

## D. Technical audience with commerce expertise

### Q45. Is a benefit record a fact, a price, an entitlement or a contract?

**Say:** “The record is a typed merchant assertion with scope, terms and evidence. A monetary ceiling supports an indicative comparison, and a signature supports attribution. Neither establishes shopper eligibility, actual price application or a complete enforceable contract by itself.”

Checkout rechecks cited records and acknowledges applicable ones, subject to terms. Entitlement enforcement and legal commitment need the real commerce integration. **Evidence:** E3–E7.

### Q46. How is shopper-specific value calculated?

**Say:** “For the deterministic comparison, a record must verify, bind to the merchant and product, have a valid ceiling and pass recognized eligibility checks. Credit is limited by the merchant ceiling and the shopper's remaining budget for that benefit type. Duplicate records are not counted again.”

```text
credit(record) = min(merchant ceiling, remaining shopper budget for that type)
                if the verification/applicability/eligibility gates pass;
                otherwise zero

ranking effective cost = shelf price - min(total credit, shelf price)
```

The floor is applied in composition. This formula explains the reference metric; it does not force the final live model ranking. **Evidence:** E5–E6.

### Q47. Can merchants buy rank by inflating ceilings or splitting records?

**Say:** “The reference calculation caps each benefit type by the shopper's own budget and deduplicates record identities. Splitting a benefit cannot exceed that type's budget. Raising a ceiling above the shopper cap cannot add further credit.”

**Important qualification:** Raising a ceiling that is below the cap can increase credit up to that cap. The broad statement ‘ceiling inflation can never change rank’ is mathematically false. Also, the live model's influence behavior needs separate tests. **Evidence:** E5, E11.

### Q48. Do you implement real promotion stacking and exclusions?

**Say:** “We have limited per-record eligibility checks and per-benefit-type budgets. We do not yet demonstrate a full promotion engine for mutually exclusive offers, best-deal selection, basket allocation, redemption limits or interactions between loyalty points and discounts.”

Per-type caps do not prevent every cross-type double count. Production should obtain authoritative applicable benefits from the merchant's promotion system and retain the explanation of exclusions. **Evidence:** E5.

### Q49. Can you prove the shopper is eligible for member benefits?

**Say:** “The recently added identity route looks up a supplied shopper ID in a merchant roster. That demonstrates merchant-specific status lookup, but it does not authenticate ownership of the ID. Real linking needs an authorized account flow and scoped claims.”

Do not describe this as complete OAuth identity linking. Checkout also needs to enforce the same entitlements; a lookup existing elsewhere is not sufficient. **Evidence:** E9.

### Q50. How are delivery thresholds, trade-ins and fees treated?

**Say:** “The schema can carry conditions, and recognized tokens can withhold deterministic credit. The prototype does not fully calculate destination-specific delivery, cart-level thresholds, trade-in inspection results or all membership costs. Those conditions must be resolved by authoritative services before claiming an applicable payable offer.”

Free-text terms are retained, but retaining text is not equivalent to executing its conditions. **Evidence:** E3, E5, E7.

### Q51. Can you compare total landed cost accurately?

**Say:** “Not yet as a complete commerce total. The prototype operates in AUD and the checkout subtotal is quantity times shelf price. It does not demonstrate a full destination, tax, shipping, duties or currency-conversion calculation.”

For an Australian merchant, establish whether imported prices already include GST and how delivery is treated. Do not call the displayed subtotal a universally complete amount payable. **Evidence:** E2, E7.

### Q52. What happens if price or policy changes between comparison and checkout?

**Say:** “Checkout reads current product data and rechecks the cited records. It can reject missing or invalid records. However, it is not a versioned quote-acceptance protocol and does not require the buyer's previously observed price or catalogue version to match.”

A production flow needs explicit quote versions or validity windows, repricing and buyer acceptance rules, plus durable records of the agreed transaction. **Evidence:** E7.

### Q53. Is the order ID an idempotency key or proof of purchase?

**Say:** “It is a deterministic content-derived identifier, not a payment receipt or durable order ledger. The implementation hashes merchant ID, items and honoured record IDs, then uses the first 16 hexadecimal characters. It does not bind the order price or the full record contents.”

The same identifier does not by itself stop duplicate processing. Production needs transactional idempotency, persistent order state and payment-provider coordination. **Evidence:** E7.

### Q54. Do you reserve stock or handle concurrent checkouts?

**Say:** “The route checks a published stock quantity when present, but does not reserve or decrement inventory. Two clients can therefore both receive confirmations against the same snapshot. That must be handled by a real inventory and order service before payment.”

Unknown stock is currently not treated as a reservation failure. Explain that behavior honestly rather than presenting confirmation as guaranteed fulfilment. **Evidence:** E7.

### Q55. Is bundling a real compatibility engine, and does checkout buy the bundle?

**Say:** “The bundler composes already-matched items using category and role recipes within one merchant, checks supported combined-budget logic and explains the set. It is not a complete compatibility graph for every connector, power requirement or accessory.”

The buyer close-loop path selects one unit of the winning SKU. Displaying a bundle does not prove an atomic multi-item purchase. In live mode, bundles are also composed before model reordering, so do not assume the displayed bundle belongs to the final model winner. **Evidence:** E6–E7.

### Q56. What exactly does the evaluation establish?

**Say:** “It evaluates 30 frozen synthetic requests against a synthetic catalogue. Each request is parsed once and resolved twice, with verified records available or absent. The headline is 15 of 18 service-and-values clauses answerable with records versus none for that control; all 154 cited records verified.”

It measures a rules-based setup, not current live-model ranking quality, causal sales uplift, cross-platform interoperability or field reliability. The report also states misses and a bundle gold-set gap. **Evidence:** E10.

### Q57. Is the 0% control a straw man?

**Say:** “It is an ablation: it isolates what happens when this catalogue's benefit records are removed. It is not a claim that the best existing shopping systems cannot obtain policy information elsewhere. Stronger evaluation should compare against enriched standard feeds and policy retrieval as well.”

The live two-pane UI is not that same controlled experiment: each pane can run independent model calls, and enabling the extension also enables merchant interpretation. For causal attribution, hold the decoded intent, shopper assumptions, catalogue snapshot and model settings constant. **Evidence:** E6, E10.

### Q58. What does the merchant learn about the shopper and competitors?

**Say:** “The normal catalogue request contains filters such as category and budget. Optional intent matching sends the shopper's sentence, and optional identity lookup sends an identifier. Valuation weights are not explicit fields in the normal merchant UCP request, but the sentence itself may disclose sensitive preferences.”

The local demo also stores cross-merchant comparison reports and provides console access without production tenant authorization. Therefore ‘the merchant never sees the comparison’ is too broad for the complete demo deployment. Real feedback sharing needs deliberate scoping and access control. **Evidence:** E6, E8–E9.

### Q59. Can signed sustainability claims prevent greenwashing?

**Say:** “They make a particular claim attributable and tamper-evident. They do not establish that its sustainability assertion is correct. A credible production system would need evidence scope, issuer identity, independent certification where relevant, freshness and a dispute or revocation process.”

Values claims remain unpriced in the reviewed policy workflow. A verified record can support a preference without pretending there is an objective dollar exchange rate for ethics. **Evidence:** E3–E5.

### Q60. What would a convincing pilot and next evaluation look like?

**Say:** “Start with one retailer, a limited category and real catalogue and policy documents. Measure how much staff correction is needed, which requirements are correctly answered and how stale or ambiguous information is handled. Test the output with an independently implemented agent before making commercial claims.”

Proposed acceptance measures:

- Time to publish a usable catalogue and approved policies.
- Fact extraction accuracy, omitted-exception rate and reviewer edits.
- Constraint satisfaction and evidence relevance per returned offer.
- Unsupported-claim rate under adversarial policies and queries.
- Latency, request cost, timeout rate and operational recovery.
- Successful quote/checkout reconciliation after integrating real commerce services.
- Paid-order contribution, returns and repeat behavior only once observable in a suitable controlled study.

Agree thresholds with the partner before collecting results. Expand categories and investment only after those measures support it.

## Questions to ask yourselves before taking the stage

1. Can each person identify one observed limitation in their own component?
2. Can you show the exact source record behind a service claim?
3. Can you explain why a signed claim might still be false?
4. Can you say which mode produced every number on the slide?
5. Can you demonstrate an unanswered request without treating it as a failure to hide?
6. Can you identify which screen reports a selection and which reports payment status?
7. Can you justify the proposed first customer without inventing interview evidence?
8. Can you explain the next integration step in business language?

The objective is not to memorize every sentence. Learn the boundaries well enough to answer a new question with the same accuracy.

## Small glossary for teammates new to commerce or engineering

| Term | Plain meaning |
|---|---|
| Catalogue | The merchant's list of products and their attributes. |
| SKU | A merchant's product/listing identifier; it is not necessarily unique across stores. |
| GTIN | A standardized trade-item identifier, often represented by a barcode. |
| Offer | A particular seller's product, price and applicable commercial terms. |
| API | A defined interface through which software requests information or actions. |
| UCP | Universal Commerce Protocol; BondLayer targets a dated draft and adds vendor capabilities. |
| PIM | Product information management: the system maintaining product descriptions and attributes. |
| ERP | Enterprise resource planning: business systems that may hold stock, pricing or financial data. |
| OMS | Order management system: tracks orders through their lifecycle. |
| Eligibility | Whether this shopper, product and basket qualify for a benefit. |
| Promotion stacking | Rules for which discounts and benefits may be combined. |
| Attribution | Knowing which issuer made a statement; in marketing, the word can instead mean allocating credit for a sale. Say which meaning you intend. |
| Entitlement | A benefit the customer is actually authorized to receive. |
| Idempotency | Repeating the same request does not perform the business action twice. |
| Ablation | A test that removes one input/component to study its contribution. |
| Shadow mode | Run the proposed system alongside operations without using its decisions to execute purchases. |
| Contribution margin | Sales less the relevant variable costs; define the included costs before calculating ROI. |
