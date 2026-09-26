# BondLayer: Q&A quick start

Prepared 13 September 2026 from the working repository, source review, focused tests, and selected official commerce sources.

**Read this first**, then use [the 60-question answer bank](PRODUCT-QA-GUIDE.md) and [the evidence and claim-check notes](QA-EVIDENCE-NOTES.md).

## The message everyone should know

> BondLayer helps retailers turn product spreadsheets and policy documents into structured, attributable information that compatible AI shopping agents can use. That lets the agent consider relevant service benefits alongside price, while leaving the buying decision on the shopper's side.

**Memorable line:** “In a room full of agents, we are building the thing agents read.”

### A 30-second answer

> Imagine asking an AI assistant for a laptop under $1,500 that is easy to return. A product feed can show the price, but the returns policy may be buried in a document. BondLayer checks the retailer's catalogue, helps extract its policies for human review, and publishes signed benefit records through a commerce API. A compatible agent can inspect those records while comparing offers. Our prototype demonstrates onboarding, matching, evidence and an API checkout confirmation; actual payment is the next integration step.

### A 60-second answer

> Retailers already compete on things beyond price: returns, warranties, delivery and loyalty benefits. AI shopping agents need those advantages in a form they can inspect reliably. BondLayer gives the merchant a connected workflow: upload a catalogue, fix data issues, upload policies, review the extracted benefits, then sign and publish them.
>
> Our buyer-agent demonstration shows how that information can be used during comparison. The current live client uses a model to choose among eligible offers; the reference rules mode uses deterministic effective-cost arithmetic. Signatures and data checks are computed in code in both cases.
>
> In our historical 30-request synthetic evaluation, benefit records answered 15 of 18 service-and-values clauses, compared with zero for our basic-feed control. That demonstrates additional answerability, not a measured sales increase. Our next business step is a retailer pilot to test integration effort, usefulness and commercial outcomes.

## Choose your explanation for the audience

| Audience | Lead with | Explain if needed | Answer-bank section |
|---|---|---|---|
| Non-technical, no commerce background | A shopper's laptop example | Shopping agent, catalogue, signed record | A: Q1–Q12 |
| Non-technical, commerce experience | Making existing service advantages visible at comparison | Adoption, merchant effort, margin and ROI | B: Q13–Q28 |
| Technical, no commerce background | Upload → validate → approve → publish → compare | Trust, schema, AI boundaries, architecture | C: Q29–Q44 |
| Technical and commerce experience | Eligibility, attribution and transaction semantics | Stacking, identity, quote integrity, evaluation | D: Q45–Q60 |

## Ten answers to rehearse first

1. **Who pays?** The proposed customer is a retailer; the proposed model is a merchant subscription based on catalogue size and usage. Pricing and willingness to pay still need validation.
2. **Why would they buy?** To make their existing offer easier for agents to understand and reduce the work of publishing it. We have a technical demonstration, not proven conversion uplift.
3. **Why not schema.org or a loyalty platform?** They are credible baselines and possible integrations. Our focus is the file-to-reviewed-and-signed-benefit workflow, with explicit scope and evidence.
4. **What does signing prove?** Integrity and attribution relative to a trusted key. It does not prove the retailer's claim is true or that the service will be delivered.
5. **Who decides the winner?** The shopper-side agent. In the current live stand-in, a model chooses the final order. The historical reference mode sorts by deterministic effective cost.
6. **What is the strongest number?** Historical synthetic answerability: **15/18 service-and-values clauses versus 0/18** for the records-absent control. Not 83% sales uplift or 83% general AI accuracy.
7. **Does checkout take payment?** No. It confirms items and rechecks cited records. The status is `confirmed_awaiting_payment`; no payment or stock reservation occurs.
8. **Is the effective cost the amount paid?** No. It is a shopper-specific comparison figure. Checkout uses the product prices, and a production total would also need the relevant tax, delivery and promotion logic.
9. **Is it production-ready?** It is a working local prototype. Authenticated merchant access, proven account linking, protected key storage, live commerce integrations and production measurements are next-stage work.
10. **What are you asking FPT for?** An introduction to one suitable retail design partner and an integration owner, so we can test the merchant workflow and agree measurable pilot outcomes.

## Four distinctions that protect your credibility

- **Signed ≠ independently true.** A merchant can sign an inaccurate claim.
- **Selected ≠ purchased.** A demo recommendation or checkout confirmation is not a paid order.
- **Historical benchmark ≠ live-model evaluation.** The benchmark evaluates a frozen synthetic rules-mode setup.
- **Readable by a compatible client ≠ adopted by every shopping platform.** Real platform interoperability needs testing and adoption.

## The current version matters

The repository was being actively integrated during this review. Live model ranking, membership lookup and shopping insights appeared or changed while it was being read. Older README and pitch sentences may describe the previous deterministic-only buyer.

Before rehearsal, open the actual demo response and check `ranking_source`. Follow `buyer-agent/src/agent/main.py` and `rank.py` for the implementation. Describe the exact submitted build; do not blend different revisions into one story. See the evidence notes for the concrete mismatches found.

## A reliable answer structure

**Answer → mechanism → evidence → boundary/next step.** Aim for 20–40 seconds, then stop.

Example: “We reduce unsupported benefit use by verifying records and keeping the source terms attached. Our tests cover tampering and refusal cases. That proves specific checks, not that all model explanations are correct; the next evaluation needs adversarial and real-policy examples.”

If you do not know a number:

> “We have not measured that yet. What we have demonstrated is ____. We would measure ____ in the pilot using ____.”

If a judge finds a real gap:

> “You're right: that part is a prototype limitation. The current behavior is ____. The production implementation would need ____.”

## Rehearsal: one hour

| Time | Exercise |
|---|---|
| 0–10 min | Every member gives the 30-second explanation without acronyms. |
| 10–25 min | Draw the architecture and narrate one request. Point to where the model decides and where code verifies. |
| 25–40 min | Randomly choose eight answer-bank questions across all four audiences. Keep each first answer under 40 seconds. |
| 40–50 min | Challenge signature truth, adoption, ROI, legal warranty wording and benchmark fairness. |
| 50–60 min | Rehearse an unseen request, no-match case, provider failure and the transition to a labelled reference/recorded demo. |

For the actual **five-minute Q&A**, use one lead answerer per question. Agree the hand-off: “Minh Hieu can explain the evaluation method” rather than having several people answer at once. Suggested ownership: product/business lead; backend/protocol lead; AI/evaluation lead; buyer-agent integration lead; merchant-experience lead. Confirm these assignments with the team.

**Final drill:** “Why should a retailer trust your result when the merchant supplies the claims, you built the demo agent, and the evaluation is synthetic?” A good answer acknowledges all three, explains the checks, and proposes an independent pilot instead of promising certainty.
