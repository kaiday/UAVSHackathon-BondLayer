# Pitch outline — Round 3 Gala Pitching Night

10 minutes maximum, followed by a 5-minute Q&A (Rulebook §D.3). Ordered against the
Problem Statement's evaluation priorities, in weight order — Intention Accuracy &
Semantic Matching, then Technical Architecture, then Business Value & Conversion — with
market strategy and the roadmap carrying the Round 2 rubric's equal-highest criterion
(Market strategy, 25 pts) into the same ten minutes.

Numbers in this outline are copied from `bondlayer/docs/eval-results.md` at commit `339a7ed`
(the run itself is `90de308`, re-verified byte-identical at `339a7ed`); see the root
`README.md` Evaluation section for the rule governing what may be spoken — a number is
spoken on stage only if it is in that file with a commit hash.

## Timed structure

| Time | Segment | Content | Speaks to |
|---|---|---|---|
| 0:00–0:45 | **The query** | State the demo query live: *"a laptop under $1,500 I can return easily if it turns out not to suit my work, from a brand that actually repairs things."* One hard price filter, one soft performance signal, one service constraint, one values constraint — say the taxonomy out loud before the system does anything. | Framing |
| 0:45–2:00 | **The decode** | Show the parsed constraints: HARD / SOFT / SERVICE / VALUES, each with its own kind and why the split matters — the bottom two rows have no catalogue column and are exactly what the interpreter has to resolve against signed records instead. Decode accuracy on the frozen 30: precision 0.914, recall 0.972, 22/30 perfect decodes. Show this decode twice — once from the agent's own trace, once from `curl -X POST .../voltway/ucp/intent/propose`, where Voltway decodes the same sentence on its own wire and returns the same `decoded_intent` block. One interpreter, two seats. | Priority 1 |
| 2:00–3:30 | **The match, with justification** | Matched SKUs with one cited `evidence_record_id` or `evidence_attribute` per constraint, and the honest `unsatisfied` list where nothing answers a clause. Not a SKU list — a reason per line. The trace's `[resolve: ok]` step reads "4 of 4 constraints answered; 2 answered only by a verified record" — the same justification the `intent/propose` response carries in `proposals[].resolved`, cited to `vw-returns-60` and `vw-repairability-parts-5y`. | Priority 1 |
| 3:30–5:00 | **The wire, with and without the extension** | Same query, twice, over the actual header: `UCP-Agent: dev.ucp.shopping.catalog.search;dev.ucp.shopping.catalog.lookup;org.bondlayer.benefit_value` declared, then absent. Show the response: `extensions` present vs entirely absent — capability negotiation, not a branch in the code. Add the fourth capability, `org.bondlayer.intent_match`, and the same header now hits `POST /voltway/ucp/intent/propose` instead of `catalog.search` — same negotiation mechanism, same 406 when a merchant (or the control) has not declared it. | Priority 2 |
| 5:00–6:00 | **The flip** | Effective cost recomputes the ranking: Voltway `VOL-0031` wins at **$933.01** effective against a $1,142.96 shelf price, never the cheapest shelf price anywhere in the catalogue, once the extension is on; off, CityCircuit `CIT-0032` wins at $1,066.00 shelf, no flip. A tamper test lands here too — inflate an unsigned claim, watch it earn nothing. | Priority 2 |
| 6:00–7:00 | **The dashboard: why we lost** | Switch to the losing merchant's view: fields exposed, share of the offer legible, verified value credited, value withheld by the wire, and the one-line reason. This is the surface FPT explicitly said matters less than the logic behind it — keep it short on stage for exactly that reason. | Priority 3 |
| 7:00–8:30 | **Market** | Segment, value model, the competitive table, distribution through FPT's own retail delivery practice. See the root README's Market strategy section for the full argument; this segment states the headline of each, not the detail. | Round 2 rubric: Market strategy (25 pts) |
| 8:30–9:30 | **Roadmap and the ask** | Pilot with one mid-market electronics retailer in shadow mode → protocol certification → an agent-side SDK → propose the benefit extension upstream to UCP. The ask: what FPT's retail delivery practice would need to carry this into a client engagement. | Round 2 rubric: Deployability, Adaptation |
| 9:30–10:00 | **Close** | Restate the positioning line: *"In a room full of agents, we are building the thing agents read."* Hand to Q&A. | — |

## Q&A drill cards

Ten cards, carried over from the pre-hackathon handover §9 (git history, commit `074e51c`) and rewritten for the
build that actually shipped: ES256 detached object signatures, not Ed25519; two
applications (`bondlayer/` and `buyer-agent/`), not five surfaces; a 30-request frozen
evaluation set, not the 100+ promised in the Round 1 proposal's Phase 4; and the 13:16
gold-set correction. Assignments use the submitted `main.tex` names — see `docs/team.md`
for the full crosswalk from the handover's nicknames.

**Q1 — Why would a customer let a merchant influence their agent?** (Thanh Nha Phan)
It doesn't. The merchant supplies signed inputs; the weights live in the shopper's own
valuation policy, which never leaves the agent. Magentic Marketplace (Bansal et al. 2025,
preprint) found unverified claims are the manipulation vector in agentic markets — signing
is the protective answer, not a promotional one.

**Q2 — Why isn't this just another loyalty API? What about Talon.One's UIP?** (Thanh Bach Ly)
Three sentences, as drilled. UIP exposes point balances, tier status and discount data for
brands already on Talon.One's platform, machine-readably, via MCP and UCP extensions — it
transports incentives. BondLayer verifies and values the *full* offer, including service
facts UIP does not carry at all (warranty, trade-in, repairability), starting from files any
mid-market retailer already has rather than requiring a platform migration. UCP and UIP both
transport; we are the layer that verifies, prices under the shopper's own policy, and
reports back what was withheld.

**Q3 — Why a protocol instead of existing standards? And why object-level signing, not UCP's own RFC 9421 message signatures?** (Hoang Manh Nguyen)
We are not a protocol — `org.bondlayer.benefit_value` is a vendor extension inside UCP's own
capability negotiation, declared in `/.well-known/ucp` like any other. On signing: UCP
already signs *messages* with RFC 9421 HTTP Message Signatures, but that signature is
transport-level and ephemeral — it authenticates one response in flight and leaves nothing
an agent can cache, re-verify later, or cite when justifying a ranking (`main.tex` §2.4).
Our records are signed as standalone objects, ES256 over canonical JSON, so a record
outlives the response that carried it and can be re-verified independently. RFC 9421
protects the wire; object signing protects the claim.

**Q4 — How do you value non-cash benefits?** (Minh Hieu Tran)
Bounds, not point estimates. The merchant declares a ceiling; the shopper's own policy
decides how much of it counts; an unsigned claim is never valued at all. Values claims
(sustainability, repairability) are a distinct case: signed, cited, and worth exactly
$0 by design — ethics do not convert to dollars, and pretending otherwise would be the
fake precision that loses this exact question in Q&A.

**Q5 — Who controls the ranking?** (Thanh Nha Phan)
The agent, over its own shopper-side valuation policy. The merchant never sees the policy
or the weights, only the request. Live: toggle the extension off and on against the same
query and watch the ranking flip without any code path changing on the merchant side.

**Q6 — How do you prevent discrimination or manipulation?** (Minh Hieu Tran)
Signed records keyed to disclosed program status only, an audit trail on every credited
figure, and two properties enforced as tests rather than asserted in a slide: inflating a
declared ceiling cannot improve rank, and a larger unsigned claim earns nothing rather than
something. Privacy and consumer-law review is flagged before any real member data would be
used; this pitch draws no legal conclusions.

**Q7 — How do you beat two-sided adoption?** (Ha Anh Minh Truong)
The merchant-side value stands alone without agent-side cooperation: UCP readiness, a
conversion story, and the dashboard's own analytics work the day a merchant plugs in.
Capability negotiation degrades gracefully for an agent that does not know us. Distribution
runs through FPT's own retail delivery practice and systems integrators, not through
persuading every agent vendor first — and the extension is designed to be proposed upstream
to UCP, which is the actual answer to the two-sided problem long-term.

**Q8 — What can you build in 16 hours?** (Hoang Manh Nguyen)
What is in this repository: two applications, one merchant service and one buyer-agent
stand-in, three merchant profiles from one code path, ES256 object signing (not the
Round 1 proposal's placeholder Ed25519), a deterministic valuation core, and a 30-request
frozen evaluation set — not the 100+ requests promised in the Round 1 proposal's Phase 4,
said honestly rather than overclaimed. The set was frozen at 10:50 on 12/09 before the
enriched catalogue feed existed, with one gold-set correction applied later at 13:16 once a
labelling error in the HARD-constraint gold answers was found — the correction is a commit,
not a rerun of the freeze.

**Q9 — What proprietary advantage develops over time?** (Thanh Bach Ly)
The benefit-schema library across merchant programs, the policy-conversion capability
itself (the approval-gated LLM step that turns prose into typed, signed facts), and the
loss-reason dataset the dashboard accumulates — none of which the open protocol produces
by itself, and all of which compound the more merchants and requests run through it.

**Q10 — What measurable value for FPT and its clients?** (Ha Anh Minh Truong)
For a client: share of the real offer legible to an agent, verified value actually
creditable, and repeat-purchase share retained against a price-only baseline, all measured
per request rather than estimated. For FPT: a reusable accelerator inside its retail
delivery practice's UCP onboarding work, with a second vertical to follow the pilot.

**Q11 — Doesn't the merchant now see the shopper's intent?** (Thanh Nha Phan)
Only on the route that negotiates it, and only the utterance — the merchant never receives
the shopper's valuation policy, its benefit weights, or the cross-merchant comparison, so it
can see what was asked but not what any of it is worth or who else is being considered. The
merchant's `intent/propose` response is a proposal with a justification, not a decision: the
agent still verifies every cited record and still ranks by effective cost, exactly as it does
against `catalog.search`. What changes is where the decoding happens, not who decides.

The numbers above are copied from `bondlayer/docs/eval-results.md` at commit `339a7ed`
(run `90de308`, re-verified byte-identical at `339a7ed`); the timing column is the outline's
own budget, not yet checked against a timed rehearsal.
