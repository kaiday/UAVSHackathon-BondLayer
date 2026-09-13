# BONDLAYER — MASTER PROJECT HANDOVER
### UAVS Hackathon 2026 · FPT Australasia challenge "The B2A Shift" · Team of Ford Phan (leader), Manh, Bach, Chan, Hieu

**How to use this file:** paste it into a new Claude conversation/project as the single source of context. It contains everything developed to date: the product definition, the full canonical Round 1 proposal text, the evidence base with verification status, all key decisions and why they were made, the Round 2 build plan, judge Q&A prep, an inventory of every artefact produced, and the open task list. Where a section says VERBATIM, treat the text as final and do not rewrite it. If you also have the files, attach: `BondLayer_Round1_FINAL.pdf/.docx` (submitted proposal), `BondLayer_Round1_Pitch.html` (HTML mirror), `BondLayer_Team_Deck.html` (internal briefing deck — NOTE: older design, see §10), `HANDOVER_LaTeX_Prompt.md` (LaTeX typesetting brief).

---

## 1. Project snapshot

- **Product:** **BondLayer** — a merchant-side layer that makes a retailer's loyalty and service value **legible, verifiable and comparable** to AI shopping agents, built as a vendor extension to the open Universal Commerce Protocol (UCP).
- **Competition:** UAVS Hackathon 2026 (UAVS-NSW). Challenge chosen: FPT Australasia — "The B2A Shift: Adapting Retail for AI Shopping Agents" (merchant side only; do NOT build the shopping agent — simulating one is allowed).
- **Status by date:** Round 1 proposal deadline was **23:59 Fri 05/09/2026 AEST** (7-page PDF — finalized version produced; assumed submitted). **Round 2 is a 16-hour hackathon in Sydney, 12–13 Sep 2026. No code may be written before 09:00 on 12/09.** Specs, declared synthetic datasets, demo scripts and task splits MAY be prepared beforehand.
- **Team & roles:** Ford Phan (leader — product, valuation model, pitch) · Manh (SW — merchant service, protocol, signing) · Bach (SW — agent library, UI, demo) · Chan (market research, data, evidence) · Hieu (AI — intent extraction, matching, explanation).
- **Team name: STILL UNDECIDED.** Many suggestions rejected (Gold Tier, Covalent, The Receipts, Race to the Bottom, No Adjectives, Zero Trust, Sidecar, Bên Bán…). The registration/team-info block needs one.

## 2. Competition rules that bind everything

**Round 1 (done):** PDF only, max 7 content pages, 11–12pt, ≥2cm margins, English; sources EXCLUDED from the page limit. Required: chosen problem statement + reason, problem framing + research, assumptions & open questions (standalone section), proposed solution (AI/ML approach), overview design (architecture diagram), roadmap, and a team block with full names, university, contact email, **team leader's phone** — missing team info = disqualification. Rubric: Problem framing 30 · Feasibility 25 · Creativity 15 · Practical impact 20 · Documentation 10.

**Round 2 (12–13 Sep):** 16 hours, all code written on the day. Scoring (from rulebook, used in our plan): UX 20 · technical 25 · deployability 20 · market 25 · adaptation 10. Round 3 Q&A carries 25 points — rehearse the flip-card answers (§9).

**Workshop steer (22/08, from the FPT Problem Setter — cite as UAVS-NSW 2026):** the judging core is **intent accuracy + semantic matching** (interpret nuanced multi-constraint requests, not keyword matching); algorithm over UI (a simple API/basic interface suffices); no official dataset — state your own synthetic catalogue as an assumption (FPT may share a mock catalogue; don't limit yourself to it); merchant side only; ambiguous/contradictory intent → return a best-understanding recommendation, never hard-fail; closest real-world example given was B2B vendor sourcing; FPT wants a technical prototype, not a client-ready product.

## 3. The product — final design (this is the version of record)

**One-liner:** BondLayer makes a retailer's full offer *verified, valuable, complete, accessible and measurable* to AI shopping agents at the discovery-and-evaluation stage, riding UCP's own extension mechanism.

**Two features (team's framing — keep this language):**
- **Feature 1 — the plug:** one UCP integration, built from the catalogue export the merchandising team already produces, makes the retailer readable by any compliant agent.
- **Feature 2 — the pitch:** signed, typed **benefit records** (member pricing, points, return windows, warranty months, trade-in credit, delivery thresholds) attached to the catalogue response the agent already fetches. "Feature one gets you into the race, feature two helps you win it — and the console tells you why you lost."

**Seven components:** catalogue adapter (export → UCP objects) · policy converter with human approval gate (LLM drafts benefit records from policy documents; every draft quotes its source; nothing publishes itself) · benefit record schema & ontology (facts, conditions, issuer, expiry, optional declared value ceiling — "facts, not adjectives") · Ed25519 signing & key publication (unsigned records are displayed but NEVER valued) · UCP capability negotiation + benefit extension (graceful degradation for unaware agents) · optional open agent-side valuation library (verify signatures → deterministic effective cost under the SHOPPER's policy; merchant never sees the weights) · merchant visibility console (per agent request: fields exposed, share of offer legible, verified value credited, benefits withheld).

**Two enforced properties (tests, not assertions):** (1) inflating a declared figure cannot improve rank — value derives from published facts under the customer's policy; declared figures are only ceilings; (2) a larger unverified claim costs more — unsigned claims are never valued and are penalised in proportion to the claim.

**AI vs deterministic split (judge-critical):** AI = intent interpretation (schema-constrained), semantic catalogue matching (embeddings; exact model/GTIN fallback in MVP), policy conversion (with approval gate), explanation (generated ONLY from the computed table). Deterministic, never a model = signature verification, eligibility/expiry checks, effective-cost arithmetic, ranking. Rationale: Magentic Marketplace manipulation/bias evidence.

**Vertical:** consumer electronics retail (repeat purchases across phones/laptops/accessories/appliances/warranties; membership perks, trade-in credits, warranty bundles at stake). Target user: e-commerce and loyalty leads at mid-market retailers.

**What it is NOT:** not a consumer chatbot; not a new protocol (a UCP vendor extension); not GEO (proof, not persuasion); not lock-in (customer policy controls ranking). **The design contains NO retention/counter-offer engine** — that was deliberately dropped (see §7).

## 4. CANONICAL ROUND 1 PROPOSAL — VERBATIM

> Exactly 7 content pages + sources as built. Placeholders `[University]`, `[email]`, `[phone]` are deliberate. Page plan: p1 cover+§1 · p2 §2.1–2.2 · p3 callout+§2.3–2.4 · p4 §3 · p5 §4 · p6 §5 (figure + component table) · p7 §6 · p8 sources. Figures: Fig 1 = human-vs-agent journey strip (from team's original docx, 2048×430); Fig 2 = architecture diagram (generated, 1993×964); both live inside `BondLayer_Round1_FINAL.docx` (`word/media/`).

### Cover + §1 (page 1)

**BondLayer** — *The merchant-side layer that makes a retailer's loyalty and service value legible, verifiable and comparable to AI shopping agents*

**Challenge:** "The B2A Shift: Adapting Retail for AI Shopping Agents" — presented by FPT Australasia · UAVS Hackathon 2026, Round 1 Idea Proposal

Team table: Ford Phan (Team Leader) [University] [email]·[phone] Product, valuation model · Manh [University] [email] Software — merchant service · Bach [University] [email] Software — agent library, UI · Chan [University] [email] Market research · Hieu [University] [email] AI — intent, matching

**1. Chosen Problem Statement & Reason for Choice**

This proposal's chosen challenge is "How might product companies and retailers adapt to successfully market and sell to autonomous AI shopping agents rather than human consumers?" for three reasons:

- The B2A shift is an emerging, largely unsolved space rather than a domain with an established playbook, which gives our team more room to propose genuinely original ideas rather than an incremental fix.
- Every side of the market is moving toward this shift at once. On the technology side, Google and Shopify launched the open Universal Commerce Protocol (UCP) in January 2026, with expansion to Australia announced in May 2026 (Google 2026b). On the consumer behaviour side, 74% of consumers say they'd trust a personal AI agent more than their best friend to make a purchase (Accenture 2026). On the business readiness side, 44% of Australian businesses are already agentic-commerce "advocates," with 85% preparing for it (Australia Post 2026).
- The challenge owner is a natural first deployer. FPT Australasia serves Australian and New Zealand retail clients, and FPT launched an agent-native commerce platform with InFlow and Visa Intelligent Commerce in May 2026 — so a merchant-side agentic-commerce layer has an obvious owner and route to market (FPT Software 2026; Business Wire 2026).

This alignment of technology, consumer trust, retailer readiness and challenge-owner capability makes it a live gap worth designing against now.

### §2 Problem Framing & Research (pages 2–3)

**2.1 Industry Context**

With growing consumer trust in AI agents making purchase decisions, agents are starting to rewrite the rules of brand value, and specifically, they are **changing the loyalty equation**. DEPT describes this as the shift from B2C to B2A: where human marketing rewards emotion and creativity, AI intermediaries reward structured, consistent and verifiable information (DEPT 2026).

- 56% of consumers would instruct their AI agent on which brands to consider, showing that brand preference remains intentional (Accenture 2026).
- 37% of behaviorally loyal consumers say they would still let their agent switch them to a different brand if it found a better fit (Accenture 2026).
- 70% of consumers would use AI agents to optimize loyalty points (Salesforce 2025).

Consumer purchase journey (Accenture 2026) can be mapped against the agentic commerce journey (Universal Commerce Protocol 2026). The touchpoint that matters is "Discovery and evaluation", where an agent ranks merchants before a purchase decision is locked in.

[FIGURE 1 — journey strip] *Figure 1 — The human purchase journey mapped against the agent journey; the decisive stage is discovery and evaluation.*

Current loyalty programs were built for human psychology: habit, emotional attachment, and cumulative perceived value earned over time. An AI agent has none of that context. It evaluates every purchase from zero, using only what it can read and verify at the moment of the transaction. Three findings define this gap:

- *Loyalty value is transported but not valued.* UCP's Loyalty Extension lets loyalty data be passed to an agent, but does not define how the agent should weigh it against price or other criteria when generating an offer (Universal Commerce Protocol 2026).
- *Agent ranking rewards speed, not fit.* Microsoft Research's Magentic Marketplace found severe first-proposal bias in every frontier model and vulnerability to unverified claims; it recommends signed credentials (Bansal et al. 2025).
- *Legibility determines visibility, not affection.* Accenture notes agents parse structured attributes, cross-check verified claims and score fulfilment records in milliseconds, with no emotional loyalty bias built in. A brand that has not made its loyalty value machine-readable stays invisible to the agent, no matter how much the human customer values it (Accenture 2026).

**2.2 Target Users & Specific Pain Points**

This is a direct signal for **e-commerce and loyalty leads at mid-market retailers** who have already built a loyal customer base, and whose value proposition depends on repeat purchases rather than one-off transactions.

The chosen segment is consumer electronics retail, since customers return repeatedly across multiple purchase categories — phones, laptops, accessories, appliances, warranties — over a long relationship, not a single transaction. That makes electronics retailers the segment with the most to lose if an agent starts making that repeat-purchase decision on price alone, bypassing the membership perks, trade-in credits, and warranty bundles the retailer built to keep the customer coming back. This is our target user: not retailers chasing new customers, but ones with existing loyalty programs now exposed to a decision-maker their programs were not designed to persuade.

> **Problem statement.** In today's agentic commerce infrastructure, a customer's loyalty value is unverifiable, and locked in unstructured text that an agent cannot read or weigh against price. As a result, e-commerce leads at mid-market consumer electronics retailers have no visibility into how their loyalty investment is represented (or ignored) in agent-generated comparisons, and no way to have that value verified and credited at the moment an agent's recommendation puts a loyal customer up for grabs.

**2.3 Existing Solutions / Comparable Products**

The protocol layer already touches this space at two points, and their limits define the gap. During discovery, UCP's draft Loyalty Extension can transport a member's program data, but it models tier benefits as display-ready, human-readable text and defines no way to weigh them (Universal Commerce Protocol 2026). After the merchant is chosen, UCP Identity Linking uses OAuth 2.0 to authenticate which user an agent is acting for, so that checkout honours the pricing or shipping benefits that user already earned (Google 2026a) — it preserves value at transaction execution, after the decision this proposal cares about has been made. UCP's capability negotiation explicitly supports vendor extensions, so richer merchant-published data is an intended, standards-compliant mechanism rather than a workaround (Google 2026a). What no existing layer provides is examined next.

**2.4 Identified Opportunity**

Placing today's infrastructure on the journey exposes the gap this proposal targets: value is preserved after the choice, and transported — as text — during it. Five properties the target user in §2.2 needs remain unprovided:

- **Verification.** Loyalty and service claims travel as published data, not proof: nothing cryptographically binds a claim to the merchant that made it, so an agent must either trust the feed or discount it. Magentic Marketplace shows unverified claims are precisely the manipulation vector, and recommends signed credentials (Bansal et al. 2025).
- **Valuation.** Exposing "200 points and Gold tier" still leaves the weighing to the model's judgement. Nothing defines how benefits convert into effective cost under the shopper's own policy — deterministic, auditable arithmetic an agent (or a sceptical judge) can re-run.
- **Completeness.** What the wire carries today is loyalty-program mechanics. For an electronics retailer, much of the retention value identified in §2.2 is service, not incentive: warranty months, trade-in credit, return windows, repairs. Those policy facts are not modelled anywhere an agent can read them.
- **Accessibility.** Every current on-ramp assumes a platform integration. A mid-market retailer whose loyalty rules live in policy documents and whose catalogue is a merchandising export has no path that does not begin with re-platforming.
- **Measurability.** Nothing answers the e-commerce lead's operational question: per agent request, how much of my real offer was legible, how much value could the agent actually credit, and what was withheld by the wire?

The identified opportunity is therefore a merchant-side layer that makes a retailer's full offer **verified, valuable, complete, accessible and measurable** to agents at the discovery-and-evaluation stage — riding UCP's own extension mechanism rather than competing with it. This is the layer Sections 4 and 5 specify, and it is aligned with the Problem Setter's stated evaluation core — interpreting nuanced multi-constraint intent and matching it semantically — because a benefit record only wins the comparison after the right product has been matched (UAVS-NSW 2026).

### §3 Assumptions & Open Questions (page 4)

**3.1 Key Assumptions**

- **A1 — Catalogue data.** No official dataset exists, so we author a synthetic consumer-electronics catalogue (60–100 SKUs across phones, laptops, accessories, appliances and warranty add-ons) from public product pages, with realistic attribute noise and near-duplicate items to stress semantic matching. Basis: the Problem Setter confirmed there is no official dataset, may share a mock catalogue, and advised teams not to limit themselves to it (UAVS-NSW 2026).
- **A2 — Simulated agent.** The shopping agent is a stand-in: a language model given a neutral system prompt to behave as a UCP-capable agent, with no knowledge of our system. Basis: teams build the merchant side only (UAVS-NSW 2026). Enforced as a test: the simulated agent must treat all merchants identically except for the data they expose.
- **A3 — Extension adoption.** At least some agent platforms will negotiate vendor extensions; where they do not, our records degrade to standard UCP fields and unvalued display text. Basis: UCP capability negotiation is designed for extensions (Google 2026a; Universal Commerce Protocol 2026). This remains our largest commercial assumption.
- **A4 — Merchant data access.** Target retailers can produce a catalogue export and their policy, loyalty and warranty documents without re-platforming, and those rules can be expressed as typed facts with conditions and a bounded monetary ceiling.
- **A5 — The approval gate is staffed.** Retailers will review model-drafted benefit records before publication within their existing merchandising workflow; nothing publishes itself.
- **A6 — Bounded value is acceptable.** A benefit's worth cannot be perfectly priced. Bounded values applied under the shopper's policy, with unsigned claims never valued and penalised, are an acceptable approximation — the status quo values these benefits at zero.
- **A7 — Privacy.** Round 2 uses synthetic member profiles only; no real customer or FPT client data is used anywhere in the prototype.

**3.2 Open Questions**

**About the organisation.** Which client profile should this fit — enterprise retail or mid-market — and is FPT's digital-commerce practice planning UCP/ACP integrations that a merchant-side layer like this could ship inside? The closest real example given at the workshop was B2B vendor sourcing (UAVS-NSW 2026): should we prioritise consumer shopping agents, B2B procurement agents, or design the benefit schema to serve both? Will FPT provide the mock catalogue mentioned at the workshop, and in which vertical — and would FPT prefer the extension proposed upstream to UCP as an open contribution, or kept as a proprietary accelerator?

**About users.** For mid-market electronics retailers, what share of retention value is service-based (warranty, trade-in, repairs, returns) versus points — and do those rules live in documents our policy converter can realistically read? Will shoppers set a valuation policy once (which benefits count, tolerated premium), and what defaults are safe when they do not?

**About implementation.** How will intent-matching accuracy — the stated evaluation core — be measured: does FPT hold a benchmark set of multi-constraint requests, or should teams author and publish their own test set with the prototype? For ambiguous or contradictory intent the system will return its best-understanding recommendation, as advised (UAVS-NSW 2026) — should it also surface one clarifying question when confidence is low? What security and privacy baseline is expected at prototype stage versus a client pilot (key management, data residency, audit)?

### §4 Proposed Solution (page 5)

**4.1 Solution Overview** — BondLayer is a merchant-side layer with two features. **Feature 1 — the plug:** one UCP integration, built from the catalogue export the merchandising team already produces, makes the retailer readable by any compliant shopping agent — instead of one bespoke integration per agent platform. **Feature 2 — the pitch:** signed, typed benefit records — member pricing, points, return windows, warranty months, trade-in credit, delivery thresholds — attached to the catalogue response the agent already fetches, so during discovery the agent sees the full offer rather than a name, a price and a photo. A visibility console reports, per agent request, what was seen and what was credited. Feature one gets the retailer into the race; feature two helps it win it; the console tells it why it lost.

**4.2 Core Value Proposition** — **For the merchant:** be visible to agents, be creditable for value beyond price, and know why you lose. **For the shopper:** benefits already earned finally count in the agent's comparison, weighed under the shopper's own policy — never the merchant's. **For the agent platform:** verifiable facts instead of scrapeable adjectives. Together these deliver the five properties identified in §2.4: verified, valuable, complete, accessible, measurable.

**4.3 AI / ML Approach** — The AI work sits exactly where language and ambiguity live, and nowhere near money. **(1) Multi-constraint intent interpretation:** a request like "beginner-friendly, under budget, durable, ethically sourced" is converted by a schema-constrained language model into structured requirements; ambiguous or contradictory intent yields the best-understanding interpretation with stated assumptions, never a hard failure (UAVS-NSW 2026). **(2) Semantic catalogue matching:** embedding similarity plus attribute filters match those requirements across inconsistent product data, so the same laptop is compared as the same laptop (exact model/identifier matching as the prototype fallback). **(3) Policy conversion with an approval gate:** a language model drafts typed benefit records from the retailer's human-written policy and warranty documents; every draft must quote its source text and is held for human approval — the work no rules engine can do, made safe by the gate. **(4) Explanation:** one model call writes the shopper-facing rationale, generated only from the computed comparison table. Everything value-bearing stays deterministic: signature verification, eligibility and expiry checks, effective-cost arithmetic and ranking are code, never a model — the design consequence of the manipulation and bias evidence in §2.1 (Bansal et al. 2025).

**4.4 How the Solution Addresses the Problem** — Each pain in §2.2 maps to a mechanism: loyalty value invisible to agents → benefit records published on the catalogue call the agent already makes; value unverifiable → Ed25519 signatures, with unsigned claims displayed but never valued; no merchant visibility → the console's four per-request figures. The prototype demonstration makes the difference concrete with a before-and-after: the same shopper request runs twice — once against a plain product feed, where our merchant sits mid-pack, and once through BondLayer, where the agent can verify returns, warranty and member value, recommends our merchant, and explains why in its own words. Same product, same price, different outcome.

**4.5 Key Features / Components** — Seven components, specified in §5.3: a catalogue adapter (export → UCP objects); the policy converter with its approval gate; the benefit record schema and ontology (facts, conditions, issuer, expiry, declared ceiling); Ed25519 signing and key publication; UCP capability negotiation with the benefit extension; an optional open agent-side valuation library for auditable arithmetic; and the merchant visibility console.

### §5 Overview Design (page 6)

**5.1 System Overview** — The system is a merchant-side layer that makes a retailer's loyalty and service value legible and verifiable to an AI agent at the moment the agent is comparing merchants. The retailer's existing catalogue export and policy documents are converted into structured, typed, signed benefit records, published as an extension to the UCP catalogue call the agent already makes during discovery and evaluation — so the data arrives before the merchant is chosen, the gap identified in Section 2. Nothing is installed on the agent side: standard UCP capability negotiation means an unaware agent keeps working unchanged, while a supporting agent receives richer, verifiable data.

**5.2 System Architecture Diagram** — [FIGURE 2] *Figure 2 — Architecture: existing files → gated conversion → signed records → UCP negotiation.* (Diagram zones: "What the retailer already has" [product export, policy/loyalty/warranty documents, loyalty table] → BondLayer merchant-side publishing layer [catalogue adapter; policy converter (LLM) + human approval gate; benefit records signed Ed25519; UCP server with catalog.search/lookup, identity_linking, benefit extension, capability negotiation; merchant visibility console] → Agent side, nothing of ours installed [shopping agent; optional valuation library; shopper]. Footnote on diagram: unsigned records are displayed but never valued; the agent's ranking policy is never visible to the merchant.)

**5.3 Key Components** — (two-column table; content = the seven components as written in §3 of this handover, table wording in the FINAL doc)

**5.4 User / System Flow** — One request runs end to end as follows. The shopper asks in natural language, naming no brand; the agent extracts intent, sets a valuation policy the merchant never sees, declares its capabilities, and receives each catalogue with signed benefit records where the extension is negotiated — or flagged as unverified where no key is published. It verifies signatures, values the facts under the shopper's policy, ranks on effective cost rather than list price, and recommends; at checkout, identity linking honours the credited benefits, while the console reports what the request exposed. Two properties are enforced as tests, not asserted: inflating a declared figure cannot improve rank (value derives from published facts under the customer's policy; the declared figure is only a ceiling), and a larger unverified claim costs more (unsigned claims are never valued, and are penalised in proportion to the claim).

### §6 Preliminary Implementation Direction (page 7)

**Phase 1 — Research & validation (now → 5 Sep 2026).** This proposal: the evidence base, comparator analysis, the Benefit Record Schema v0.1 as a written specification, the synthetic catalogue design and the demonstration script. Remaining before submission: verify each quoted statistic against its original source, and log the §3.2 questions with the Problem Setter. Exit: proposal submitted.

**Phase 2 — Prototype (Round 2, 12–13 Sep 2026, 16 hours).** All code is written on the day, as the rules require; only specifications, declared synthetic datasets and the demo script are prepared in advance. Scope: one FastAPI merchant service running three merchant profiles from JSON manifests; UCP-shaped catalog.search / catalog.lookup plus the benefit extension with capability negotiation; Ed25519 signing; a simulated shopping agent (neutral system prompt, no knowledge of our system); the deterministic effective-cost library; a lightweight shopper view and the merchant visibility console; SQLite storage. Excluded: real connectors, payments, containerisation. The demonstration is the before-and-after run described in §4.4, closed by a live tamper test in which an inflated, unsigned claim is ignored and penalised.

**Phase 3 — AI/ML hardening (post-hackathon).** Run the policy converter on the published terms of three to four Australian electronics retailers with the approval-gate interface; move product matching from exact identifiers to embedding-plus-attribute matching with a human-verified crosswalk; expand the intent schema from the Round 2 test set; add explanation-faithfulness checks (every claim in the rationale must exist in the computed table).

**Phase 4 — Testing & evaluation.** The two §5.4 properties become named property tests: inflation cannot improve rank, and larger unverified claims cost more. Because intent-matching accuracy is the stated judging core, we author and publish an evaluation set of 100+ multi-constraint requests with the repository, reporting match precision and per-request legibility share.

**Phase 5 — Deployment & scaling.** Pilot with one mid-market electronics retailer in shadow mode: a manifest built from its public terms, console metrics measured against a holdout; success is the share of the offer that becomes legible and credited, and repeat-purchase share retained versus a price-only baseline. Scaling direction: propose the benefit extension upstream to UCP as an open contribution, and package the layer as an accelerator inside FPT's retail delivery practice, with a second vertical to follow. Privacy and consumer-law review is flagged before any real member data is used; this proposal draws no legal conclusions.

### Sources (Harvard style, excluded from page limit)

Accenture 2026 (accenture.com/us-en/insights/consulting/talk-my-ai-agent) · Australia Post 2026 eCommerce Report (auspost.com.au/business/ecommerce/ecommerce-report) · Bansal et al. 2025, Magentic Marketplace, arXiv:2510.25779 (PREPRINT — always say "preprint", never "peer-reviewed") · Business Wire 2026, 21 May (businesswire.com/news/home/20260521235556/en/ — FPT AI Factory + InFlow + Visa Intelligent Commerce) · DEPT 2026, 27 May (deptagency.com/insight/from-b2c-to-b2a-how-ai-is-rewriting-the-rules-of-the-customer-journey/) · FPT Software 2026 (fptsoftware.com/fpt-australasia) · Google 2026a UCP updates (blog.google .../ucp-updates/) · Google 2026b Google Marketing Live retail (blog.google .../shopping-updates-google-marketing-live/) · Salesforce 2025 (salesforce.com/news/stories/consumers-ready-for-ai-agents-research/) · UAVS-NSW 2026 workshop notes (internal) · Universal Commerce Protocol 2026, Loyalty Extension draft (ucp.dev/draft/specification/common/extensions/loyalty/).

## 5. Evidence base beyond the proposal (for Q&A and the Round 2 pitch)

- **UCP timeline:** launched by Google + Shopify **11 Jan 2026** with Etsy, Wayfair, Target, Walmart; endorsed by Visa, Mastercard, Stripe, PayPal; open source. Identity-linking capability + updates published **7 Apr 2026**; draft **Loyalty Extension** appeared Apr 2026 — models tiers/benefits as human-readable display strings; **redeemable balances explicitly out of scope** (spec wording: not modelled by this loyalty extension); community Issue #384 proposes loyalty-provider offer discovery. **AU expansion announced May 2026** (Google Marketing Live; confirm exact wording on blog.google). Vendor extensions are explicitly supported via capability negotiation.
- **OpenAI retired ChatGPT Instant Checkout in Mar 2026** after weak conversion and inaccurate product data — data quality, not checkout, is the bottleneck; agents shape consideration more than checkout (CNBC coverage).
- **Magentic Marketplace (Bansal et al. 2025, arXiv:2510.25779, preprint):** severe first-proposal bias in every frontier model tested (speed advantage over quality); manipulation via fake authority and unverified claims shifted purchases; authors recommend cryptographically signed credentials and oversight for high-value transactions. This is the backbone of our verification + deterministic-valuation design.
- **Stats used with verification status:** Accenture 74% (trust agent more than best friend) / 56% (instruct agent on brands) / 37% (loyal but would let agent switch) — VERIFY exact wording at source before quoting live. Australia Post 44% advocates / 85% preparing — VERIFY page number in the 2026 PDF. Salesforce 70% (agents to optimise loyalty points, Apr 2025) and 24% (comfortable with agent purchasing) — verified on Salesforce's page earlier. A "~75% switched brands in past year" figure exists only via secondary coverage — DO NOT use unless the original is found.
- **Australia context (used in the internal deck):** A$82.6b online retail spend 2025 (+14%), 9.8m households buying online (Australia Post 2026); Everyday Rewards ~71% and Flybuys ~70% membership penetration (Finder, Mar 2026).
- **Talon.One UIP — REMOVED from the proposal but REQUIRED knowledge for Q&A (see §7):** Unified Incentives Protocol announced **28 Jan 2026** (Business Wire): exposes loyalty + promotion data (point balances, tier status, earn/redeem, discount scope/type/stacking) machine-readably via MCP and as UCP loyalty/discount extensions; live for Talon.One's ~300 enterprise customers; roadmap mentions ACP/other surfaces. What UIP does NOT do (our differentiation): no cryptographic verification/signing; no valuation semantics (weighing left to the model); incentives-only (no service facts like warranty/trade-in/returns); platform-coupled (Talon.One customers — no mid-market on-ramp from existing files); no per-request merchant visibility.

## 6. Registration-form answer (VERBATIM, 283 words, deliberately zero em dashes — Ford's rule for form answers)

**BondLayer** is a merchant-side layer that makes a retailer's loyalty and service value legible, verifiable and comparable to AI shopping agents.

As commerce shifts from B2C to B2A, shopping agents increasingly rank merchants and lock in purchase decisions before a human ever sees the options. Agents read structure, not sentiment. A retailer's real advantages, such as member pricing, points, free returns, warranty and trade-in credit, are locked in unstructured text an agent cannot read, weigh or verify. Loyal customers get put "up for grabs" on headline price alone.

BondLayer fixes this with two features. **The plug:** one integration with the open Universal Commerce Protocol (UCP), built from the catalogue export the retailer already produces, makes the merchant readable by any compliant agent. **The pitch:** an AI policy converter reads the retailer's human-written policy and warranty documents and drafts typed benefit records. Every draft quotes its source text and passes a human approval gate, then each record is signed with the merchant's key and served on the catalogue call agents already make during discovery.

Four factors make this unique. **Verified, not claimed:** Ed25519 signatures let agents prove who made each claim. Unsigned text is displayed but never valued, and inflating a claim cannot improve rank; we enforce these properties as tests. **Valued, not just transported:** an open library converts benefits into effective cost deterministically under the shopper's own policy. Money stays in auditable arithmetic, never model judgement. **Complete:** we carry service facts (warranty, returns, trade-in) that incentive-only feeds miss. **Measurable:** a visibility console shows merchants, per agent request, what was legible, credited and withheld. No one offers that visibility today. BondLayer extends UCP rather than competing with it: a breakthrough layer built on open rails.

## 7. Decision log (the WHY behind the current state — do not silently reverse these)

1. **Talon.One/UIP removed from the proposal entirely** (Ford's call: a hackathon idea should read as a breakthrough). §2.3 was reframed against the protocol layer only. Trade-off accepted knowingly: judges may ask about UIP — the answer is rehearsed, not written (see §9, Q2). Never reintroduce Talon into written materials without Ford's say-so.
2. **Retention/counter-offer engine dropped from the design.** Earlier internal drafts had a "Retention Decision Engine" (signed bounded counter-offers) and a TRV ledger demo with retention offers. The teammates' final §5 design is legibility + verification + valuation + visibility only. The §2.2 problem statement was accordingly softened from "no real-time mechanism to respond" to "no way to have that value verified and credited". The internal team deck still shows the OLD design (see §10).
3. **Vertical switched footwear → consumer electronics** (teammates' §2.2 decision; all new material must use electronics examples).
4. **Third reason added to §1** (FPT as natural first deployer) to hit the rubric line "follows the organisation's interest".
5. **Team's voice preserved:** "the plug / the pitch" framing and the before/after demo narrative are the team's own wording — keep them in all materials.
6. **Citation discipline:** Harvard style; Magentic is always a "preprint"; ranges + stated assumptions beat fake precision; anything unverifiable gets softened or dropped.
7. **Ford's form-answer style rule: NO em dashes** in registration/form text (applies to form answers specifically; the proposal itself uses em dashes).
8. **BondLayer casing:** capital B, capital L (teammates sometimes wrote "Bondlayer" — standardise to BondLayer).

## 8. Round 2 build plan (16 hours, 12–13 Sep — all code written on the day)

**Stack (locked):** FastAPI + Streamlit + SQLite + PyNaCl (Ed25519); exactly two LLM call types (intent extraction; explanation from computed table, with cached fallbacks + a faithfulness check that every number in the explanation exists in the table); GTIN/exact-model matching in MVP (embeddings = stretch). NO Docker, NO Postgres, NO JWT, NO Next.js. One FastAPI app serves 3 merchant profiles from JSON manifests; agent is a neutral-prompt LLM stand-in; checkout simulated as a status flag.

**Demo script (the 3-minute core):** (1) BEFORE — same multi-constraint request against plain feeds: our merchant sits mid-pack on price. (2) AFTER — through BondLayer: agent verifies signed returns/warranty/member value, effective cost flips the ranking, agent explains why in its own words. (3) TAMPER — a merchant inflates an unsigned "lifetime warranty" claim: it is ignored in valuation and penalised. (4) Console view: what each request exposed. Rehearse the fairness test line: the simulated agent treats all merchants identically except for the data they expose.

**Per-person 16h split (D1 = hours 1–8 "make it run", D2 = hours 9–16 "make it convincing"):**
- **Manh:** merchant service + 3 manifests + UCP-shaped endpoints (h1–5) → Ed25519 signing, expiry, nonce (h5–8) → benefit-extension negotiation hardening + tamper handling (h9–13) → README + one-command setup (h13–16).
- **Hieu:** intent extraction with schema output (h1–3) → deterministic effective-cost library (h3–7) → GTIN matching (h7–8) → explanation + faithfulness check (h9–12) → cached fallbacks + tests (h12–16).
- **Bach:** Streamlit request→offers view (h1–4) → effective-cost panel + policy controls (h4–8) → merchant visibility console (h9–12) → seeded loss reasons + demo rehearsal (h12–16).
- **Chan:** synthetic electronics catalogue (h1–4) → member data + competitor scan (h4–8) → console metrics screenshots + value model (h9–12) → risk/compliance slide (h12–16).
- **Ford:** demo script + JSON contract review (h1–3) → integration across streams (h3–8) → pitch deck (h9–12) → live-demo rehearsal + Q&A prep (h12–16).

**The single most important integration point:** the JSON contract between Manh's merchant service and Bach/Hieu's agent-side code. **Status: NOT YET WRITTEN.** It may be prepared before the hackathon as a spec document (not code). Starting point: benefit record = { benefit_type (from ontology: member_price | points_earn | free_returns | warranty | trade_in_credit | delivery), facts {…typed fields…}, conditions [testable predicates], issuer, issued_at, expires_at, declared_value_ceiling_aud (optional), signature (Ed25519 over canonical JSON), key_id }. Extension name used in the proposal: the benefit extension offered via UCP capability negotiation alongside catalog.search / catalog.lookup / identity_linking.

**Pre-hackathon prep allowed (specs/data only):** synthetic catalogue CSV (60–100 SKUs, near-duplicates, attribute noise), 3 merchant manifests (loyalty rules as typed facts), 20+ multi-constraint test requests, demo script, the JSON contract spec, Streamlit screen sketches.

## 9. Judge Q&A (Round 3 = 25 points) — 10 questions with rehearsed answers

Assignments: Ford 1 & 5 · Manh 3 & 8 · Bach 2 & 9 · Chan 7 & 10 · Hieu 4 & 6.

1. *Why would a customer let a merchant influence their agent?* It doesn't. The merchant supplies signed inputs; weights live in the customer's policy. Magentic shows unverified inputs are the manipulation vector — signing is protective, not promotional.
2. *Why isn't this just another loyalty API? / What about Talon.One's UIP?* UIP exposes incentives for brands already on Talon.One's platform; BondLayer verifies and values the full offer — including service facts like warranty and trade-in — starting from files any mid-market retailer already has. UCP transports; we verify, value, and measure.
3. *Why a protocol instead of existing standards?* We don't build one. We're a vendor extension of UCP's own capability negotiation — show /.well-known/ucp declaring the benefit extension.
4. *How do you value non-cash benefits?* Bounds, not point estimates: merchant declares a range + conditions; customer policy decides whether it counts; unverified claims are penalised; provisional flags mirror UCP. The alternative today is zero.
5. *Who controls the ranking?* The agent, via the open valuation library or its own logic over our fields. The merchant never sees the policy. (Live: move the policy control, watch the ranking flip.)
6. *How do you prevent discrimination or manipulation?* Signed records keyed to disclosed program status only; audit trail; the two enforced properties (inflation can't help; unverified costs more); privacy/consumer-law review flagged before real data — no legal conclusions claimed.
7. *How do you beat two-sided adoption?* Merchant-side value stands alone (UCP readiness + conversion + analytics); graceful degradation; one vertical; FPT's client base as route to market; propose the extension upstream to UCP. Named as our biggest assumption (A3).
8. *What can you build in 16 hours?* Three merchants from JSON manifests, a deterministic valuation core, two LLM calls with fallbacks, Streamlit, SQLite, real Ed25519 signing. No pre-written code; specs and synthetic data prepared as the rules allow.
9. *What proprietary advantage develops over time?* The benefit-schema library across programs, the policy-conversion capability, and the loss-reason dataset from the console — none of which the open protocol produces by itself.
10. *What measurable value for FPT and its clients?* Clients: share of offer legible/credited, repeat-purchase share retained vs a price-only baseline, discount efficiency (ranges + assumptions; pilot holdout produces the real number). FPT: a reusable accelerator inside its UCP onboarding/retail delivery practice.

## 10. Artefact inventory (what exists, and its state)

| Artefact | State | Notes |
|---|---|---|
| `BondLayer_Round1_FINAL.docx` / `.pdf` | **FINAL** — 7 content pages + sources | The submitted proposal. Both figures embedded (`word/media/`: 2048×430 journey; 1993×964 architecture). Placeholders [University]/[email]/[phone] must have been filled at submission. Zero Talon mentions (verified by grep). |
| `BondLayer_Round1_Pitch.html` (+ `_preview.pdf`) | **FINAL, aligned** | Single-file HTML mirror of the FINAL doc (8 fixed A4 pages, base64 figures, print toolbar). Content verbatim from the doc. |
| `HANDOVER_LaTeX_Prompt.md` | Ready | Self-contained Claude Code brief to re-typeset the FINAL doc in LaTeX (pdflatex + carlito, page plan, overflow playbook, verify loop). Needs the FINAL docx alongside for figure extraction. |
| `BondLayer_Team_Deck.html` | **OUTDATED CONTENT — needs realignment** | 17-slide interactive briefing deck (keyboard nav, N notes, F fullscreen; animated research bars; clickable 2026 timeline; live interactive ledger with policy sliders + retention-offer button + tamper toggle; clickable Agent Journey Map; step-through transaction flow; hover architecture with MVP toggle; per-person 16h Gantt; 10 flip-card judge questions). BUT its content predates the final doc: footwear examples, a "TRV/retention engine" design, and a retention-offer demo that is NO LONGER in the product. If reused, realign: electronics vertical; plug/pitch framing; five properties; seven components; remove the retention engine and retention-offer ledger button (keep sliders + tamper toggle — those match the final design); judge cards → the §9 answers above. |
| `Round_1_-_Idea_Registration_FORD.docx` | Superseded | Working doc with Ford's sections + amber [GUIDE] skeletons + red review appendix; superseded by FINAL. |
| Registration-form answer | Final | §6 above, verbatim. |
| Team deck's earlier drafts / plan MD | Superseded | Early strategy plan predates electronics switch + Talon removal. |
| JSON contract (merchant ↔ agent) | **Not yet written** | See §8 — top prep priority. |
| Intent-accuracy eval set (100+ requests) | Not yet written | Promised in §6 Phase 4 of the proposal. |

## 11. Outstanding tasks

1. **Team name** — still undecided; needed for team-info blocks and the Round 2 pitch title.
2. **Realign the team deck** to the final design (see inventory row) — or build the Round 2 pitch deck fresh on the day (Ford's h9–12 slot) using this handover's §3–§6 as content.
3. **Write the merchant↔agent JSON contract spec** (allowed pre-hackathon as a document).
4. **Prepare pre-hackathon assets:** synthetic electronics catalogue, 3 merchant manifests, 20+ multi-constraint test requests, demo script rehearsal.
5. **Verify remaining stats at source** if they'll be spoken in the pitch: Accenture 74/56/37 wording, Australia Post 44/85 page refs, Google AU-expansion wording.
6. **Rehearse Q&A** per §9 assignments — especially the UIP answer (Q2), since it was removed from the paper deliberately.

## 12. Working conventions with Ford

- Direct, fast-turnaround; deliverables as real files; verbatim preservation of teammates' writing unless fit requires trims (then minimal and flagged).
- Push back honestly when a call has downside (e.g., Talon removal → keep the Q&A answer ready) but execute the decision.
- No em dashes in form answers. BondLayer casing. Harvard citations. "Preprint" for Magentic. Ranges + assumptions over fake precision. Placeholders stay bracketed until Ford fills them.
