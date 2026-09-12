# Problem Setter notes

Template for the 15:30–16:00 Problem Setter window (`bondlayer/WORKPLAN.md` Day 1 schedule).
Round 2's "Adaptation & upgrade" criterion (10 points) scores exactly this: "how well the
team incorporated the full case study and Problem Setter input" (Rulebook §C.4). This file
is the evidence.

**This document was not attended by the agent that formatted it, and its content is not
invented here.** Nha led the window in person; the questions below are the standing list she
walked in with (`BondLayer_PROJECT_HANDOVER.md` §3.2). The ANSWER and WHAT CHANGED columns
are left as placeholders for Nha to dictate from her own notes — nothing is filled in on her
behalf. If a question was not put to the Problem Setter in the window, say so rather than
leaving the row silently blank.

**How to fill this in.** For each row: (1) paste or summarise what FPT actually said,
verbatim where you have it; (2) name the concrete thing that changed in the product, the
data, or the pitch as a direct result — a file, a commit, a design decision — or write "no
change made" if the answer did not change anything. A change that cannot point at an
artefact is not evidence for the Adaptation criterion.

---

## About the organisation

| # | Question asked (handover §3.2) | ANSWER — Ford to dictate | What changed |
|---|---|---|---|
| 1 | Which client profile should this fit — enterprise retail or mid-market? | ANSWER — Ford to dictate | — |
| 2 | Is FPT's digital-commerce practice planning UCP/ACP integrations that a merchant-side layer like this could ship inside? | ANSWER — Ford to dictate | — |
| 3 | The closest real-world example given at the workshop was B2B vendor sourcing — should we prioritise consumer shopping agents, B2B procurement agents, or design the benefit schema to serve both? | ANSWER — Ford to dictate | — |
| 4 | Will FPT provide the mock catalogue mentioned at the workshop, and in which vertical? | ANSWER — Ford to dictate | — |
| 5 | Would FPT prefer the benefit extension proposed upstream to UCP as an open contribution, or kept as a proprietary accelerator? | ANSWER — Ford to dictate | — |

## About users

| # | Question asked (handover §3.2) | ANSWER — Ford to dictate | What changed |
|---|---|---|---|
| 6 | For mid-market electronics retailers, what share of retention value is service-based (warranty, trade-in, repairs, returns) versus points? | ANSWER — Ford to dictate | — |
| 7 | Do those rules realistically live in documents a policy converter can read? | ANSWER — Ford to dictate | — |
| 8 | Will shoppers set a valuation policy once (which benefits count, tolerated premium), and what defaults are safe when they do not? | ANSWER — Ford to dictate | — |

## About implementation

| # | Question asked (handover §3.2) | ANSWER — Ford to dictate | What changed |
|---|---|---|---|
| 9 | How will intent-matching accuracy be measured — does FPT hold a benchmark set of multi-constraint requests, or should teams author and publish their own? | ANSWER — Ford to dictate | — |
| 10 | For ambiguous or contradictory intent the system returns its best-understanding recommendation, as advised — should it also surface one clarifying question when confidence is low? | ANSWER — Ford to dictate | — |
| 11 | What security and privacy baseline is expected at prototype stage versus a client pilot (key management, data residency, audit)? | ANSWER — Ford to dictate | — |

---

## Case-study adaptations already made before the window

These are changes the team made in response to its own re-reading of `FPT-Problem-Statement-Final.pdf`
and the Round 2 alignment analysis, ahead of and independent of the 15:30 window itself.
Recorded here because they are also "Adaptation & upgrade" evidence, and because they show
what the team already understood correctly before asking, which sharpens which of the
questions above are still genuinely open:

| Adaptation | Trigger | Evidence |
|---|---|---|
| Multi-constraint intent taxonomy (HARD / SOFT / SERVICE / VALUES) replacing the four-field valuation-policy extractor | Alignment analysis §3.1(a): the Round 1 spike decoded price-sensitivity, not intent | `bondlayer/data/eval/taxonomy.md` |
| Electronics catalogue with 62 distinct products, near-duplicates and attribute noise, replacing the single shared-barcode jacket scenario | Alignment analysis §3.1(c): identical products across merchants leave nothing to match | `bondlayer/data/catalog/electronics.csv`, `bondlayer/GAPS.md` "Two corrections" |
| Values claims (`sustainability`, `repairability`, `durability`) as signed-but-unpriced records | Problem statement, Illustrative Direction 2, "Values-Based SEO for Agents" | `bondlayer/GAPS.md` gap 5, `bondlayer/data/records/northgear.signed.json` |
| Third merchant (NorthGear) added so ranking is a ranking, not a coin flip | Handover §8 assumed three profiles; the Day 1 plan had two | `bondlayer/data/policies/manifests.json` |
| ES256 over Ed25519 | The UCP signatures spec (`ucp.dev/2026-04-08/specification/signatures/`) mandates ES256; the Round 1 proposal (`main.tex` §5.1) already specified it — the handover's stack note was stale, not the submission | `bondlayer/docs/stage1-agent-ready-catalog.md` §5.5, `round2/overview-progress.md` §4.1 |

## Not yet acted on

Dynamic bundling (`Bundler`, WS-G) and closing the API loop past a status flag remain
partially or not implemented as of this document's commit — see the root `README.md`
"Deliberately not attempted" section for the current state, since that section is updated
later in the day and this one is not.

<!-- VERIFY 13/09: every ANSWER and What-changed cell above, once Ford dictates them. -->
