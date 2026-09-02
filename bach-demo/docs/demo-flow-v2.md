# Demo flow v2 — the spec

Status: agreed 2026-09-01. Supersedes the four-tab Streamlit flow for the
Round 2 demo. The engine is unchanged; this is a flow and presentation spec.

> As with everything in `demo/`, this document is **permitted pre-work** and the
> implementation under it is **not** (D0). The spec, the metric definitions, the
> prompts and the recorded fixtures survive into Round 2. The code is rewritten
> on the day.

---

## Why the old flow was replaced

Four findings, in the order they hurt:

1. **No human in the frame.** The pitch opens with a person asking for a
   jacket. The demo opened with a `UCP-Agent` header. A judge saw only engine
   internals — no shopper, no merchant, no moment of plugging in.
2. **Tabs organised by our concerns.** *Plug · comparison · ledger · transcript*
   is an engineering decomposition. The narrative — customer asks, agents
   compete, our merchant wins, here is why it is trustworthy — was split across
   tabs 2 and 3 and told twice with two different answers.
3. **Two verdicts, one question.** The LLM path and the TRV path each named a
   winner. Honest, and rhetorically fatal: a judge cannot tell which one is the
   product.
4. **The money shot rested on n = 1** of a model that, on the first real
   recording, did not flip at all (D9.14).

## The four decisions

| # | Decision | Chosen |
|---|---|---|
| 01 | Whose screen | Split: shopper chat beside merchant console |
| 02 | Which verdict | The model decides; the ledger is the audit drawer |
| 03 | The money shot | Reframe as an information gap **and** record n = 5 |
| 04 | The stack | FastAPI plus one hand-built page |

---

## 1. The screen

One page, two panes, one switch.

```
┌─ SHOPPER ─────────────────────┬─ ALPINE OUTFITTERS · console ──────────┐
│ 🧑 Find me a good waterproof  │  [ BondLayer  OFF ●───  ON ]           │
│    jacket under $200.         │                                        │
│                               │  What the agent could see   9 → 96     │
│ 🤖 I'd go with Peak — $179.    │  Your real offer, legible   0% → 100%  │
│    It's the cheapest and the  │  Verified value creditable  $0 → $41.74 │
│    specs match.               │  Benefits withheld           6 → 0     │
│                               │                                        │
│                               │  ▸ the payload we sent                 │
│                               │  ▸ show the arithmetic (ledger)        │
└───────────────────────────────┴────────────────────────────────────────┘
```

**Left pane — the shopper.** A **real, live, multi-turn conversation** against
OpenAI (`src/bondlayer/agent/chat.py`), streamed token by token.

Nothing is sent on load. The canonical request is the input's **placeholder**,
offered alongside three follow-up suggestions, so the first thing a judge sees
is an agent waiting to be asked rather than an answer that already happened.
The shopper types; the agent answers; follow-ups keep context ("and what if it
doesn't fit me?" gets answered from the signed returns record).

This is the one place the demo is deliberately *not* fixture-backed. A fixture
cannot answer a question nobody recorded, and "ask it anything" is the moment
that proves the data is real rather than staged. `compare`, `transcript` and
the n=5 tally stay fixture-replayed, so the pinned baseline (D5) is untouched.

The chat has its own prompt (`CHAT_SYSTEM`) because the scripted path demands
JSON only. It still never mentions BondLayer, the extension or the schema —
`tests/test_flow_v2.py` asserts that, because a prompt that names us is a demo
telling the model the answer. The model ends each reply with a
`RECOMMENDATION: <merchant_id>` line, which is stripped before display and used
to drive the console.

**Right pane — the merchant console.** Alpine's own view of the same event. Four
live numbers (below), then two disclosure drawers. This pane is the product;
the left pane is the reason it matters.

**The switch.** `BondLayer OFF → ON` is the only control that matters on stage.
Flipping it starts a fresh thread and re-asks the last question, because a
capability change means the agent must re-query the merchants and the old
thread is grounded in a catalog that no longer exists. One gesture, one live
call, both panes change. Under the hood it is exactly the old
`use_extension` flag — the capability set the agent declares in its `UCP-Agent`
header — so the "before" remains our own product pruned by ordinary UCP
negotiation, not a strawman (D5).

**Presenter affordances.** `→` / `←` flip the switch, `T` opens the transcript
overlay, `E` opens the evidence screen, `Esc` closes the overlay. Typing goes to the composer, so no shortcut may be a
bare letter that a shopper might type — the keydown handler returns early
whenever the focus is in a field.

### Screens that are no longer top-level

Ingest, the approval gate, and the transcript keep every capability they had,
but move out of the primary flow:

- **Ingest + approval gate** → a `/merchant/onboarding` route, shown only if
  asked. It is a *setup* story, and the demo has thirty seconds.
- **Transcript** → the `T` overlay and the `/transcript` route. Unchanged in
  substance: every prompt, every completion, every provenance field.
- **Adversary toggles** (Ridgeway escalation, Alpine bound inflation) → inside
  the ledger drawer, where they belong, because they are claims about the
  arithmetic.

---

## 2. The verdict

**The model's sentence is the answer.** It is rendered as the assistant's reply
in the left pane, verbatim, with its provenance chip attached. This is the
claim the pitch actually makes: a third-party agent that has never heard of
BondLayer, reasoning for itself, changes its recommendation.

**The ledger is a drawer, never a rival.** `▸ show the arithmetic` opens the
deterministic TRV valuation *underneath* the model's answer, framed as
verification, not as a second opinion:

> The agent said $189.05 effective. Here is that number, computed without a
> model touching it.

Consequences the implementation must honour:

- The ledger drawer never displays its own "Agent recommends" metric. It shows
  line items and totals only. Exactly one winner appears on the page.
- If the two paths ever disagree, the drawer says so explicitly rather than
  hiding it — a disagreement is a finding, and the page has room for it in a
  single amber line. It must not silently show two winners.
- D8 is unaffected: the primary path still involves no BondLayer code on the
  agent side.

---

## 3. The money shot

Two changes, both required. The reframe makes the claim survivable; the repeats
make it evidence.

### 3a. The claim is an information gap

The headline number is no longer *who won*. It is **what the agent could see**.

Four metrics, computed by `bondlayer.visibility` from the exact payload sent to
the model — not narrated, derived:

| Metric | Off | On | Definition |
|---|---|---|---|
| `fields_visible` | 9 | 96 | Machine-readable claims about Alpine's offer in the payload (every scalar leaf; a scalar list counts once) |
| `offer_legible_pct` | 0% | 100% | Share of Alpine's published benefit records that reach the agent |
| `verified_value_aud` | $0.00 | $41.74 | TRV-valued lines whose signature verifies — signed only, never provisional |
| `benefits_withheld` | 6 | 0 | Records held back by capability negotiation |

Counting top-level keys instead would report 6 → 8, which is true and useless:
`published_benefits` is one key whether it holds one record or twenty. What
negotiation changes is the number of separate facts the agent can reason about.

The recommendation flip is then presented as the *payoff* — "and so the agent
changes its pick" — rather than as the entire proof. A model that ranks on list
price no longer sinks the demo, because the gap is still real and still
measured.

The claim, in the words we will use on stage:

> Publishing signed, priced, structured benefit data does not make a
> price-ranking agent change its mind. It makes an agent that is *already*
> reasoning about total cost able to credit you for what you actually offer —
> and it denies that credit to competitors who publish nothing, or publish it
> unsigned.

### 3b. n = 5 per condition

`bondlayer.agent.repeat` runs the ranking call five times per condition and
displays the tally.

- **Variation is the payload order, not a nonce.** Each repeat presents the
  three offers in a different permutation. This tests the thing most likely to
  embarrass us — position bias — and it changes the prompt, so each repeat gets
  its own fixture key for free. No change to `llm._key`.
- Permutations are fixed and seeded (`itertools.permutations`, first five of
  six, in a stable order), so the run is reproducible and the fixture set is
  finite: 10 new `rank-*.json` fixtures, 5 per condition.
- The tally is rendered honestly. `5/5` is displayed as `5/5`; `3/5` is
  displayed as `3/5` with the dissenting runs one click away. **A split vote is
  shown, never rounded.**
- Fixture-miss behaviour: any repeat with no fixture and no transport is
  reported as `not recorded`, and the tally reads `4/4 recorded` rather than
  silently counting a price-ranked fallback as a model vote.

Recording: `python scripts/seed_fixtures.py --repeats 5`.

---

## 4. The stack

```
demo/
  app/
    api.py              FastAPI: static mount + JSON and SSE endpoints
    web/
      index.html        the one screen
      app.js            SSE consumer, switch, drawers, keyboard
      styles.css        tokens, both themes
  src/bondlayer/
    visibility.py       NEW — the four information-gap metrics
    agent/repeat.py     NEW — the n=5 harness and tally
    (everything else unchanged)
  scripts/seed_fixtures.py   --repeats N added
```

## 5. The evidence screen (`/evidence`)

The comparison screen answers *what happened*. It cannot answer the four
questions a sceptical judge actually asks, so those get their own screen,
one keypress away (`E`) and never in the way of the 30-second money shot.

**"How do we know you really implement UCP?"** — *The wire* shows the actual
HTTP: request headers including `UCP-Agent`, the capability set the merchant
activated in reply, the raw JSON body, for all three merchants under both
declarations. Every exchange carries the equivalent `curl`, because the
strongest answer to that question is a judge running the command themselves and
getting the same bytes.

**"How can that be validated?"** — *UCP conformance* runs
`bondlayer.ucp.conformance` against the live services on every page load: 14
checks covering namespace correctness, versioning, `extends`, intersection
semantics, extension pruning to a fixpoint, `406` on an un-negotiated
capability, byte-identical plain-UCP responses, key publication, and the
deliberate absence of cart/checkout/payments. The same checks run in
`tests/test_ucp_conformance.py`, where a second test deliberately squats
`dev.ucp.*` to prove the suite can go red.

**"What are the system prompts?"** — *The prompts* shows all five verbatim, each
with what it is used for and why it says what it says, plus a live check that no
agent-side prompt contains `bondlayer`, `benefit_value` or `org.bondlayer`. The
D9.14 story — the first prompt failed, and we narrowed the claim rather than
naming ourselves in it — is told here rather than buried in DECISIONS.md.

**"Is the comparison fair?"** — *Fairness*, below.

**"Where is the BondLayer agent?"** — *Architecture* answers that there isn't
one, and that this is the position rather than a gap. Every row is labelled
real / simulated / mocked.

Round 1's summary described a *middle layer*, a *plug*, a *universal adapter*,
something that *implements UCP* and is *readable* — five passive descriptions —
but two mermaid nodes were labelled "Bondlayer agent". Those labels contradicted
the document's own prose and have been corrected to **service**
(`round1/bondlayer-summary.md`, with a note recording the original wording).

The screen then makes the non-agency the argument:

> In a room full of agents, we are building the thing agents read.

A publishing layer has no per-comparison latency budget, no real-time dependency
at the moment of decision, and no privacy story to defend — because the merchant
never learns it was compared. When a judge asks *"so what does it decide?"*, the
answer is **nothing, by design**, followed by the costed reason: the deciding
version (`org.bondlayer.retention_request`) is designed and deliberately
deferred (D6), because deciding at comparison time buys a second protocol flow,
a policy engine, a privacy surface, and Australia's automated-decision
transparency obligations commencing 10 December 2026.

And the honest counterpoint, also on screen: the one place an LLM agent *is*
used is merchant onboarding, where it drafts benefit records from prose and a
human approves before anything is signed. Agent where it is cheap and
reversible, never in the serving path.

### Fairness: the competitors now have real policies

The demo used to give Alpine a `policy.md` and its competitors nothing but a
CSV. That is not a legibility story, it is a merit story, and a judge would have
read it as stacking the deck.

`data/merchants/peak/policy.md` and `ridgeway/policy.md` now describe genuine,
competitive terms — Peak has free delivery over $99, 30-day returns; Ridgeway
has a 2-year warranty and flat-rate delivery. Neither reaches an agent, because
neither runs BondLayer. The table on screen:

| Merchant | Real policy | Published to agents | Signed | Stranded in prose |
|---|---|---|---|---|
| alpine | yes | 6 | 6 | $0.00 — all of it published |
| peak | yes | 0 | 0 | $9.95 |
| ridgeway | yes | 1 | 0 | $8.00 |

So the claim sharpens from *"Alpine offers more"* to *"Alpine can prove what it
offers, and the others cannot"* — which is a claim about the protocol rather
than about the merchants.

`policy_facts.json` beside each competitor policy is hand-extracted for this
table. It is never served by a merchant service and never reaches the agent,
and the file says so in its own `_comment`.

---

### Endpoints

| Method | Path | Returns |
|---|---|---|
| `GET` | `/` | the page |
| `GET` | `/api/scenario` | merchants, member, canonical request, provenance banner |
| `POST` | `/api/chat` | SSE: a live conversation turn (offers, visibility, tokens, verdict) |
| `GET` | `/evidence` | the evidence screen |
| `GET` | `/api/evidence` | conformance report, captured wire, prompts, fairness |
| `GET` | `/api/ledger?…` | TRV valuation, with adversary toggles as query params |
| `GET` | `/api/repeats?extension=…` | the n=5 tally |
| `GET` | `/api/scoreboard?n=…` | win/loss over both conditions, plus priced loss attribution |
| `GET` | `/onboard` | the merchant onboarding screen |
| `GET` | `/api/onboard?merchant=…` | raw export, adapter issues, model drafts, live wire state |
| `POST` | `/api/onboard/sign` | the approval gate: signs only the ids a person ticked |
| `GET` | `/api/transcript` | every `CallRecord` this session |

**SSE event sequence** for `/api/chat`, which is also the on-stage beat sheet:

```
event: offers       [ {merchant, price, benefit_count, signed_count}, … ]
event: visibility   { fields_visible, offer_legible_pct, verified_value_aud, benefits_withheld }
event: payload      { chars, benefit_records, text }
event: token        { text }          ← repeated; the reply, streamed live
event: replace      { text }          ← the held-back RECOMMENDATION line, stripped
event: verdict      { winner, explanation, call, trv_winner, agrees }
event: done         { calls }
```

There was also a `GET /api/run` that replayed a recorded completion in chunks
so a fixture "felt" like a run. It was removed once the chat went live: nothing
called it, and a page that fakes streaming next to a pane that streams for real
is a liability on stage. The reproducible fixture path still exists, in the
place it belongs — `run_demo.py compare` and `transcript`.

### Why not Streamlit

Streamlit reruns the whole script on every widget change, has no SSE, and no
chat primitive that can stream a live completion convincingly. The switch — the
single most important gesture in the demo — would blink the entire page.

The four-pane Streamlit app was deleted once this page had run end to end, per
the condition above. Nothing it showed was lost: the ledger and transcript are a
drawer and an overlay here, and the ingest findings are `run_demo.py ingest`.

---

## What is explicitly out of scope

- Any change to `schema.py`, `signing.py`, `trv.py`, `policy.py`, or the UCP
  server. The engine is not the problem.
- Any change to the ranking, intent or explain **prompts**. Changing a prompt
  invalidates every recorded fixture and re-opens D9.14.

## Definition of done

1. `python run_demo.py web` serves the page with no console errors, both themes.
2. The switch flips both panes in under a second, from fixtures, offline.
3. Every number on the page traces to a function in `src/bondlayer/`, not to a
   literal in the HTML.
4. `--repeats 5` records 10 fixtures; the tally renders from them; a deliberately
   deleted fixture shows `not recorded` rather than a fabricated vote.
5. `pytest tests -q` passes, including new tests for `visibility` and `repeat`.
6. Nothing on the page claims a live model call when a fixture answered.

---

## 6. The re-plan (02/09/2026) — the values that were built and not shown

The v2 screen proved one comparison very well and left four things the codebase
already does completely invisible. Two of them went missing when `app/ui.py`
was deleted and its surfaces were never rebuilt; two had never had a surface at
all. This section records what was added and why each addition is a *value*
rather than a feature.

| Gap | Where the code was | Where it is now |
|---|---|---|
| Visibility diagnosis — "agents cannot match this product" | `ingest/catalog_adapter.py`, CLI only | `/onboard` step 1 |
| The approval gate — model drafts, a person signs | `ingest/policy_converter.py`, CLI only | `/onboard` steps 2–3 |
| The shopper's own valuation | `/api/ledger` accepted four params **nothing ever sent** | sliders in the ledger drawer |
| Why the merchant lost, over time | did not exist | `/api/scoreboard`, first drawer |

### `/onboard` — the merchant's first hour

Three steps in the order a merchant experiences them: hand over the export you
already have, hand over the policy page you already publish, then approve. It
answers the question the money shot cannot: *what do I actually have to do?*

The step boundaries are the argument. Step 1 is deterministic because a
hallucinated price is worse than a missing one. Step 2 is the one place a model
is genuinely necessary, and every claim it drafts must cite a sentence the
document actually contains. Step 3 is the guardrail, and it is structural
rather than statistical — `sign_approved()` takes only records a person ticked,
and `policy_converter` has no access to a key at all.

Nothing on the page is authored: the issues come from the adapter, the drafts
from a real converter run, and each returned signature is verified back through
a fresh `KeyRing` on the server before the page ever sees it. On the recorded
run that is 3 products mapped, 1 issue, 10 drafts, 8 of them flagged by the
validator, and 0 signed until somebody clicks.

### The scoreboard — the only standing question in the demo

Everything else here answers "did BondLayer change the outcome of *this*
comparison?". No merchant renews a subscription for that. The scoreboard
answers the question they will actually ask every month:

> I lost. What did I lose to, and is any of it something I can fix?

It ranks ten times — five per capability state — then names the published
benefits the agent was never handed and prices each one through the same
deterministic ledger. On the recorded run: **0 of 5 won with the extension off,
5 of 5 with it on, $41.74 of signed value stranded across five benefits.**

Two disciplines carried over deliberately. A run that fell back to list-price
ranking is reported and never counted, as in `agent/repeat.py`. And the
recoverable total counts **signed** lines only — the provisional line is listed
on screen and excluded from the sum, because a figure labelled *recoverable*
must not contain value that cannot be proved. `tests/test_scoreboard.py` holds
both claims.

### The shopper's four numbers

`/api/ledger` has always accepted `fit`, `ship`, `warranty` and `penalty`. The
page never sent them, so the shopper half of the design — *the customer's
valuation policy is derived from what they said, not configured by us* — was a
server-side feature with no way to reach it. The sliders are now beside the
ledger, styled apart from the adversary toggles below them, and captioned with
the property that makes them matter: **no merchant is ever sent these.** Nothing
on the wire carries a shopper preference, and `/evidence → The wire` is where a
sceptic checks that.

A useful thing happens when the delivery slider is pushed to $30: Alpine's
adjusted cost moves less than a dollar, because the published bound is a
$12.95 ceiling. The invariant is visible without anyone narrating it.

---

## 7. Feedback pass (02/09/2026)

Four changes, from a review of the re-planned demo.

### Light, and one palette

Every colour is now a token on `:root` in `styles.css`; the two other
stylesheets had hardcoded four status colours between them, which is why the
first pass produced a half-dark page. `/static` and the four routes are served
`Cache-Control: no-store` — the theme change rendered mixed on a browser that
had seen the old stylesheet, on a machine where the files were entirely
correct, and a stale asset on stage is not worth a few kB of caching.

### The merchant uploads their own files

`POST /api/onboard/upload` accepts a product CSV and a policy document and runs
the whole pipeline on them. `adapt_csv_text` is the new entry point, so an
upload never touches disk — a merchant's catalogue is their commercial data,
and reading it from memory means the demo can accept a real export without
acquiring a copy of it. Uploads live in process and are forgotten on restart.

Verified on a fabricated third-party retailer: 2 products mapped, 3 issues
found (`POA` price → invisible, short barcode → unmatchable, "waterproof-ish" →
incomparable), 3 claims drafted from the uploaded policy with the $11.50 return
fee correctly extracted and correctly flagged.

**One constraint worth stating plainly:** an uploaded policy is a document no
fixture was ever recorded for, so step 3 needs `run_demo.py web --live`. The
error message says so rather than printing a fixture hash.

### Four steps, one at a time

`/onboard` is now a wizard with a progress rail. One step visible, one button
naming the next action. The earlier single scrolling page read as a report
about a pipeline rather than as something the reader was being asked to do.

### The console got a lever the merchant can actually pull

This was the sharpest note: *"as a merchant I don't know what to do, though the
final incentive is to improve my ranking."* Correct, and the diagnosis holds
for **both** panels that were there. The adversary toggles are claims about our
arithmetic. The valuation sliders are the *shopper's* preferences. A merchant
can act on neither.

`GET /api/levers` now lists the merchant's own published terms with what the
ledger credits each one, and `/api/ledger?publish=…` re-prices with only the
ticked ones. The panel reports position, effective cost and the gap to the
leader:

```
all six published     1st of 3 · $155.26 effective
three unticked        2nd of 3 · $186.21 · $7.21 behind peak
none published        2nd of 3 · $199.00 · $20.00 behind peak
```

The two old panels stay, relabelled for what they are — *"the shopper's side —
not yours to set"* and *"can a merchant game this? — try it"*.

**A bug this surfaced.** Both the levers and the adversary toggles work by
reconfiguring the live merchant services and querying them over real HTTP,
which makes the mutation global. Without a restore, unticking a lever stripped
those benefits from `/api/chat` and `/api/scoreboard` as well — the money shot
would have quietly answered a question nobody asked, and it would have looked
like a model result rather than a leaked toggle. The reconfiguration is now a
context manager with a `finally`, pinned by
`test_ledger_toggles_do_not_leak_into_the_rest_of_the_demo`.

### A homepage

`/` is now a front door with two cards; the two-pane screen moved to `/demo`. A
merchant and a judge want different screens and sending both to the money shot
served neither. The one dollar figure on it is derived in `/api/scenario`, not
typed into the HTML.

---

## 8. Feedback pass two (02/09/2026)

### The model-name bug, and the variable that caused it

The live chat failed with `404 — the model claude-sonnet-5 does not exist`.
The chat is hardwired to OpenAI; `BONDLAYER_MODEL` had been set to
`claude-sonnet-5` so the *ranking fixtures* would hit, and `stream_openai` read
that variable unconditionally. One variable was doing two jobs across two
providers.

`llm.chat_model()` now honours `BONDLAYER_MODEL` only when the configured
transport actually *is* openai, with `BONDLAYER_CHAT_MODEL` as an explicit
override. `BONDLAYER_MODEL` means "the model for the configured transport", and
the live chat is not that transport unless it is OpenAI.

**The reason the override existed at all is also fixed.** Seeding gpt-5
fixtures had been failing because `_call_openai` sized `max_tokens` for the
answer, and a reasoning model spends that budget thinking first — returning an
empty string, or on newer API versions a 400. That is precisely how the repo
acquired two empty gpt-5 fixtures and then silently ranked on list price. The
non-streaming path now asks for `reasoning_effort: "low"` and real headroom,
escalating the budget on the specific 400 and dropping either parameter if the
model rejects it.

All 13 gpt-5 fixtures are recorded, **0 empty**, and `python run_demo.py web`
works with no environment overrides: 5/5 peak off, 5/5 alpine on, live chat
answering from gpt-5 and agreeing with the ledger.

### Step 2 became work rather than a diagnosis

The old screen listed parser events. A diagnosis on its own is a bill: it tells
a merchant they have a problem without telling them what to do. The new
`ingest/remediation.py` splits every finding in two.

**What can be done mechanically, we did.** Prices written `AUD 129.00`,
ratings written `20K mm H2O`, weights written `1.2kg`, size lists written
`"S, M, L"` — all unambiguous, all normalised, nobody retypes them.

**What needs a person becomes one instruction, not one line per row.** Ten
products missing a barcode is *one* to-do with ten products attached, because
that is how the work will actually be done.

The screen is now a scorecard, two columns (*your to-do list* / *already done
for you*), and a preview of the corrected catalogue with changed cells
highlighted — plus `GET /api/onboard/fixed.csv` to download it.

Three things that are load-bearing, and tested in `tests/test_remediation.py`:

- **A row we could not map still appears**, marked `ACTION REQUIRED`. Dropping
  it would return a file that looks clean and is quietly shorter than the one
  the merchant gave us.
- **We never invent a value a human has to supply.** A fabricated GTIN would
  match the wrong product, which is worse than an absent one.
- **Every to-do is either theirs or ours**, never in between.

Two bugs this surfaced, both caught by looking at the output rather than the
code. The waterproofing group was filed under "normalised — already applied"
while pointing at the one row where normalising had *failed*: exactly
backwards, since everything in `issues` is by definition unresolved. And
`changed_cells` compared an intermediate split rather than the rendered cell,
so `S/M/L` → `S|M|L` reported as unchanged while the reader could plainly see
it move.
