# BondLayer chat app — the buyer-agent stand-in

Not a consumer product. This is a stand-in for the agent side of the UCP
protocol, so a judge can watch what a real shopping agent would see and do
against `bondlayer/`'s merchant service.

**There is one merchant, one dataset, one valuation library, and this process
owns none of them.** They all live in `bondlayer/`. This app is a client: it
declares capabilities over `UCP-Agent`, fetches `bondlayer`'s catalogue and
benefit extension over real HTTP, and hands both to
`bondlayer.agent.composition.run_request`, which does the verification,
crediting and ranking. Nothing here re-implements any of that.

## Architecture

```
src/agent/
  main.py         FastAPI app, :8001 -- the only service this folder runs
  ucp_client.py   the switch: declares capabilities, fetches, verifies
  llm.py          optional prose over an already-decided ranking (D4)
  static/index.html   two panes (control | BondLayer), one query
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
cp .env.example .env                # OPENAI_API_KEY is optional -- see below
python -m uvicorn src.agent.main:app --host 127.0.0.1 --port 8001
```

Open `http://127.0.0.1:8001/`.

No API key, no wifi required: with `OPENAI_API_KEY` unset, `/query` still
returns a full ranking, credited amounts and a template sentence explaining
the winner (`llm.narrate`, D4 -- prose is optional and never on the ranking
path). Set `BONDLAYER_MERCHANT_URL` if the merchant bound a different port
than :8000 (`run_server.py` moves up automatically if :8000 is busy, and
prints the URL it actually bound).

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
and why) and returned *alongside* the deterministic ranking, never instead of
it (D1). `recommendation` is the one place a model can appear, and it cannot
change `ranked` -- there is no path from `llm.py` back into `run_request`.

## The UI

Two panes, one query: control (no extension declared) on the left, BondLayer
(extension declared) on the right, run side by side from the same submitted
text so the comparison never depends on remembering to ask twice. Per
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

- Ranking used to be a live model call over raw records ("no effective cost
  computed for it", the old `main.py`'s words). It is now
  `bondlayer.agent.composition.run_request` -- deterministic, always, per D4.
- Verification and crediting used to run against this app's own signed
  records and its own `voltway` key (which had drifted from `bondlayer/`'s).
  Both are gone; every verification call resolves the merchant's key live from
  its own `/.well-known/ucp`.
- `_audit()` -- what verified, what was ignored, why -- is the one piece of
  the old design kept, because it is exactly what a shopper-facing UI needs on
  top of a ranking, and it costs nothing extra now that `citations` already
  carries that breakdown per record.
