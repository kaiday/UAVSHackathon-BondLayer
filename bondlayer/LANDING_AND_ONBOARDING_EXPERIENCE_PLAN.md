# BondLayer Landing and Merchant Onboarding Experience Plan

## Purpose

Use the existing four-step onboarding mock-up as a product and content reference in two distinct experiences:

1. A public, pre-login landing page that shows prospective merchants what BondLayer can do.
2. An authenticated onboarding flow that collects the information needed to activate a merchant workspace.

The mock-up implementation in `bach-demo/app/web` is reference material only. Rebuild the experience in the current dashboard frontend and connect it to the existing production backend services.

## Audience and outcome

### Pre-login visitor

The visitor is evaluating whether BondLayer is useful for their business. The page should make the product outcome understandable before asking them to create an account or upload data.

**Desired outcome:** the visitor requests access, creates an account, or signs in to begin merchant setup.

### Authenticated merchant

The merchant has decided to use BondLayer and must provide accurate business, catalogue, policy, and membership information.

**Desired outcome:** the merchant submits a complete onboarding package for review or activation.

## Experience architecture

```text
Public landing page
  -> Explore the product outcome
  -> Start merchant setup or sign in
  -> Authenticated dashboard onboarding
  -> Review and submit
  -> Merchant dashboard
```

Keep the public page and the authenticated wizard visually related, but do not make the landing page feel like a compliance form. The landing page sells the value; onboarding gathers the required evidence.

## Public landing page

### Primary message

**Make your product catalogue and merchant policies legible to AI shopping agents.**

Supporting message: BondLayer turns existing catalogue exports and customer policies into structured, reviewable information so agents can discover products, understand fulfilment conditions, and represent merchant value accurately.

### Recommended page sections

| Section | Purpose | Content and interaction |
|---|---|---|
| Hero | Explain the value immediately | Headline, one-sentence explanation, **See how it works** and **Start merchant setup** calls to action. |
| Before and after | Make the information gap visible | A simple comparison: unstructured catalogue/policy text versus agent-ready product and policy information. |
| Four-step preview | Borrow the strongest part of the mock-up | Show a preview rail: Bring your files, Find what agents cannot read, Review clear claims, Publish with confidence. This is an explanation, not an actual upload flow. |
| What agents can understand | Demonstrate output | Example product card or catalogue row showing structured fields, availability, policy facts, and evidence status. |
| Merchant controls | Establish trust | Explain that the merchant reviews data, controls publishing, and accepts policies before anything is activated. |
| Product capabilities | Clarify scope | Catalogue upload, data quality checks, policy publishing, membership management, and agent-ready records. |
| Final CTA | Move visitors into the product | **Create merchant workspace**, **Sign in**, and optional **Request a demo**. |

### Landing-page interaction rules

- Do not ask visitors to upload business files before sign-in.
- Use illustrative sample data and clearly label it as an example.
- A visitor who selects **Start merchant setup** should go to sign-up/sign-in, then the authenticated onboarding wizard.
- A returning authenticated merchant should bypass the landing page and resume the correct onboarding step.
- Keep claims grounded: explain what the system structures, validates, or presents for review; do not promise automatic publication or guaranteed sales outcomes.

## Mapping mock-up ideas to the public landing page

| Mock-up concept | Landing-page adaptation |
|---|---|
| `Your files` | Explain that merchants can connect a catalogue export and business/policy information after creating a workspace. |
| `What agents cannot read` | Visualise the gap between human-readable pages and structured data agents can use. |
| `Your claims drafted` | Explain that policies can be made reviewable and clear; do not expose or promise automatic legal drafting. |
| `Approve and sign` | Explain merchant control, approval, policy acceptance, and auditability. |
| Progress rail | Use as a read-only four-step product tour. |

## Authenticated onboarding flow

Retain the existing dashboard onboarding structure. It is more complete than the mock-up because it includes operational and compliance requirements.

| Dashboard step | Goal | Mock-up relationship |
|---|---|---|
| Welcome | Explain setup time and what happens next | Reuse concise, confidence-building setup framing. |
| Business profile | Identify the merchant organisation | New requirement. |
| Business files | Upload registration and supporting files | Expands the mock-up's file-upload concept. |
| Data import | Upload and validate source data | Expands product-export upload with mapping and errors. |
| Catalogue | Import or manually add products | Turns input data into a merchant catalogue. |
| Merchant policies | Upload shipping, returns, privacy, and terms | Expands the mock-up's policy-page upload. |
| Membership policy | Accept current membership terms | Formalises the mock-up's approval/signing concept. |
| Review and submit | Resolve requirements and submit | Reuses the explicit final-approval pattern. |

## Content direction

Use the mock-up's plain, merchant-centred language:

- "Start with the files you already have."
- "See what agents can understand and what needs your review."
- "Nothing is published until you approve it."

Avoid language that implies the system can make legal, commercial, or policy decisions on the merchant's behalf.

## Implementation phases

### Phase 1 - Existing dashboard onboarding

- Keep `/onboarding` as the authenticated wizard.
- Connect file pickers, data imports, catalogue processing, and policy records to the existing backend services.
- Add first-visitor routing based on merchant onboarding status.

### Phase 2 - Public landing page

- Add a public route, such as `/` or `/merchant`.
- Build the hero, before/after example, four-step product tour, capability overview, trust content, and CTAs.
- Use static sample data only; no authenticated merchant data on the public page.

### Phase 3 - Conversion and lifecycle

- Connect **Start merchant setup** to sign-up/sign-in.
- Return authenticated visitors to their saved onboarding step.
- Track high-level conversion events: landing-page CTA, account creation, onboarding start, onboarding completion, and submission.

## Acceptance criteria

- A prospective merchant can understand the product value without signing in.
- The public product tour clearly distinguishes examples from uploaded merchant data.
- Public CTAs route users into sign-up/sign-in and then onboarding.
- Authenticated merchants can resume onboarding without returning to the public landing page.
- The public page and dashboard onboarding use consistent terminology, visual identity, and trust messaging.
- No code from the pre-work mock-up is copied into the production dashboard implementation.

## Decisions to resolve

- Should the public landing page be the root route, or should the root route remain a signed-in dashboard?
- Is merchant sign-up self-service, invite-only, or a demo-request workflow?
- Which public claims are legally approved for marketing use?
- Should the landing-page example focus on a generic retailer, or a category-specific use case such as electronics?
- Is automated policy extraction/drafting a future feature, or should the page only promise uploads and review?
