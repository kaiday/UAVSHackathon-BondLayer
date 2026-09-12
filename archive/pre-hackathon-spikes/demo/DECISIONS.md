# Design decisions — AgentBridge spike

Companion to the team's BondLayer spike (`bach-demo`); the two share wire
vocabulary on purpose. Like it, **this is pre-work, not submission code**
(rulebook: nothing written before the Round 2 window may be copied in).
The artefacts that survive are the schemas, the invariants, the prompts,
the recorded fixtures and the demo scripts — the implementation gets
rewritten on the day.

## D1 — Two protocol heads over one core
MCP (stdio) is how a real third-party agent — Claude Desktop — shops here
live on stage. The UCP head (draft-style HTTP) is the proposal's actual
architecture: benefit records ride a vendor extension pruned by ordinary
capability negotiation. Both heads call the same `AgentBridgeService`, so
neither is a mock of the other. Rejected: UCP-only (loses the live
third-party-agent moment), MCP-only (leaves the §5 architecture claim
undemonstrated).

## D2 — The transaction leg is in scope here
Unlike the sibling spike, this repo *buys things*: create (PENDING, no
money) → confirm (test-mode settle), idempotency keys that also never
double-discount, consent-gated enrolment, settlement at the member price.
"The offer that won is the offer delivered" is executed, not asserted.

## D3 — Value derives from FACTS under the customer's policy
First implementation valued warranty/shipping cards *at their declared
ceiling* — so a merchant inflating the ceiling inflated its credit. The
sibling spike's invariant test caught the same flaw in their first draft;
ours is fixed the same way: cards carry typed facts
(`extra_warranty_months: 12`), the customer's policy converts facts to
cents, and the declared figure is applied only as a cap.
`tests/test_invariants.py::test_inflating_declared_ceilings_changes_nothing`
re-signs the inflated cards (as a lying merchant would) and asserts
nothing moves.

## D4 — Unsigned claims are penalised, not just zeroed
Under plain value-at-zero, a merchant spamming unverifiable claims lands
where an honest silent merchant lands — lying would be free. Penalty =
10% of the claimed ceiling (a CustomerPolicy dial), added to effective
cost. Expired-but-signed promos are rejected *without* penalty: a lapsed
verifiable promise is not a lie. Note the planted unsigned "$50 agent
bonus" card in our own catalogue costs *us* $5.00 of effective cost —
kept deliberately, because watching the rule fire against the merchant
publishing it is the demonstration.

## D5 — The baseline is negotiation, not sabotage
BEFORE = the same payload with the extension pruned because the agent
did not declare it. One `if BENEFIT_VALUE in negotiated` in `ucp.py` is
the entire difference. (The *hostile HTML* baseline in benchmark.py is a
different, older claim — transactability — and is kept separate.)

## D6 — Fixture-first model calls with provenance
Every completion records model, timestamp, latency and the prompt hash,
and replays by default; the fixture key hashes model+prompt so switching
either re-records instead of silently replaying a different experiment.
A stage run never touches the network. Same policy as the sibling spike.

## D7 — The converter's guardrail normalises before matching
Source quotes are matched with markdown emphasis stripped, whitespace
collapsed, case folded — adopting the sibling spike's recorded D9.15
failure (`**$12.95**` vs `$12.95` rejected ten faithful drafts) without
re-learning it. The approval gate is interactive by default;
`--approve-all` exists but announces itself as rehearsal mode, and
approved cards write to a JSON artefact that serving deliberately does
NOT auto-load.

## D8 — Honesty labels stay in the output
"UCP-draft-style, not certified" (README, module docstrings); fixture
provenance printed beside every replayed answer; the compare script's
tally warns when the adversary got credited instead of hiding the run.

## Known weaknesses (recorded, not hidden)
1. Key distribution is demo-grade: the key is fetched from the merchant
   being verified. Pinning helps; a registry/CA is the real answer.
2. CustomerPolicy defaults ($0.25/warranty-month) are invented, not
   measured — "value under a stated policy", never "true value".
3. The live experiment is unrecorded until the user runs it with a key;
   until then this repo's flip is a hypothesis, the sibling spike's is
   evidence (theirs: 5/5 both conditions, one model, one prompt).
4. One member store, in memory; enrolments vanish on restart.
5. The web demo's chat needs a key once per prompt-variant to record;
   only the canonical question will have been rehearsed.
