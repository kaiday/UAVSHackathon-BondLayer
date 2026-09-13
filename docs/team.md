# Team — names, branches, Q&A cards

Four different naming schemes have been used for the same five people across this
repository's documents: the handover's internal nicknames, the names submitted on the
Round 1 `main.tex` (source of truth for registration), the Round 2 git branches, and the
Day 1 `WORKPLAN.md` owner labels. This file is the crosswalk. If a document elsewhere
names someone inconsistently, this file wins. (The handover, `WORKPLAN.md` and the Day 1
progress notes cited below were removed from the tree in the 13/09 cleanup; they are in git
history at commit `074e51c`.)

## The crosswalk

| Submitted name (`main.tex`, source of truth) | Handover nickname | University role | Round 2 `WORKPLAN.md` label | Round 2 branch(es) | Q&A card owned |
|---|---|---|---|---|---|
| **Thanh Nha Phan** | Ford | Product Manager | Nha | `feat/nha-eval-data`, `feat/nha-d2-docs` | Q1, Q5 |
| **Hoang Manh Nguyen** | Manh | Software Engineer | Nguyen | `feat/nguyen-ucp-head`, `feat/nguyen-d2-deploy` | Q3, Q8 |
| **Minh Hieu Tran** | Hieu | ML Engineer | Hieu | `feat/hieu-interpreter`, `feat/hieu-d2-resolver` | Q4, Q6 |
| **Thanh Bach Ly** | Bach | Software Engineer | Bach | `feat/bach-records-signing`, `feat/bach`, `feat/bach-d2-one-demo` | Q2, Q9 |
| **Ha Anh Minh Truong** | Chan | UX/UI Designer | Minh | `feat/minh-console` | Q7, Q10 |

All five: University of Wollongong.

## Where the naming came from, and why it drifted

- **`main.tex`** (the submitted Round 1 proposal, `/Users/apple/Downloads/UOW/UAVS/main.tex`)
  is the only document with full legal names, university, email and role, and it is what
  went to the Organising Committee. It is the source of truth for the team block in every
  Round 2 document, per `docs/notes/DAY2-PLAN.md` §2's source-of-truth order.
- **`docs/notes/BondLayer_PROJECT_HANDOVER.md`** was written before the team settled on using full
  names consistently, and uses short first-name-style handles (Ford, Manh, Bach, Chan,
  Hieu) for the same five people. Its §9 Q&A assignments ("Ford 1 & 5 · Manh 3 & 8 · Bach
  2 & 9 · Chan 7 & 10 · Hieu 4 & 6") use this scheme. **"Chan" in the handover is Ha Anh
  Minh Truong** — the handover's nickname for the UX/UI designer, not a sixth team member.
- **`bondlayer/WORKPLAN.md`** (Round 2, Day 1) introduced yet another label for the same
  UX/UI designer: **"Minh."** This is Ha Anh Minh Truong again, chosen from her own given
  name rather than the handover's "Chan." It is a coincidence of naming, not a relation, that
  the ML engineer's submitted name is *Minh* Hieu Tran and the UX designer's `WORKPLAN.md`
  label is also *Minh* — two different people. Where a document just says "Minh" with no
  branch or file path alongside it, check which one from context; this repository's own
  branch names disambiguate (`feat/hieu-interpreter` vs `feat/minh-console`).
- **Branch names describe Day 1 origin, not current content.** `docs/notes/overview-progress.md`
  §2 records that by 13:05 on Day 1 the actual work had moved: `feat/nguyen-ucp-head` became
  the dashboard, `feat/bach-records-signing` became the chat app, `feat/hieu-interpreter`
  became RAG/DAO before settling back onto the intent interpreter. The team's decision was to
  leave the names as they were rather than rename mid-hackathon. The Day 1 branches have since
  been merged into `round2/dev` and deleted.

## Q&A card assignments, in the real names

Renumbered from the handover §9 list (Ford 1 & 5 · Manh 3 & 8 · Bach 2 & 9 · Chan 7 & 10 ·
Hieu 4 & 6) to the submitted names. The rewritten cards themselves, updated for the real
build (ES256 not Ed25519, two apps not five surfaces, 30 requests not 100+, the 13:16 gold-set
correction), are in [`docs/notes/PITCH-OUTLINE.md`](../docs/notes/PITCH-OUTLINE.md).

| Card | Question (handover §9 topic) | Owner |
|---|---|---|
| Q1 | Why would a customer let a merchant influence their agent? | Thanh Nha Phan |
| Q2 | Why isn't this just another loyalty API? / Talon.One's UIP? | Thanh Bach Ly |
| Q3 | Why a protocol instead of an existing standard? | Hoang Manh Nguyen |
| Q4 | How do you value non-cash benefits? | Minh Hieu Tran |
| Q5 | Who controls the ranking? | Thanh Nha Phan |
| Q6 | How do you prevent discrimination or manipulation? | Minh Hieu Tran |
| Q7 | How do you beat two-sided adoption? | Ha Anh Minh Truong |
| Q8 | What can you build in 16 hours? | Hoang Manh Nguyen |
| Q9 | What proprietary advantage develops over time? | Thanh Bach Ly |
| Q10 | What measurable value for FPT and its clients? | Ha Anh Minh Truong |
| Q11 | Doesn't the merchant now see the shopper's intent? (added 13/09 for the intent route) | Thanh Nha Phan |

<!-- VERIFY 13/09: confirm each owner still holds their card at rehearsal; DAY2-PLAN.md's
     Day 2 schedule does not name a fixed Q&A-rehearsal slot the way the Day 1 plan did.
     Left unresolved by the WS-D2 truth pass (13/09): whether each owner still holds their
     card is a fact about a rehearsal that has not happened yet, not something this pass can
     verify from the repository. -->
