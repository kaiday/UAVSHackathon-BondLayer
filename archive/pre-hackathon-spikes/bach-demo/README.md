# BondLayer — demo spike

A UCP extension that makes a merchant's non-price value legible, verifiable and
comparable to an AI shopping agent **at the moment the agent decides**.

> ## ⚠ This is not submission code
>
> The rulebook prohibits using code written before 09:00 on 05/09/2026. Round 2
> runs 05–06/09/2026. This was written on 30/08/2026, so **nothing here may be
> copied into the Round 2 repository.**
>
> Its job is to de-risk the design and produce the artefacts that *are*
> permitted as pre-work — the specification, the schema, the synthetic data,
> the prompts and the demo script. Rewrite the implementation on the day.
>
> Full reasoning: [`DECISIONS.md`](DECISIONS.md) D0.

---

## Run it

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt

.venv/Scripts/python.exe run_demo.py web         # THE DEMO -- one screen, two panes, one switch
.venv/Scripts/python.exe run_demo.py compare     # the same run, in the terminal
.venv/Scripts/python.exe run_demo.py transcript  # every prompt and reply, in full
.venv/Scripts/python.exe run_demo.py ingest      # what the catalogue adapter had to fix
.venv/Scripts/python.exe run_demo.py serve       # just the three merchant services
.venv/Scripts/python.exe -m pytest tests -q      # the invariants the pitch depends on
```

No API key needed to *run* it — every model call replays from `data/fixtures/`,
so a stage run never touches the network. Those fixtures are **real recorded
model output**; see "Provenance" below for how they were made and how to
regenerate them.

---

## The demo (v2)

`run_demo.py web` serves one screen: a **shopper chat** beside the **merchant's
console**, with a single switch between them.

```
+- SHOPPER --------------------+- ALPINE OUTFITTERS  console -----------+
| you  Find me a good          |  [ BondLayer  OFF *---  ON ]           |
|      waterproof jacket       |                                        |
|      under $200.             |  What the agent could see    9 -> 96   |
|                              |  Your real offer, legible   0% -> 100% |
| bot  I'd go with Peak, $179  |  Verified value creditable  $0 -> $41.74|
|      ...                     |  Benefits withheld           6 -> 0    |
|                              |                                        |
| RECOMMENDS  peak -> alpine   |  > Is this one lucky run?    5/5       |
+------------------------------+----------------------------------------+
```

The left pane is a **real conversation with a live model** (OpenAI, streamed).
Nothing is sent on load -- the canonical request is the input's placeholder, so
a judge sees an agent waiting to be asked. Follow-ups keep context, so "and
what if it doesn't fit me?" is answered from the signed free-returns record.

Flipping the switch starts a fresh thread and re-asks the last question. Under
it is the same `use_extension` flag as before -- the capability set the agent
declares in its `UCP-Agent` header -- so the "before" is still our own product
pruned by ordinary UCP negotiation, not a strawman.

The chat needs `OPENAI_API_KEY` in `.env`. Everything else (`compare`,
`transcript`, the n=5 tally) still replays from fixtures and runs offline.

Presenter keys: `<-` / `->` flip the switch, `T` opens the transcript, `E`
opens the evidence screen. Full rationale and endpoint list: [`docs/demo-flow-v2.md`](docs/demo-flow-v2.md).

**The headline is the information gap, not the flip.** Every number above is
derived by `src/bondlayer/visibility.py` from the exact payload the agent
received. The recommendation change is the payoff, not the whole proof -- so a
model that ranks on list price no longer sinks the demo.

---

## What it does

`compare` runs the same shopping agent against the same three merchants twice.
The only thing that changes between runs is which capabilities the agent
declares in its `UCP-Agent` header:

```
BEFORE — plain UCP
  Alpine Outfitters  $199.00      Peak  $179.00      Ridgeway  $195.00
  -> recommends: peak
     "…no merchant publishing any figures for delivery, returns, or
      warranty, so price and stated specs are all that differentiate
      them: Peak is cheapest at $179 vs Alpine's $199 (+$20)…"

AFTER — org.bondlayer.benefit_value negotiated
  Alpine Outfitters  $199.00  [6 published benefits]
  -> recommends: alpine
     "Alpine's out-of-pocket cost is $199 - $9.95 (verified 5% Gold member
      discount) = $189.05, with free shipping over $100 (avoiding a $12.95
      fee) and $3.98 of verified points earned… Peak is cheaper on paper at
      $179 but publishes zero verified delivery/returns/warranty terms, so
      that price carries no proven protection, and Ridgeway's '2 year
      warranty' claim is unsigned/unverified so it can't be credited."

  deterministic cross-check:
  * Alpine    list $199.00   adjusted $155.26
        -9.95  Gold member price          [signed]
        -9.00  Free returns (60 days)     [signed]
        -8.00  24 month warranty          [signed]
       -12.00  Free delivery over $100    [signed]
        -2.79  Summit Club points         [signed]
        -2.00  280 points from Platinum   [provisional]
    Peak       list $179.00   adjusted $179.00
    Ridgeway   list $195.00   adjusted $199.00
        +0.00  2 year warranty            [unverified — displayed, never valued]
        +4.00  Uncertainty penalty        [unverified]
```

Both quotes above are verbatim from a real recorded run. `run_demo.py
transcript` prints the system prompt, the full catalog payload and the
complete reply for every call; the UI's transcript tab does the same.

**The "before" is not a strawman.** It is this same product with the extension
pruned by ordinary UCP capability negotiation — which is what every UCP
merchant has today. Alpine genuinely deserves to lose it: it really is $20
dearer.

---

## How it fits together

```
shopper's words
      │
      ▼
  intent extraction (LLM)  ──►  customer policy      the merchant never sees this
      │
      ▼
  agent  ──HTTP──►  three merchant UCP services
      │                    │
      │                    ├─ alpine    catalog.search/lookup + identity_linking
      │                    │            + org.bondlayer.benefit_value  (signed)
      │                    ├─ peak      plain UCP
      │                    └─ ridgeway  declares the extension, publishes no key
      │                                 → its claims arrive unsigned
      ▼
  ┌─ primary path ──────────────┐   ┌─ upgrade path ─────────────────┐
  │ LLM reads the structured    │   │ deterministic TRV library       │
  │ data and decides. No        │   │ ranks; LLM writes prose only,   │
  │ BondLayer code agent-side.  │   │ then a faithfulness check.      │
  └─────────────────────────────┘   └────────────────────────────────┘
```

The **primary path is the claim**: a merchant plugs in once and does better
with agents that have never heard of BondLayer. The library is the upgrade for
agents that want auditable arithmetic instead of model judgement — deliberately
*not* what the headline demo depends on, because assuming agents adopt our
library assumes away the problem (`DECISIONS.md` D8).

---

## Answering the sceptic: `/evidence`

Press `E`, or open <http://127.0.0.1:8080/evidence>. Four questions the
comparison screen cannot answer, each answered by running the real thing rather
than by asserting it:

| Question | Answered by |
|---|---|
| Do you really implement UCP? | **The wire** — real HTTP, headers, activated capabilities, raw bodies, all three merchants, both declarations |
| How can I validate that? | **UCP conformance** — 14 checks against the live services, plus `pytest tests/test_ucp_conformance.py` and a test that deliberately breaks the namespace to prove they can fail |
| What are the agents' system prompts? | **The prompts** — all five verbatim, with a live check that no agent-side prompt mentions BondLayer |
| Is the comparison fair? | **Fairness** — every merchant now has a real policy document; the table shows what each published and signed |
| Where is the "BondLayer agent"? | **Architecture** — there isn't one, by design. BondLayer is a merchant-side *server* plus an optional agent-side library, and the non-agency is the differentiator. |

Every `curl` on the wire tab is runnable as printed:

```bash
curl -s -H 'UCP-Agent: demo-shopper/0.1; capabilities=dev.ucp.shopping.catalog.search,dev.ucp.shopping.catalog.lookup'   'http://127.0.0.1:8101/ucp/catalog/search?q=waterproof+jacket'
```

Add `,org.bondlayer.benefit_value` (and `dev.ucp.common.identity_linking`) to
that header and the same endpoint returns the signed extension block. That one
diff is the whole product.

---

## The two properties worth defending

Both are enforced by `tests/test_invariants.py`, not just asserted.

**1. A merchant can never improve its own position by inflating a number.**
Value is derived from published *facts* under the *customer's* policy; the
merchant's declared figure is applied as a ceiling. Raising it raises a ceiling
that is never reached.

> This test caught the design being wrong. The first implementation derived
> points and tier value *from* the declared bound, so inflating bounds 2× cut
> the adjusted cost from $155.26 to $150.48. The claim was false; the code was
> fixed, not the test.

**2. A bigger unsigned claim costs the merchant more.**
Unverified claims are never valued and are penalised in proportion to what they
ask you to believe. Under a plain value-at-zero rule, a merchant spamming
unverifiable claims lands exactly where an honest merchant claiming nothing
lands — lying would be free.

Together: *inflate a signed number and it is ignored; make a big unsigned claim
and it counts against you.* Both are watchable live via the toggles in the UI's
ledger pane.

---

## Provenance of the model output

Every completion in `data/fixtures/` is **real recorded model output** for the
exact prompt shown beside it — `claude-sonnet-5`, temperature 0, one call each.
Each fixture records `source`, `recorded_at`, `latency_ms`, token usage and
cost, and every surface in the demo reads that field and says which it is
showing. If a hand-authored fixture is ever present, the banner turns red.

Recording uses whichever provider is available (`DECISIONS.md` D9.13), in this
order — the current fixtures came from the third, because this machine had no
key at all:

| transport | trigger | model default |
|---|---|---|
| `openai` | `OPENAI_API_KEY` | `gpt-5` |
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-5` |
| `claude_cli` | `claude` on PATH, logged in | `claude-sonnet-5` |

Keys live in `demo/.env`, which is git-ignored and read once at package
import, so every entry point — the CLI, the Streamlit app, the recorder,
pytest — sees the same configuration:

```bash
cp .env.example .env      # then put your key in it
rm data/fixtures/*.json
.venv/Scripts/python.exe scripts/seed_fixtures.py
```

A real environment variable always wins over `.env`, so
`OPENAI_API_KEY=... python run_demo.py compare --live` does what it looks like.
`BONDLAYER_ENV_FILE` points somewhere else, or empty skips `.env` entirely.
Every banner names the file it read and which keys came from it — never a
value, because those banners go on a projector.

Also settable in `.env`: `BONDLAYER_LLM` forces a transport, or `off` for
fixtures only — **worth setting on the demo machine**, so a stage run can never
hang on the network. `BONDLAYER_MODEL` overrides the model id.

The fixture key hashes the model, so switching provider re-records rather than
silently replaying another model's answers — a fixture from a different model
is a different experiment. If you set a key and the fixtures no longer match,
the banner says so outright (`0 of those were recorded from gpt-5 …`) and any
call that falls back prints `!! NO MODEL ANSWERED` rather than quietly
returning a price-ranked answer that looks like a decision.

`--authored` writes hand-written stand-ins for a machine with none of the
three. Those are **not** evidence of model behaviour and the demo labels them
loudly.

> **Switching to OpenAI: re-record and check the result before demoing.** It is
> a swap, not a rewrite — no prompt mentions a provider — but D9.14 below is
> exactly the kind of thing that can come back with a different model. Check,
> in this order: does AFTER pick Alpine; does BEFORE *still* pick Peak (a
> baseline that accidentally picks Alpine looks like good news and destroys the
> narrative); does the model refuse to credit Ridgeway's unsigned claim. Full
> checklist in `DECISIONS.md` D9.16.

---

## ⚠ What recording the fixtures actually found

The fixtures used to be hand-authored, and they were wrong. Recording them
changed the design in three places. Full detail in `DECISIONS.md` D9.14–D9.15;
the short version, because it is the honest version of the pitch:

**1. The model did not flip.** With six signed benefits in front of it, the
first real run ranked Peak in *both* runs — it read the extension, understood
the signatures, and still ranked on list price. Two causes: three of the six
benefits published no dollar figure at all (so they read as feature bullets,
not as cost), and the agent's prompt never asked for effective cost.

**2. So the claim is narrower than the deck's, and this is the one to make:**

> Publishing signed, priced, structured benefit data does not make a
> price-ranking agent change its mind. It makes an agent that is *already*
> reasoning about total cost able to credit you for what you actually offer —
> and it denies that credit to competitors who publish nothing or publish it
> unsigned.

Do not say "any LLM agent flips". Say "an agent reasoning about total cost can
finally see the difference, and cannot be fooled by an unsigned claim." The
agent's prompt still contains no mention of BondLayer, the extension or the
schema, so D8 survives — but it survives in this narrower form.

**3. Two guardrails were firing on formatting rather than on fabrication.** The
policy converter's source-quote check rejected all ten drafts because the
document writes `**$12.95**` and the model quoted `$12.95`; the explanation
faithfulness check failed a perfectly faithful sentence for citing $200, which
was the shopper's own budget. Both were silent total failures that a
hand-authored fixture could never have exposed, because such a fixture is
written to pass its own checks.

One test had to change with them: it asserted the converter's drafts *contained*
a hallucination, which was testing the recording rather than the check. It now
tests the check directly, against an invented sentence and a faithful one.

**No longer outstanding: n = 1.** This has now been run five times per
condition, with the three merchants presented in a different order each time
(`bondlayer/agent/repeat.py`, `seed_fixtures.py --repeats 5`). The result:

```
BEFORE  5/5 -> peak      AFTER  5/5 -> alpine
```

Unanimous in both conditions, across five orderings -- so the flip is not a
position-bias artefact and not one lucky completion. A repeat with no fixture
is reported as `not recorded` and excluded from the denominator, never counted
as a model vote; `tests/test_flow_v2.py` enforces that, because the price-rank
fallback would otherwise manufacture a confident 5/5 on a machine with no
fixtures at all.

Still open: one model, one temperature, one prompt.

The deterministic path has no such caveat — it involves no model at all.

---

## Layout

```
.env.example                copy to .env; keys and provider choice
DECISIONS.md                every design decision, with alternatives rejected
docs/ucp-findings.md        live UCP spec research — 3 findings contradict the deck
docs/benefit-value-schema.md  the extension spec (the artefact that survives)
docs/deferred-retention-engine.md   what was cut, and how to pick it up
docs/demo-flow-v2.md        the demo flow spec: four decisions, and why
docs/what-we-publish.md     what goes on the wire, why it moves ranking,
                            and how the tier is known -- the walkthrough

src/bondlayer/
  visibility.py             the four information-gap metrics, derived
  schema.py                 benefit_value records, ontology, member context
  signing.py                Ed25519 sign/verify, key pinning
  config.py                 .env loading; a real env var always wins
  llm.py                    fixture-first model client (OpenAI/Anthropic/CLI)
                            + call transcript
  demo_data.py              the three-merchant scenario
  ingest/catalog_adapter.py  messy CSV → conformant UCP
  ingest/policy_converter.py prose → drafts → human approval gate → signed
  ucp/capabilities.py       declaration + server-selects negotiation
  ucp/server.py             catalog.search, catalog.lookup, identity_linking
  agent/policy.py           the customer's valuation policy
  agent/trv.py              deterministic valuation (no model touches a number)
  agent/shopping_agent.py   the mock third-party agent, both paths
  agent/repeat.py           n=5 per condition, payload reordered, tallied
  agent/chat.py             the live multi-turn conversation (not fixture-backed)
  fairness.py               what each merchant offers vs what it put on the wire
  ucp/conformance.py        14 checks, run against the live services
  ucp/wire.py               captured HTTP exchanges + the equivalent curl

app/web/evidence.*          /evidence: wire, conformance, prompts, fairness

app/api.py                  FastAPI behind the v2 page
app/web/                    index.html + app.js + styles.css -- the one screen

tests/test_invariants.py    the claims, as tests
tests/test_flow_v2.py       visibility metrics + "a miss is never a vote"
tests/test_ucp_conformance.py  the UCP checks, incl. one proving they can fail
tests/test_llm_transport.py provider transports, incl. the OpenAI param fallback
tests/test_config.py        .env parsing and precedence
scripts/seed_fixtures.py    fixture recording (API key or claude CLI)
data/merchants/*            deliberately messy native exports + policy prose
```

---

## Known weaknesses

Recorded rather than hidden — full list in `DECISIONS.md`.

1. **Two-sided adoption.** The merchant-side value stands alone, but nothing
   here proves agents will verify signatures.
2. **Key distribution is demo-grade.** Fetching a merchant's key from the
   merchant is not a trust root.
3. **Customer policy defaults are invented.** "A return is worth $9 to you" is
   plausible, not measured. The design never claims a *true* value — only a
   value under a stated policy — but the defaults are still ours.
4. **Catalog cacheability** is genuinely damaged for linked members.
5. **The LLM policy converter will sometimes be wrong.** The approval gate
   contains the blast radius; it does not remove the failure.
6. **The result depends on the agent's system prompt, not only on the data.**
   Swap in a prompt that ranks on list price and Alpine loses again. The
   mechanism gives an agent something true to reason about; it cannot make an
   agent reason. See D9.14 — this is a finding, not a hypothetical.
7. **One model, one temperature.** n = 5 per condition with the payload
   reordered now exists (unanimous both ways), but everything was recorded from
   `claude-sonnet-5` at temperature 0 against a single prompt. No second model.

## Anticipated questions

**"What if every merchant adopts BondLayer?"** Then agents choose on genuine
merit rather than on who happened to publish machine-readable data — which is
better for shoppers and is the point. The current advantage is an early-adopter
one, and we should say so rather than pretend otherwise.

**"Isn't this just prompt-stuffing?"** No: an unsigned claim is never valued
and is penalised. That is the difference between publishing evidence and
publishing marketing copy, and it is demonstrable in the ledger pane.

**"The merchant declares its own benefits — why wouldn't it inflate them?"**
See property 1 above, and watch the inflation toggle do nothing.
