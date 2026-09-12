# BondLayer demo — decision record

Every design decision taken while building `demo/`, with the reasoning and the
alternatives rejected. Decisions marked **[asked]** were put to the team;
decisions marked **[taken]** were made unilaterally under the standing rule
"if an option stands out at >=70% confidence, choose it and document it".

**Authority note:** `round1/bondlayer-summary.md` is **the plan**.
`round1/BondLayer_Team_Deck (1).html` is brainstorming that exists as a
suggestion, not a specification. Where the two conflict, the summary wins.
Several decisions below were revised mid-build when this was clarified; the
revisions are recorded rather than erased.

---

## D0 — This code is a throwaway spike, not submission code **[taken]**

The rulebook (Round 2, section b) says: *"All code must be written during the
Hackathon period. Using code written before 09:00 on 05/09/2026 is strictly
prohibited."* Round 2 runs 05–06/09/2026; submission closes 17:00 on 06/09.
Today is 30/08/2026.

Therefore **nothing in `demo/` may be copied into the Round 2 submission.**
Its purpose is to de-risk the design and to produce artefacts that *are*
permitted as pre-work: specifications, schemas, synthetic datasets, prompts and
the demo script. The team rewrites the implementation on the day.

The deck's "12–13 Sep" hackathon dates are stale; the rulebook says 05–06/09.

---

## D1 — Scope: full mechanism, not a richer product feed **[asked]**

**Chosen: implement signed benefit values + deterministic valuation.**

The summary's Feature 2 ("feed the agent deals, policy, shipping speed,
membership perks") can be delivered two ways: as unstructured extra text in the
feed, or as typed, signed, independently verifiable claims. The first is
indistinguishable from prompt-stuffing and collapses under the question "so you
just wrote more marketing copy into your product data?". The second is a real
mechanism.

Rejected: "richer feed only" — no defensible answer to the prompt-stuffing
objection.

---

## D2 — UCP fidelity: real spec on the read path **[asked]**

**Chosen: implement the actual UCP catalog capabilities and the real vendor
extension mechanism; stub cart/checkout/payments entirely.**

The pitch's load-bearing claim is "an extension of UCP, never a rival protocol".
That claim is worth exactly as much as the wire format behind it. Reading a spec
and copying field names is tedious, low-creativity work that is explicitly
permitted as pre-hackathon effort, so doing it now is strictly better than
burning hackathon hours on it.

Payments and checkout are stubbed because BondLayer never touches them, so spec
fidelity there buys nothing.

Findings from the live spec are in `docs/ucp-findings.md`. Three of them
contradict the deck and matter.

---

## D3 — `org.bondlayer.benefit_value` extends catalog, not checkout **[asked]**

**Chosen: extend `dev.ucp.shopping.catalog.search` and
`dev.ucp.shopping.catalog.lookup`.**

The real UCP loyalty extension (`dev.uip.shopping.loyalty`) extends
**checkout** — loyalty data appears only once the shopper has already chosen the
merchant. Comparison-time offer data lives in the catalog capabilities.

So the framing is not "UCP forgot some fields". It is: *the loyalty extension
attaches to checkout; we attach the same class of data to catalog, because
catalog is where the agent actually decides.* That is a claim grounded in a
verifiable spec fact rather than an opinion.

Consequence and known objection: extending catalog with member-specific data
makes those responses per-member and therefore uncacheable. Mitigation: the
member block only appears when a member is linked via
`dev.ucp.common.identity_linking`; with no linked member the catalog response is
byte-identical to plain UCP. That is also the graceful-degradation path, and it
doubles as the demo's "before" state (see D5).

Rejected: extending checkout (spec-idiomatic, but the valuation would arrive
after the decision was made, which defeats the purpose); doing both (doubles the
schema surface for no demo value — trivial to add later if asked).

---

## D4 — The merchant's declared value is a ceiling, never a floor **[asked]**

**Chosen: hybrid.** Merchants sign verifiable *facts*; they may also declare a
bounded amount only where money is intrinsic (points rate, a discount). The
agent values everything from facts under the *customer's* parameters, then
applies `min(policy_value, merchant_declared_bound)`.

This buys one invariant, which is the strongest property in the design:

> **A merchant can never improve its own position by inflating a number.**

Inflating a declared bound raises a ceiling that is never reached, so it changes
nothing. Understating it only hurts them. This is demonstrable live rather than
asserted — see the inflation toggle in D9.4.

Rejected: merchant-declares-value (the merchant grades its own homework, and
"bounded" would only mean "bounded by the merchant's own claim");
facts-only (cannot express points redemption value — you need the merchant's own
rate and breakage assumptions, which no customer policy can supply).

Note: this resolved a contradiction inside the deck, which described benefits as
"bounded in AUD" by the merchant on one slide and exposed fit-risk value as a
*customer* slider on the next.

---

## D5 — The demo has a "before", and it is our own product switched off **[asked]**

**Chosen: two modes.** Baseline = the same LLM agent, the same query, against a
catalog with no `benefit_value` extension. Then the same run with it on.

The critical property is that the baseline is not a strawman built to lose. The
"no extension present" path is the graceful-degradation behaviour we are
required to implement anyway (D3), so *the "before" is our own product with the
extension switched off — which is what every UCP merchant has today.*

Two consequences accepted deliberately:

- The baseline is pinned (cached, temperature 0) for stage safety, with a
  "run it live" button as the optional flex. An LLM that accidentally picks our
  merchant in the baseline run would detonate the narrative.
- Our merchant must **genuinely deserve to lose** the baseline. The catalogue is
  built so it is a real loser at list price and a real winner on adjusted cost.
  Tuning the data so benefits "just barely" tip it would be visible and cheap.

Rejected: no baseline at all (assumes the judge already believes the problem
exists; the before/after is what makes it legible in 30 seconds to a
non-technical judge, and Market Strategy is 25 of 100 points); a deterministic
price-only baseline (a strawman a judge can poke — "you compared yourself to a
`sort()`").

---

## D6 — Retention Decision Engine: cut from the build, kept in the docs **[asked]**

**Chosen: out of scope for the spike.** Design preserved in
`docs/deferred-retention-engine.md` for later experimentation.

It has no counterpart in the summary at all — nothing in the plan describes the
merchant *reacting* at decision time. Features 1 and 2 are a **publishing**
layer: the merchant declares things, the agent verifies them, and the merchant
never learns it was compared. A retention engine makes BondLayer a real-time
bidding participant that must be told "you are losing to someone 10–15%
cheaper". That is a different product with a different privacy story, and the
most expensive piece in the design (second protocol flow, merchant-side policy
engine, dashboard).

It was the deck's "wow moment". The deck is a suggestion, not the plan.

---

## D7 — The plug is visible: real ingest, both halves **[asked]**

**Chosen: merchant *native* artefacts go in.**

1. A messy catalogue export (inconsistent units, missing GTINs, free-text sizes)
   → deterministic mapping → conformant UCP catalog.
2. A plain-English returns / warranty / membership policy document → LLM drafts
   typed `benefit_value` records → **human approval gate** → signed.

Feature 1 is half the pitch and is otherwise invisible plumbing. If the mock
merchant data were already tidy JSON shaped like UCP, we would have proved
nothing, and a judge would notice the input schema suspiciously resembles the
output.

The policy-document converter is also the highest-risk component in the design
and the one most worth discovering problems in *now*: it is where an LLM is
genuinely necessary (nobody hand-codes every merchant's T&Cs), where
hallucination would be most damaging, and what makes the AI/ML use
non-mechanical rather than decorative.

The approval gate keeps the model strictly out of the money path: it drafts, a
person approves, and **only signed records are ever valued.** Unapproved drafts
are displayed and ignored.

Mitigation for demo fragility: the approval gate is a real screen with
pre-approved records cached, so a bad draft is visibly *caught and corrected*
rather than crashing the opening beat — which demonstrates the guardrail better
than a clean run would.

---

## D8 — Two valuation paths; the money shot uses the one that needs no adoption **[asked]**

**Chosen: degradation-first.**

- **Primary path** — BondLayer publishes normalised, typed, signed benefit data
  into the UCP catalog response. *Any* LLM agent reads it and reasons better
  because the data is finally structured and verifiable. No BondLayer code on
  the agent side.
- **Upgrade path** — the deterministic TRV library, for agents that want
  auditable arithmetic instead of model judgement.

The money shot runs on the **primary** path. The deepest strategic hole in the
agent-side-library design is that it assumes agents adopt our library — and an
agent that imports BondLayer has, by definition, already heard of us, which is
the opposite of the summary's premise. Putting the library first would mean
demoing a world that does not exist yet.

Ordering it this way means the core claim never depends on anyone adopting
anything: the merchant plugs in once and gets better outcomes from agents that
do not know we exist. The library then reads as "and here is where this goes
when agents want provable numbers instead of vibes" — a roadmap asset, not a
dependency.

**Constraint this imposes on schema design (deliberate and welcome):** the
published data must be *self-describing*. An LLM that has never seen our schema
must make sense of it from field names and units alone. This forces the schema
to be legible rather than clever.

Rejected: agent-side library only (gated on adoption we cannot assume);
merchant-side computed ranking (the merchant scores itself — the exact problem
D4 exists to avoid).

---

## D9 — Decisions taken without asking

| # | Decision | Reasoning |
|---|---|---|
| D9.1 | **Vertical: waterproof jackets, ~$200.** | The summary's own worked example is *"a good waterproof jacket under $200"*. Initially set to footwear from the deck's pilot wedge; corrected once the summary was confirmed as the authority. |
| D9.2 | **Three merchants.** A runs BondLayer and is dearer at list; B is plain UCP and cheapest at list; C is plain UCP and makes an unsigned claim. | Minimum cast that produces a real comparison, an honest baseline loss, and an adversary. |
| D9.3 | **Minimal tamper toggle kept.** One competitor makes an unsigned claim; it is displayed but never valued. | Not for theatrics — without an adversary in the picture, signing is unmotivated and a judge will reasonably ask why the schema needs cryptography at all. Cheap once signing exists. |
| D9.4 | **Inflation toggle kept.** Inflate merchant A's declared bound; watch the ranking not move. | The D4 invariant is only convincing if you can watch it fail to do anything. Pairs with D9.3: inflate a *signed* number and it is ignored; make a big *unsigned* claim and it counts against you. |
| D9.5 | **Uncertainty is two mechanisms, not one flat constant.** *Unverified* (no valid signature): penalised proportionally to the size of the claim, capped by policy. *Provisional* (signed but forecast/conditional, e.g. tier progression): confidence-weighted — discounted, not penalised. | A flat penalty is the one number in the ledger with no derivation behind it, in a design whose entire pitch is "deterministic and explainable". Proportional penalty also gives lying a price: under a value-at-zero rule, a merchant spamming unverifiable claims ends up in exactly the same position as an honest merchant who claims nothing. |
| D9.6 | **Benefit ontology v0.1 — 7 types:** `points_earn`, `member_price`, `free_returns`, `free_shipping`, `warranty_extension`, `tier_progression`, `retention_offer`. Each carries `facts`, optional `declared_bound_aud`, `conditions`, `expires_at`, `signature`. | `retention_offer` is defined in the schema but produced by nothing (D6) — defining it now costs nothing and keeps the deferred work purely additive. |
| D9.7 | **Customer policy is derived from the shopper's own words** by intent extraction, with sliders exposed for live manipulation. | More summary-faithful than a slider-first UI: the summary describes a shopper *talking to* an agent, not configuring one. Sliders remain for stage control. |
| D9.8 | **Merchant public keys are published in the UCP capability declaration** and pinned on first fetch. | The trust root has to live somewhere, and the capability declaration is already fetched during negotiation. A real deployment needs a stronger story — noted as a known gap, not solved. |
| D9.9 | **Stack: Python, FastAPI, Streamlit, PyNaCl (Ed25519), JSON files.** No database, no Docker. | Matches what the team already declared they can run. State is small enough that a database would be ceremony. |
| D9.10 | **LLM: Anthropic, fixture-first.** Every LLM call is cached to `data/fixtures/`; the demo runs fully offline from fixtures and only calls the API when a key is present and the cache misses. | No API key present in this environment, and stage wifi is not to be trusted. Also makes the pinned baseline of D5 fall out for free. |
| D9.11 | **Merchants are separate HTTP services**, and the agent speaks to them over real HTTP. | The demo's claim is that a third-party agent can read a merchant over a protocol. In-process function calls would quietly assume away the thing being demonstrated. |
| D9.12 | **LLM explanation gets a faithfulness check**: every number it cites must exist in the computed table, else fall back to a template. | The model is allowed to write the sentence; it is not allowed to invent the arithmetic. |

---

## D9.13 — Fixtures are recorded live, through whichever provider is available **[taken]**

The original build had no `ANTHROPIC_API_KEY`, so every fixture was
hand-authored and the README carried a large honesty warning saying so. That
warning was correct and it was also fatal: a hand-written completion proves
nothing about model behaviour, and the demo's entire headline is "the model
chose for itself".

`bondlayer/llm.py` therefore takes whatever live transport it can get. Three
exist, preferred in this order:

| transport | trigger | model default |
|---|---|---|
| `openai` | `OPENAI_API_KEY` | `gpt-5` |
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-5` |
| `claude_cli` | `claude` on PATH, logged in | `claude-sonnet-5` |

`BONDLAYER_LLM` forces one; `BONDLAYER_MODEL` overrides the model id. Both,
and the keys, live in `demo/.env` (git-ignored, template in `.env.example`),
read once at import of the `bondlayer` package so the CLI, the Streamlit app,
the fixture recorder and pytest cannot disagree about configuration. A real
environment variable always wins over the file, which is the usual dotenv
convention and the one that makes `OPENAI_API_KEY=... python run_demo.py`
behave as written. No `python-dotenv` dependency: the format we need is a
handful of `KEY=value` lines, and one fewer pip install that can fail on the
morning of the hackathon is worth more than the edge cases it handles.

`BONDLAYER_LLM=off` belongs in the demo machine's `.env`. Every banner names
the env file and the keys it supplied — names only, never values, because the
banners are on a projector.

The Claude Code CLI is installed on this machine and logged in, which is what
made the first real recording possible at all:

    claude -p --model sonnet --system-prompt-file <system> --max-turns 1
           --allowedTools "" --output-format json

`--system-prompt-file` replaces the CLI's own system prompt outright, so the
model sees the agent's system prompt and nothing else of ours; `--max-turns 1`
with an empty tool allowlist makes it a single completion rather than an agent
loop. `BONDLAYER_LLM=off` forces fixtures only, for stage safety.

The OpenAI transport sends the strict, reproducible form first
(`temperature=0`, `max_tokens`) and drops or renames whichever parameter the
API objects to, because support varies by model generation and a hard-coded
table of which model wants what goes stale. Any such fallback is written into
the fixture's usage block: a run that quietly lost `temperature=0` is no
longer the pinned baseline D5 asks for, so it has to be visible rather than
silent. `tests/test_llm_transport.py` covers that loop, since it is the one
piece of the client that would otherwise fail for the first time in front of a
judge.

Every fixture records `source`, `recorded_at`, `latency_ms`, model, token usage
and cost. Every surface in the demo reads that field and says which it is
showing. **All five fixtures in this build are real recordings** (claude CLI,
`claude-sonnet-5`).

The fixture key hashes the model id, so switching provider misses the cache and
re-records rather than silently replaying another model's answers. That is
deliberate: a fixture from a different model is a different experiment, and the
demo must never present one as the other.

## D9.14 — Publishing structured data is necessary but not sufficient **[finding]**

**This is the most important thing the spike learned, and it only came out
because the fixtures were recorded rather than authored.**

The first real recording ranked **Peak in both runs**. With six signed Alpine
benefits in front of it, the model wrote:

> "Peak Supply Co sells the identical Stormline 3L Hardshell for a flat $179,
> which beats Alpine's price even after its verified 5% Gold member discount
> ($199 -> $189.05)."

It read the extension, understood the signatures, and still ranked on list
price. The hand-authored fixture had assumed the opposite. Two distinct causes,
both fixed:

**1. Three of six benefits published no money at all.** `free_returns`,
`free_shipping` and `warranty_extension` carried facts with no dollar figure,
so the model treated them as feature bullets rather than as cost. D8 requires
the published data to be self-describing to a model that has never seen the
schema; "self-describing" turns out to include *self-describing in dollars*
wherever the merchant knows the figure. Alpine now publishes the two it
genuinely knows — the `$9.95` return label fee it waives and the `$12.95`
standard delivery fee it waives — as facts *and* as declared bounds. Both are
stated in `policy.md`, so the policy converter can find them, and both are
ceilings under D4, so this cannot help Alpine inflate anything: the ledger
total is unchanged at $155.26 because the customer's own policy values are
lower than both bounds.

**2. The agent was never asked for effective cost.** The old system prompt said
"consider price, but also anything else the merchant published that materially
affects what the shopper pays or risks" — too weak to overcome price anchoring.
It now says to rank by what the shopper ends up paying and receiving over the
life of the purchase, to use stated dollar figures, and — the load-bearing
clause — that **a merchant which publishes nothing has not proved anything, so
gets credited with nothing**.

Nothing in that prompt mentions BondLayer, the extension or the schema, so the
D8 claim survives: it is what any competent shopping agent would be told to do.
But the honest form of the claim is now narrower than the deck's, and we should
say the narrow one:

> Publishing signed, priced, structured benefit data does not make a
> price-ranking agent change its mind. It makes an agent that is *already*
> reasoning about total cost able to credit you for what you actually offer —
> and it denies that credit to competitors who publish nothing or publish it
> unsigned.

That is a smaller claim, and it is the one that survives contact with a real
model. Anyone demoing this must not say "any LLM agent flips" — say "an agent
reasoning about total cost can finally see the difference, and cannot be fooled
by an unsigned claim."

Both recorded runs are in `data/fixtures/` and readable in full via
`python run_demo.py transcript` or the UI's transcript tab.

## D9.15 — Two guardrails were firing on formatting, not on fabrication **[finding]**

Also surfaced only by real recordings, because a hand-authored fixture is
written to pass its own checks.

**The policy converter's source-quote check rejected all ten drafts.** The
model had quoted the document faithfully; the check compared raw strings, and
`policy.md` writes `**$12.95**` where the quote said `$12.95`. A check that
fires on everything catches nothing, and it would have withheld every record
from signing — a silent, total failure. `_normalise` now deletes markdown
emphasis and collapses whitespace before comparing, so wording, numbers and
punctuation still have to match exactly. Nine of ten drafts now pass the quote
check; the flags that remain are real (a dollar figure attached to a type with
no intrinsic monetary rate; fact names with no unit).

**The explanation faithfulness check rejected a faithful sentence.** The model
ended with "the best value under $200" and was failed for citing $200, which is
the shopper's own budget from their own request. The check now admits
`policy.budget_aud`.

`tests/test_invariants.py` was changed too, and this is worth flagging. One
test asserted that the converter's drafts *contained* a hallucination. That
held only while the fixtures were hand-authored with one planted in it — it was
testing the recording, not the check. It now tests `_validate` directly against
both an invented sentence (must flag) and a faithfully-quoted one that differs
only in markdown (must not flag).

---

## D9.16 — Provider is a swap, not a rewrite **[taken]**

The team is moving to the OpenAI API. Nothing above the transport layer needed
to change to allow it, and that is worth stating explicitly because it is a
claim the design already made and had not yet been asked to honour.

The agent's prompts contain no provider-specific instruction, no tool schema
and no JSON-mode flag — they ask for JSON in plain English and the response is
parsed leniently (`llm.extract_json` strips code fences). D8 already requires
the published catalog data to be legible to *a model that has never seen our
schema*; a model from a different vendor is simply a stronger version of that
test.

So switching provider is:

```bash
export OPENAI_API_KEY=...
rm data/fixtures/*.json
python scripts/seed_fixtures.py
```

**But re-recording is a real experiment, not a formality, and it must be run
before anyone demos on OpenAI.** D9.14 is the reason: the first Anthropic
recording ranked Peak in *both* runs, and the fix was partly in the data and
partly in the agent's prompt. There is no reason to assume a different model
sits on the same side of that line. The specific things to check in the new
recording, in order of how badly each would hurt:

1. **Does the AFTER run pick Alpine?** If not, D9.14 has recurred and the
   prompt or the published dollar figures need the same treatment again.
2. **Does the BEFORE run still pick Peak?** A baseline that accidentally picks
   Alpine destroys the narrative (D5) and is the failure most likely to be
   missed, because it looks like good news.
3. **Does the model refuse to credit Ridgeway's unsigned claim?** This is the
   entire argument for signing. Anthropic's run said so unprompted; that is not
   evidence any other model will.
4. **Does the policy converter still quote faithfully?** D9.15's quote check is
   now formatting-insensitive but still strict on wording. A model that
   paraphrases rather than quotes will have every draft withheld from signing.
5. **Does the explanation pass the faithfulness check?** A model that cites a
   number not in the computed table gets its sentence discarded for a template
   (D9.12), which is the guardrail working, but is worth knowing in advance.

Each of those is directly readable in `run_demo.py transcript` or the UI's
transcript tab. Keeping the current Anthropic recordings somewhere before
deleting them is worth the thirty seconds: a side-by-side of two providers on
the same prompts is a better answer to "did you just tune this until it worked"
than any amount of explanation.

Note also that this remains n = 1 per provider. Two providers agreeing is
better evidence than one; it is still not many samples.

---

## Known weaknesses, recorded rather than hidden

1. **Two-sided adoption.** The merchant-side value stands alone (D8), but the
   full vision still wants agents to verify signatures. Nothing here proves they
   will.
2. **Key distribution** (D9.8) is demo-grade. A real deployment needs a trust
   root that is not "fetch it from the party you are verifying".
3. **Customer policy parameters are invented.** "A return is worth $9 of
   fit-risk to you" is a plausible number, not a measured one. The design
   deliberately never claims a *true* value — only a value under a stated
   policy — but the defaults are still ours.
4. **Catalog cacheability** is genuinely damaged for linked members (D3).
5. **The LLM policy converter will sometimes be wrong.** The approval gate
   contains the blast radius; it does not eliminate the failure.
6. **The result depends on the agent's system prompt, not only on the data**
   (D9.14). Swap in a prompt that ranks on list price and Alpine loses again.
   The mechanism gives an agent something true to reason about; it cannot make
   an agent reason.
7. **n = 1 per run.** Each fixture is a single temperature-0 completion. Nobody
   has run this ten times, across models, or with the merchants reordered in
   the payload. Before Round 2 that is the cheapest remaining experiment and
   the one most likely to embarrass us on stage.
