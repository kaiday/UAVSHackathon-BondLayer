# BondLayer chat app — the shopping agent

A conversational buyer agent, so a judge can watch what a real shopping agent
would see and do against `bondlayer/`'s merchant service.

`POST /chat` carries the conversation: it takes the thread so far and either
asks one clarifying question or folds the whole conversation into a single
sentence to send to the merchants. `POST /query` is that search, and can still
be called directly with a complete request. The page uses both -- it talks, and
when it searches it runs `/query` twice, once with the extension declared and
once without, which is the A/B.

**There is one merchant service and one valuation library, and this process
owns none of them.** They all live in `bondlayer/`. This app is a client: it
declares capabilities over `UCP-Agent`, fetches `bondlayer`'s catalogue and
benefit extension over real HTTP, and hands both to
`bondlayer.agent.composition.run_request`, which does the verification,
crediting and reference effective costs. In live mode the buyer model then chooses the order.

## Architecture

```
src/agent/
  main.py         FastAPI app, :8001 -- the only service this folder runs
  ucp_client.py   the switch: declares capabilities, fetches, verifies
  llm.py          shared OpenAI transport, ranking/chat schemas, per-request evidence
  rank.py         shared intent decoder and model-controlled offer ranking
  static/index.html   conversation, identity/value controls, control/BondLayer evidence
```

There is no `src/merchant/` any more, and no `data/`. The merchant is
`bondlayer/`'s server; the catalogue, policies, keys and signed records all
live there too. Deleted, not synced, per Ford's D1 ruling on 12/09 -- two
copies of the same data drift, and a drift makes the comparison meaningless.

## The switch

`ucp_client.agent_header(bondlayer_enabled)` builds the `UCP-Agent` header this
agent declares:

```
on  -> dev.ucp.shopping.catalog.search;dev.ucp.shopping.catalog.lookup;org.bondlayer.benefit_value
off -> dev.ucp.shopping.catalog.search;dev.ucp.shopping.catalog.lookup
```

`catalog.search` is declared in *both* states -- it has to be, or the search
route 406s before negotiation ever reaches the extension. The only thing the
toggle adds or removes is `org.bondlayer.benefit_value`. Same merchant, same
route, same response builder on the other end (`bondlayer/README.md`,
"Where the extension attaches, and why").

## Run it

From the repository root, `./run.sh` (or `.\run.ps1`) starts the merchant
(`bondlayer/run_server.py`, :8000) and this agent (:8001) together. To run this
service on its own:

```bash
cd bondlayer && pip install -e '.[dev]' && python run_server.py &   # :8000

cd buyer-agent
pip install -e ../bondlayer      # the local sibling package
pip install -r requirements.txt
cp .env.example .env                # set a real OPENAI_API_KEY for live mode
python -m uvicorn src.agent.main:app --host 127.0.0.1 --port 8001
```

Open `http://127.0.0.1:8001/`.

The merchant registry starts empty on a fresh install. First visit
`http://127.0.0.1:8000/console/onboarding/` to publish your own catalogue.
Each query discovers the current registry through `GET /onboard/merchants`,
including merchants added since the agent started. Existing uploads are restored.
No bundled demo merchant is used in normal operation. An empty registry returns
`onboarding_required: true`, no winner and a link to onboarding.

Search follows catalogue pagination. A newly uploaded merchant is catalogue-only,
so both comparison panes use its real shelf prices and credit no invented benefits.

Live mode uses OpenAI for intent decoding, conversation and ranking, with visible errors for missing
credentials or failed calls. Configure the root `.env` or this folder's `.env`; the root
configuration takes precedence. `BONDLAYER_MODEL` defaults to `gpt-4o-mini`.
`BONDLAYER_AI_MODE=rules` explicitly selects the offline reference parser, deterministic ranking
and a labelled template. The chat page passes user messages to the reference search in this
mode without calling a model. It is never a silent fallback for a failed live request.

Live queries accept `values_aud` (benefit type to non-negative AUD amount). The page exposes
these as shopper-entered values, defaulting to zero. They control reference effective-cost
figures, not the live model's order. Optional `shopper_id` enables merchant identity linking;
membership comes from each merchant's response. Anonymous live requests assume no membership
or trade-in eligibility. Actual comparisons are sent over HTTP to the merchant's persistent storage and are
summarised in the merchant's Shopping insights page, with supporting evidence per request.
The response's `ai` and `transcript` fields contain
actual model/completion IDs and usage metadata, not a global log of other shoppers' prompts.
Set `BONDLAYER_MERCHANT_URL` if the merchant service uses a different address.

## What `/query` returns

```json
{
  "user_query": "...",
  "bondlayer_enabled": true,
  "ucp_agent_header": "dev.ucp.shopping.catalog.search;...;org.bondlayer.benefit_value",
  "constraints": [{"text": "...", "kind": "HARD"}],
  "steps": [{"phase": "intent", "outcome": "ok", "summary": "...", "detail": {}}],
  "ranked": [{"merchant": "voltway", "sku_id": "VOL-0031", "shelf_price_aud": "1142.96",
              "credited_aud": "155.00", "effective_cost_aud": "987.96",
              "citations": [{"benefit_type": "free_returns", "credited": "45.00", "cited": true, "why": "..."}]}],
  "winner": { "...": "the top of ranked" },
  "flipped": true,
  "recommendation": "one paragraph, model or template",
  "merchant_decodes": {"kind": "merchant_decode", "outcome": "ok", "summary": "2 of 3 merchants decoded the request themselves; ...",
                       "merchant_decodes": [{"merchant": "voltway", "negotiated": true,
                                             "decoded_intent": {"constraints": [...], "assumptions": [...], "clarifying_question": null},
                                             "proposals": [{"sku_id": "VOL-0001", "title": "...", "price": "1455.00", "resolved": [...], "unsatisfied": []}],
                                             "agreement": {"clauses": [...], "agreed": 4, "total": 4}}]},
  "audit": [{"sku_id": "...", "verified_count": 2, "verified": [...], "ignored_count": 1, "ignored": [...]}],
  "transcript": []
}
```

`merchant_decodes` is the merchant's side of the decode. With the toggle on,
`UCP-Agent` also declares `org.bondlayer.intent_match`, and after `run_request`
has finished the agent sends the shopper's sentence verbatim to every merchant
(`POST /{merchant}/ucp/intent/propose`, via `ucp_client.make_proposer`) and
records what each one understood and proposed --
`bondlayer.agent.merchant_decode.run_with_merchant_decode`, one appended trace
step, whose detail this key is (plus the step's `outcome` and `summary`). Per
merchant: whether it negotiated the capability (CityCircuit never does, and
answers 406), its `decoded_intent` block verbatim, its first five proposals
with the resolver's per-clause notes, and a clause-by-clause agreement check
against `constraints` above. With the toggle off the sentence is not sent at
all and the step says so, DEGRADED. Nothing in `ranked` is computed from it.

`order` closes the loop (FPT's step 5). After the ranking is decided the agent
checks out `winner` -- `POST /{merchant}/ucp/checkout` via
`ucp_client.make_checkout`, one unit of the winning SKU, citing exactly the
record ids it relied on (verified records that moved the effective cost or
answered a clause; an unverified record is never sent) --
`bondlayer.agent.close_loop.close_loop`, one appended trace step, whose detail
this key is (plus `outcome` and `summary`): the `request` body as sent, the
merchant's `order` object verbatim (`order_id`, `status:
confirmed_awaiting_payment`, `line_items`, `subtotal`, `payment: {status:
out_of_scope}` -- no funds move), and `honoured_benefits`, the merchant's
verdict on every cited id. `dev.ucp.shopping.checkout` is base UCP and is
declared in both toggle states, so the control pane places a plain order on
the same route and `honoured_benefits` is `null` there. The page renders this
as the receipt at the bottom of each pane, the last thing shown, and derives
nothing from it: the tick or cross is the merchant's `honoured`, the sentence
is the merchant's `reason`. A merchant that cannot be reached at checkout is a
DEGRADED step with `order: null`, never a 500 -- the ranking above is not the
checkout's to lose.

`steps`, `ranked` and `flipped` are `bondlayer.agent.trace.AgentRun` rendered
as JSON -- the same object `bondlayer/scripts/trace_run.py` prints as text.
`audit` is kept from the original P6 design (what verified, what was ignored,
and why) and returned *alongside* the ranking, never instead of it (D1).

In live mode `ranked` is in the **model's** order. `run_request` still computes an effective
cost for every offer and it is still reported per offer, but it no longer
decides anything here: `rank.apply_ranking` reorders `run.ranked` in place, so
`winner` -- and the checkout that follows it -- is the model's pick. Where the
model and the arithmetic disagree, the offer card shows both, and that
disagreement is visible. `ranking_source` identifies `model` or explicit `rules` mode.
The `ai.intent` and `ai.ranking` fields carry completion metadata; `request_id` links to the
saved report. Offers are identified by both merchant and SKU so store-local codes cannot collide.

## The UI

A chat thread with the prompt bar pinned to the bottom edge, and an **Evidence**
widget beside it holding everything that is not the answer: the model's decode,
the trace, each merchant's own reading, every offer's signed records and clause
resolution, the checkout receipt, intent completion metadata and this request's ranking calls.
A toggle at the top of that widget switches between the BondLayer
run and the control, which are the same sentence asked twice -- so the
comparison never depends on remembering to ask twice. Per
published record: three visually distinct states -- signed and priced
(green, cited, credited $X), signed and unpriced (purple, cited, verified,
$0 -- a values claim, worth stating but never a price), and unsigned (grey,
shown, never cited, with the reason). A SERVICE or VALUES constraint with no
citation to answer it carries `← no catalogue attribute answers this`.

Between the trace and the ranking sits **"Merchant's own reading"** -- one
dashed block per pane, rendered from `merchant_decodes` and deliberately
styled like neither an offer card nor the bundle frame so it cannot be read
as a second ranking. Per merchant: a badge saying whether it negotiated
`org.bondlayer.intent_match`, the merchant's own constraint rows (`kind ·
clause · interpretation`) each marked ✓/✗ against the agent's decode, the
merchant's plain-sentence assumptions, its clarifying question when it asked
one, and its first proposal with the same clause-by-clause resolver lines the
ranked offers use, so the two seats look identical on screen. In the control
pane the block says the sentence was not sent. The ranking below it never
reads this block: it is what the merchant understood and proposed; the ranking
is what the agent verified and decided.

**Kept as a single static page, not React/Vite.** An unwired React/Vite
scaffold shipped in `src/ui/` from an earlier phase; every launch path
(including the deleted `launch.sh`/`launch.ps1`) actually pointed a browser at
this agent's own no-build fallback page once the Vite dev server needed `npm
install`. Rebuilding the React app against the new response shape, inside this
brief's time box, was not worth it for a UI no launch script used -- so it was
removed rather than left stale beside a page that works. One file, no build
step, no second thing to keep in sync.

## What changed from the earlier P5/P6 design

- Verification and reference effective-cost arithmetic live in
  `bondlayer.agent.composition.run_request`. The live buyer model orders the verified
  offers; the historical rules-mode path retains deterministic ranking.
- Verification and crediting used to run against this app's own signed
  records and its own `voltway` key (which had drifted from `bondlayer/`'s).
  Both are gone; every verification call resolves the merchant's key live from
  its own `/.well-known/ucp`.
- `_audit()` -- what verified, what was ignored, why -- is the one piece of
  the old design kept, because it is exactly what a shopper-facing UI needs on
  top of a ranking, and it costs nothing extra now that `citations` already
  carries that breakdown per record.
