# Stage 1 — Making a traditional catalogue agent-ready

**Implementation spec. Written 12/09/2026, inside the competition window.**

Who implements what:

| Section | Owner | Branch |
|---|---|---|
| §4 Readiness audit · §5.1–5.3 ingest, identity, semantics | Nguyen | `feat/nguyen-ucp-head` |
| §5.4 policy import — envelope, records, conditions, provenance + approval gate | Hieu | `feat/hieu-interpreter` |
| §5.5–5.6 signing and publication | Bach | `feat/bach-records-signing` |
| §4 audit rendering · §7 the onboarding screen | Minh | `feat/minh-console` |
| Data, gold answers, acceptance | Nha | `feat/nha-eval-data` |

Everything codes against `src/bondlayer/types.py`. §9 lists the four additions
that module needs; **channel first, then `round2/dev`** — do not edit it on a
feature branch.

---

## 1. The one-sentence problem

> UCP gives an agent a price, a barcode, and a **hyperlink** to your returns policy.

Every fact that answers a SERVICE or VALUES constraint sits on the far side of
that hyperlink, in prose a machine cannot weigh. Stage 1 is the work of dragging
those facts back across it, into typed, signed, machine-readable records.

## 2. Why this is true — spec evidence, not assertion

Verified against ucp.dev on 12/09/2026. A judge can open these.

**The Product schema carries no service or policy fields.**

| Object | Fields |
|---|---|
| `Product` | `id`*, `title`*, `description`*, `price_range`*, `variants`* (required); `handle`, `url`, `categories`, `list_price_range`, `media`, `options`, `rating`, `tags`, `metadata` |
| `Variant` | `id`, `sku`, `barcodes`, `handle`, `title`, `description`, `url`, `categories`, `price`, `list_price`, `unit_price`, `availability`, `options`, `media`, `rating`, `tags`, `metadata`, `seller` |

**Policies are `Link` objects, not data.** The `catalog.search` response carries a
`policies` array, but a policy is:

```json
{ "type": "refund_policy", "url": "https://merchant.example/returns", "title": "Returns" }
```

Well-known `type` values include `privacy_policy`, `terms_of_service`,
`refund_policy`, `shipping_policy`, `faq`. **The return window, the restocking
fee, the warranty months and the repairability commitment are all behind that
URL, as prose.**

**And loyalty arrives too late.** `dev.uip.shopping.loyalty` extends
`dev.ucp.shopping.checkout`, not catalog — so UCP surfaces loyalty only after the
merchant has already been chosen (`bach-demo/docs/ucp-findings.md`, Finding 3).

Together: at the moment the agent decides, the protocol hands it a price, a
barcode and some links. That is the gap Stage 1 closes.

## 3. Target state — four properties

The customer's words, mapped to testable properties.

| Merchant asks for | Property | Means | Failure if missing |
|---|---|---|---|
| "Visible" | **Discoverable** | `/.well-known/ucp` profile declaring capabilities, extensions and `signing_keys[]` | Agent cannot find you. Onboarding is permissionless — no registration, no partnership |
| "Interactive" | **Queryable** | Live `catalog.search` / `catalog.lookup`, capability negotiation, fresh availability | A nightly CSV cannot answer "in stock near me today" |
| "Transparent" | **Resolvable** | Stable identity: GTIN, parent→variant graph, attributes with units | Agent cannot tell your product from another, or match yours across merchants |
| "Appealing" | **Creditable** | Service and values facts as typed, signed records | Structured-but-unsigned is still marketing. This is BondLayer |

The first three are table stakes any UCP merchant needs. **The fourth is ours** —
and it is the one the protocol does not supply.

## 4. The Agent-Readiness Audit — the onboarding moment

**Build the audit before the fix.** The merchant uploads the export they already
have; the system scores it and shows which SKUs are invisible to an agent and
why. Then it remediates. Re-score after publish shows the delta.

This is the "why you lost" console moved to *before* the loss, and it is what
makes onboarding demoable. "We normalised your CSV" is not a demo.

### Score: five dimensions, 0–100 each, reported separately

Never average them into one number — a merchant with perfect identity and no
policy data has a specific, fixable problem, and one blended score hides it.

| # | Dimension | Measure | Floor |
|---|---|---|---|
| 1 | **Identity** | % SKUs with a valid GTIN *and* a resolved variant parent | Below this, the SKU is excluded from matching entirely |
| 2 | **Attribute completeness** | % of category-required attributes present, with units | Category-specific; laptops need cpu/ram/storage/screen/weight |
| 3 | **Semantic density** | mean count of machine-parseable facts per description | Target ≥ 5 facts. "Premium quality backpack" = 0 |
| 4 | **Policy coverage** | of 6 service facts (returns window, return fees, return method, delivery threshold, warranty months, repairability), how many exist as typed records | Prose-only counts as 0 |
| 5 | **Verifiability** | % of published records carrying a valid ES256 signature | Unsigned records are displayed, never credited |

Report per SKU **and** in aggregate, and always name the worst offenders by SKU
id — a list of twelve broken SKUs is actionable; "attribute completeness 78%" is
not.

### The audit output is a `ReadinessReport`

```python
@dataclass(frozen=True)
class ReadinessReport:
    merchant_id: str
    generated_at: datetime
    sku_count: int
    scores: dict[str, float]          # dimension -> 0..100
    excluded_skus: list[tuple[str, str]]   # (sku_id, reason)
    missing_attributes: dict[str, list[str]]  # sku_id -> attribute names
    policy_facts_found: list[BenefitType]
    policy_facts_missing: list[BenefitType]
    unsigned_records: list[str]       # record_ids
```

## 5. The pipeline

```
merchant's existing files
        |
   [1] ingest        CSV / XML / JSON export, any shape
        |
   [2] normalise     units, currency, casing, booleans
        |
   [3] resolve       GTIN, variant parent, cross-merchant model key
        |
   [4] enrich        attributes with units; semantic density check
        |
   [5] extract       policy prose -> draft BenefitRecords  [LLM + approval gate]
        |
   [6] sign          ES256 over canonical JSON
        |
   [7] publish       /.well-known/ucp + catalog.search + catalog.lookup
        |
   re-score  ->  ReadinessReport, before vs after
```

### 5.1 Ingest — assume the file is hostile

Our own `data/catalog/electronics.csv` already carries deliberate noise; the real
thing is worse. Accept and repair, never reject:

| Seen in the wild | Rule |
|---|---|
| `$199.00`, `AUD 129.00`, `129`, `1,455` | Strip symbols and separators, parse to `Decimal`, currency to a separate field. **Never float.** |
| `485g`, `0.31kg`, `1.1 kg` | Normalise to one unit per attribute; store the unit in the attribute name (`weight_kg`) not the value |
| `20k mm H2O`, `10,000mm`, `waterproof - very high` | Numeric where parseable; unparseable prose goes to `unresolved` and costs semantic-density points. Do not guess |
| `"XS, S, M, L, XL"` vs `S/M/L/XL` vs `"S,M,L"` | Split to a list on any of `, / |` |
| Missing barcode | Flag for the Identity score. Do not invent one |
| `stock: 0` | Keep the SKU, mark unavailable. Deleting it makes the catalogue silently lie about range |

Every repair is logged as a `Remediation(sku_id, field, before, after, rule)`.
**The remediation log is a demo asset** — it is the literal answer to FPT's
framing question about what friction a machine meets on a human feed.

### 5.2 Resolve identity — the highest-value step

Three distinct jobs, often conflated:

1. **GTIN presence.** Missing GTIN → the SKU cannot be reliably matched to the
   same product elsewhere. Score it, report it, never fabricate it.
2. **Variant parent.** One parent record, N variant nodes, each with its own
   sku/price/availability. Three colours × two sizes is **one product with six
   variants**, never six products. Orphaned variants read to an agent as a
   data-quality failure.
3. **Cross-merchant model key.** Our `model_key` column: the thing that makes
   "the same laptop at three merchants" comparable. 148 SKUs across 62 model
   keys, 53 shared — that sharing is what gives ranking something to rank.

### 5.3 Enrich — semantic density is a measurable property

An embedding has nothing to bite on in *"Premium quality backpack"*. Target is
**five or more machine-parseable facts** per description: a quantity with a unit,
a named compatibility, a material, a capacity, a use case.

```
BAD   "Premium quality laptop, great for professionals."        facts: 0
GOOD  "14in business laptop, i5-1335U, 16GB RAM, 512GB SSD,
       1.4kg, 60Wh battery. Runs Figma and light 4K edit."      facts: 7
```

Implement `density(description) -> int` as a counter over: number+unit pairs,
model identifiers, named standards, and explicit use-case clauses. It is a
heuristic and should be labelled one — but it is measurable, repeatable, and it
moves a real score.

### 5.4 Import the policy — four outputs, not one

**Input:** the merchant's T&C, returns, delivery, warranty and loyalty prose
(`data/policies/*.md`).

The T&C is where the merchant states what it will honour, what it will refuse,
and under which conditions. It is tempting to read it only for the benefits.
That misses three quarters of what UCP needs from it:

| Output | What it is | Where it lands | Why UCP needs it |
|---|---|---|---|
| **A. Envelope** | The operational boundary — what an agent may do on the merchant's behalf | `/.well-known/ucp` (which capabilities to declare) + request-time filtering | Stops the agent proposing something the merchant will refuse at checkout — the exact failure the problem statement names |
| **B. Records** | The typed facts — returns, delivery, warranty, loyalty, repairability | `BenefitRecord` | The value that wins the comparison |
| **C. Conditions** | The predicates that gate each record — *when* it is true | `BenefitRecord.conditions` | A benefit that is false for this SKU or shopper is worse than none: it is a hallucinated claim carrying our signature |
| **D. Provenance** | Issuer identity, effective dates, canonical policy URLs | `issuer`, `issued_at` / `expires_at`, UCP `policies[]` Links | Ties every claim to a legal entity and a signing key; feeds UCP's own `refund_policy` / `shipping_policy` links |

"Boundary" is A and C. "Environment" is D. **Extract A first** — it decides
which capabilities the profile declares, and nothing else can be published until
that is known.

#### 5.4.A The envelope

What the T&C must answer before a single capability is declared:

| Question | T&C section, typically | Consequence |
|---|---|---|
| **Transactability** — may an agent *buy*, or only browse and quote? | Terms of sale, "orders placed by third parties" | Whether to declare `cart` / `checkout` or stop at `catalog.*`. We stop at catalog in 16 hours regardless — but the *decision* comes from the T&C, not from us, and the profile must say so |
| **Territory** — ship-to countries and states, currency, GST-inclusive pricing | Delivery, pricing | Filter before ranking, not reject at checkout. An NZ shopper against an AU-only merchant never sees the offer |
| **Eligibility** — age-restricted goods, business-only pricing, membership gating | Eligibility, account terms | Filter per SKU per shopper context |
| **Limits** — max quantity per order, max order value, one-per-customer promotions | Orders, promotions | Cap the `Bundle`; refuse over-limit proposals before they are made |
| **Identity requirements** — does member pricing require `identity_linking`? Does enrolment require explicit consent? | Loyalty terms, **privacy policy** | Declares `dev.ucp.common.identity_linking`; the privacy clause is the authority for the consent gate |
| **Payment and fulfilment methods** | Payment, delivery | What checkout will actually accept; out of scope to implement, in scope to declare |

```python
@dataclass(frozen=True)
class MerchantEnvelope:
    merchant_id: str
    agents_may_transact: bool
    ship_to_countries: list[str]        # ISO 3166-1 alpha-2
    ship_to_regions: list[str] | None   # states / postcode zones, None = all
    currency: str                       # ISO 4217
    prices_include_tax: bool
    age_restricted_categories: list[str]
    business_only: bool
    max_quantity_per_order: int | None
    max_order_value_aud: Decimal | None
    member_pricing_requires_identity: bool
    enrolment_requires_consent: bool
    payment_methods: list[str]
    source_spans: dict[str, str]        # field -> quoted sentence
```

Every field carries its source span, same as a record. An envelope field the
T&C does not answer is `None` and is reported as a gap in the Readiness Audit —
it is not defaulted to permissive.

#### 5.4.B The records

**Output:** draft `BenefitRecord`s awaiting approval. Six service facts, plus the
values claims:

| Fact | `BenefitType` | `fact` shape | Priced? |
|---|---|---|---|
| Return window | `FREE_RETURNS` | `{"days": 30, "fee_aud": 0}` | yes |
| Delivery threshold | `DELIVERY` | `{"free_over_aud": 100, "fee_aud": 12.95}` | yes |
| Warranty | `WARRANTY` | `{"months": 24, "basis": "voluntary"}` | yes — voluntary excess only, see 5.4.E |
| Member price | `MEMBER_PRICE` | `{"pct_off": 5, "tier": "gold"}` | yes |
| Points | `POINTS_EARN` | `{"per_aud": 1, "unit": "points"}` | yes |
| Trade-in | `TRADE_IN_CREDIT` | `{"max_aud": 300}` | yes |
| Repairability | `REPAIRABILITY` | `{"parts_years_after_eol": 5}` | **no — ceiling `None`** |
| Sustainability | `SUSTAINABILITY` | `{"ewaste_tonnes_fy2026": 412}` | **no** |

**Three hard rules.**

1. **Every draft quotes its source.** `source_span` carries the exact sentence
   the fact came from. A draft with no quotable span is rejected, not published.
2. **Nothing publishes itself.** Drafts sit in a review queue. The gate is a
   human clicking approve. This is the containment for a wrong extraction, and
   it is assumption A5.
3. **Compare the quote loosely, the fact strictly.** The spike's converter
   rejected all ten drafts because the document wrote `**$12.95**` and the model
   quoted `$12.95`. Normalise markdown, whitespace and currency formatting before
   comparing spans — the check is for fabrication, not formatting.

**Values claims are the cheap win.** `value_ceiling_aud = None` means validated
but never priced: it satisfies a VALUES constraint, gets cited in the
justification, and contributes exactly zero to effective cost. Signing is what
separates a verified repairability commitment from NorthGear's unsigned
*"Australia's most sustainable electronics retailer"*. Do not special-case them
anywhere in the signing or valuation path.

#### 5.4.C The conditions — the underspecified part

`BenefitRecord.conditions` is `list[str]` today. Free text is fine for display
and useless for enforcement. Policy prose is dense with **negations**:

> Free returns within 30 days, **except** clearance items, opened software and
> personalised products. Warranty **excludes** accidental damage and liquid
> ingress. Free delivery on orders over $100, **metro areas only**.

Language models are unreliable on negations. If these are not converted to
testable predicates, we sign a returns record that is false for a third of the
catalogue — and an agent that cites it at checkout discovers the lie, which is
worse for trust than never having published it.

```python
@dataclass(frozen=True)
class Condition:
    field: str        # "category" | "order_total_aud" | "postcode_zone"
                      # | "member_tier" | "item_condition" | "sku_id"
    op: str           # "eq" | "ne" | "in" | "not_in" | "gte" | "lte"
    value: str | int | float | list[str]
    source_span: str  # the sentence it came from
```

`conditions: list[Condition]`. The valuation library evaluates every condition
against the SKU and the shopper context **before** crediting. A record whose
conditions fail is displayed as *inapplicable* — never credited, never cited in
the justification.

**Extraction rule for Hieu:** run a separate negation pass. First ask the model
for the benefit; then ask it, explicitly, for every exclusion, exception, and
"only" clause attached to that benefit, as a list. Convert each to a `Condition`.
A record with a plausible exclusion in the prose and no `Condition` for it should
fail the approval queue's own check.

#### 5.4.D Provenance

Three things the T&C establishes that nothing else can:

- **Issuer.** The legal entity making the claim — trading name, ABN. This is
  `BenefitRecord.issuer` and it must be the same entity the signing key belongs
  to. A record issued by "CityCircuit Pty Ltd" signed with a key published by a
  different domain is a verification failure, not a formatting one.
- **Validity window.** Policy effective date → `issued_at`. Promotional or
  time-bound clauses → `expires_at`. A record with no expiry that describes a
  promotion is an extraction error.
- **Canonical URLs.** UCP's own `policies[]` array wants `Link` objects. The T&C
  import emits them directly — `refund_policy`, `shipping_policy`,
  `privacy_policy`, `terms_of_service` — so the prose stays reachable for an
  agent that wants to read it, alongside the typed records for one that wants to
  compute over it.

#### 5.4.E Australian Consumer Law — the floor is not a differentiator

In Australia the T&C sits **on top of** the Australian Consumer Law. Consumer
guarantees — acceptable quality, fitness for purpose, remedies for major failure
— cannot be excluded by any policy, and a merchant's "12-month warranty" is a
*voluntary warranty against defects* in addition to them, with mandatory wording
requirements.

Two consequences for extraction:

1. **The statutory floor is identical for every merchant and is not creditable.**
   Crediting it inflates everyone equally and proves nothing. A `WARRANTY`
   record carries `"basis": "voluntary"` and only the voluntary excess is valued.
   If the T&C merely restates ACL rights, no warranty record is drafted.
2. **A policy that purports to exclude ACL rights** ("no refunds on sale items")
   is drafted as a record with a `Condition`, and flagged in the approval queue —
   the merchant is publishing something it cannot lawfully enforce, and the
   approval gate is the place a human sees that.

This is what Round 2's *Deployability* criterion means by "legal compliance under
current regulations". One honest paragraph here earns points most technical teams
leave on the table. **Verify the specific regulation references before they are
spoken** — the principle is settled; the citation is not to be quoted from
memory.

### 5.5 Sign — the spec is prescriptive here, follow it exactly

Verified against the UCP signatures spec:

- **ES256 (P-256/SHA-256) is mandatory.** All implementations MUST verify it.
  ES384 optional. Do not reach for Ed25519 — the Round 1 proposal said Ed25519,
  the spec says ES256, and **the spec wins.** Say so in the pitch as an
  adaptation, not a correction.
- **Keys publish in `/.well-known/ucp` under `signing_keys[]`**, JWK format
  (RFC 7517): `kid`, `kty: "EC"`, curve, `x`, `y`, optional `use`/`alg`.
  `kid` resolves there; no match → fail `key_not_found`.
- **Transport signing is RFC 9421 HTTP Message Signatures**, over `@method`,
  `@authority`, `@path`, plus conditionally `@query`, `content-digest`,
  `content-type`, `ucp-agent`, `idempotency-key`. Responses sign `@status`.
- **Our record signing is object-level and separate.** A detached ES256
  signature over the record's canonical JSON, so the record survives the
  response that carried it and can be cached, re-verified and cited. Transport
  signatures do not do this.

> **Correction for Bach.** A widely-cited vendor blog claims `/.well-known/jwks.json`
> is the canonical trust source and the profile's `signing_keys[]` is merely
> informational. **The ucp.dev spec does not say that.** It publishes keys in the
> profile. Build against ucp.dev.

Canonical JSON: sort keys, no insignificant whitespace, integers for minor units,
UTF-8, no trailing newline. Serialiser and its round-trip test are Bach's, and
need no catalogue — they are the Phase 0 non-blocking task.

### 5.6 Publish

```
/.well-known/ucp        profile: capabilities, extensions, signing_keys[]
/ucp/catalog/search     dev.ucp.shopping.catalog.search
/ucp/catalog/lookup/{id} dev.ucp.shopping.catalog.lookup
```

Extension declaration, reverse-domain named, `extends` the catalog capabilities
because catalog is where the agent decides:

```json
{
  "org.bondlayer.benefit_value": [{
    "version": "2026-09-12",
    "extends": "dev.ucp.shopping.catalog.lookup",
    "spec": "https://bondlayer.example/spec/benefit_value",
    "schema": "https://bondlayer.example/schemas/benefit_value.json"
  }]
}
```

`dev.ucp.*` is reserved for the UCP Tech Council. Ours is `org.bondlayer.*`.
Negotiation is server-selects: intersect names, pick the highest mutual version,
prune extensions whose parent did not survive, repeat until stable. Echo the
active set in every response.

**This is what makes the before/after honest:** the "before" run is an agent that
simply does not declare `org.bondlayer.benefit_value`, so negotiation prunes it.
We never switch code paths to make the baseline lose — the protocol does it.

## 6. Also emit the legacy surface

UCP is the thesis, but most agents today read Google Merchant Center and
schema.org. Emitting both costs little and widens the claim from "works with UCP"
to "works with what agents actually read now":

- `MerchantReturnPolicy` — `merchantReturnDays`, `returnFees`, `returnMethod`,
  `refundType`, `applicableCountry`, `itemCondition`
- `ShippingDeliveryTime` — `handlingTime`, `transitTime`, each `minValue` /
  `maxValue` / `unitCode`

These are real, stable, verifiable schema.org types, and they are the closest
existing standard to what we are arguing for. Worth one slide: *the structured
baseline exists for returns and shipping; nothing equivalent exists for loyalty,
warranty value or repairability, and that is the hole we fill.*

## 7. The onboarding screen (Minh)

Three states, one screen:

1. **Before** — score bars across the five dimensions, red, with the worst SKUs
   named.
2. **Remediating** — the remediation log scrolling: every repair with before,
   after and the rule that fired. The approval queue for policy drafts, each
   showing its quoted source span.
3. **After** — the same five bars, plus what is now publishable and signed, and
   the delta.

Per the Problem Setter's note, logic outranks polish: the remediation log and the
approval queue matter more than the bars looking good.

## 8. Acceptance — Stage 1 is done when

1. A merchant export with deliberate noise ingests with **zero manual edits**,
   and every repair appears in the remediation log.
2. `ReadinessReport` scores all five dimensions before and after, naming
   excluded SKUs with reasons.
3. Every published `BenefitRecord` carries a `source_span` traceable to the
   prose, and passed a human approval click.
4. Every record verifies under ES256 against a key resolved from
   `/.well-known/ucp` `signing_keys[]`.
5. `catalog.search` returns benefit records **only** when the agent declares the
   extension, and the same call without it returns plain UCP.
6. One unsigned claim is present in the published data, is displayed, and is
   never credited or cited.
7. A values claim satisfies a VALUES constraint while contributing exactly
   `$0.00` to effective cost.
8. The `MerchantEnvelope` is extracted **before** the profile is published, and
   the profile declares only the capabilities the envelope permits. An envelope
   field the T&C does not answer is reported as a gap, never defaulted.
9. Every negation in the policy prose has a matching `Condition`; a record whose
   conditions fail for a given SKU is shown as inapplicable and contributes
   nothing.
10. A `WARRANTY` record is drafted only for the voluntary excess over the
    statutory floor.

## 9. Four additions `types.py` needs — channel first

`Sku` currently carries `sku_id`, `title`, `category`, `shelf_price`,
`attributes`. Stage 1 needs identity to be first-class, not buried in the
attributes dict:

```python
gtin: str | None          # None is a legitimate, scored state
model_key: str | None     # cross-merchant identity
variant_parent: str | None
availability: bool
```

Plus three new types:

- `ReadinessReport` from §4.
- `MerchantEnvelope` from §5.4.A.
- `Condition` from §5.4.C — and `BenefitRecord.conditions` changes from
  `list[str]` to `list[Condition]`. This is the one breaking change; Bach's
  serialiser and Hieu's converter both touch it, so it lands before either
  writes against the field.

**None of these are mine to commit** — post to the channel, land them on
`round2/dev` as their own commit, everyone rebases.

## 10. Sources and their standing

**Authoritative — quote these freely.**

- UCP core concepts, `/.well-known/ucp`, permissionless onboarding —
  <https://ucp.dev/documentation/core-concepts/>
- `catalog.search` request/response, the `policies` array —
  <https://ucp.dev/draft/specification/shopping/catalog/search/>
- Product and Variant schema, `Link` object and policy types —
  <http://ucp.dev/2026-04-08/specification/reference/>
- ES256 mandatory, RFC 9421, `signing_keys[]` —
  <https://ucp.dev/2026-04-08/specification/signatures/>
- Loyalty extends checkout, `dev.uip.shopping.loyalty` —
  `bach-demo/docs/ucp-findings.md` (our own, verified 30/08)
- `MerchantReturnPolicy` — <https://schema.org/MerchantReturnPolicy> and
  <https://developers.google.com/search/docs/appearance/structured-data/return-policy>

**Vendor and SEO blogs — directionally useful, NOT citable.**

Figures circulating in this literature include ~40% of a catalogue ignored for
lacking structured attributes, ~60% of catalogues missing GTINs or carrying stale
inventory, a 95% attribute fill-rate threshold, and 28% of AI shopping
conversations involving shipping-and-returns constraints. **Several of these
sources cite each other rather than a primary study.** Use them to shape the
build; do not put a number from them on a slide. If one is spoken, say "industry
estimates suggest, and we have not verified this" — the same discipline applied
to the Accenture and Australia Post figures in Round 1.

**The honest version of the claim.** Publishing structured, signed, priced
benefit data does not make a price-ranking agent change its mind. It lets an
agent *already* reasoning about total cost credit you for what you actually
offer, and denies that credit to competitors who publish nothing or publish it
unsigned.
