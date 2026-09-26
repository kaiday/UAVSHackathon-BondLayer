# BondLayer — merchant service

A retailer's existing catalogue export and policy documents, published as UCP
data an AI shopping agent can read, verify and value **while it is still
comparing merchants**.

Merchants share one protocol implementation and onboard their own catalogues. For the
current user journey and live OpenAI setup, see the [root README](../README.md).

## Run it

```bash
cd bondlayer
pip install -e '.[dev]'   # runtime deps + pytest; note the trailing dot
python run_server.py      # :8000, or the next free port if it is busy
```

Or, from the repository root, `./run.sh` (or `.\run.ps1`) does the venv,
the install and the start in one command.

Pass a port if you want a specific one: `python run_server.py 8123`, or set
`PORT`. If something else already holds :8000 the launcher moves up and prints
the URL it actually bound -- so you never end up reading a stale build on the
port you expected.

Normal operation starts empty and restores uploaded data. Configure `OPENAI_API_KEY` and
`BONDLAYER_AI_MODE=openai` in the root `.env` for real intent decoding, merchant assistance
and policy extraction. Approved policy records are signed with locally stored merchant
keys and published through the same catalogue and checkout routes. Use the console's
Benefit records page for upload, review and publication; Settings can test the API connection.

The Voltway/CityCircuit/NorthGear examples below describe historical synthetic data.
Enable `BONDLAYER_TEST_DATA=1` and `BONDLAYER_AI_MODE=rules` explicitly to reproduce that
offline reference mode. It is separate from your real merchant uploads.

```bash
pytest            # network-free regression tests
```

## What an agent sees

```bash
# the profile it reads first
curl localhost:8000/voltway/.well-known/ucp

# plain UCP — what every agent in the world does today
curl "localhost:8000/voltway/ucp/catalog/search?category=laptop&max_price=1500"

# an agent that declares the extension
curl -H "UCP-Agent: dev.ucp.shopping.catalog.lookup;org.bondlayer.benefit_value" \
     "localhost:8000/voltway/ucp/catalog/lookup?sku_id=VOL-0034"
```

The second and third calls hit the same route and the same response builder.
The third one carries `extensions` and the second does not — **not because of
a branch anywhere in the code**, but because capability negotiation pruned an
extension the agent never declared. An agent that declares nothing gets valid,
conformant UCP.

That property is what makes the control merchant honest. CityCircuit is this
server with the extension absent from its manifest, not a second
implementation. If it were a second implementation the comparison would prove
nothing (assumption A2).

| Merchant | Role | Extension | Readiness |
|---|---|---|---|
| Voltway | BondLayer | yes | 78.7 |
| CityCircuit | control | no | 82.1 |
| NorthGear | competitor | yes | 83.6 |

## Where the extension attaches, and why

`org.bondlayer.benefit_value` extends **`catalog.search` and
`catalog.lookup`** — never `checkout`.

UCP's own loyalty extension hangs off `dev.ucp.shopping.checkout`, so loyalty
data only exists once the shopper has already chosen the merchant. By then the
comparison is over. Catalog is where the agent decides, so that is where
verifiable benefit data has to arrive.

It is namespaced `org.bondlayer.*` because `dev.ucp.*` is reserved for
capabilities governed by the UCP Tech Council.

## The adapter: normalising the mess is the deliverable

`data/catalog/electronics.csv` is 148 listings across 62 products with the
defects a real retailer's export actually carries. All 148 load; none are
rejected. Every repair is **recorded** rather than silently applied, because
the merchant needs to know what was wrong with their feed.

Severity is defined by **agent consequence**, not data purity:

| Severity | Meaning | Hits |
|---|---|---|
| `blocker` | invisible to a filter an agent will apply | 56 |
| `degrades_match` | findable, but loses a comparison it should win | 25 |
| `cosmetic` | tidiness; nothing downstream breaks | 7 |
| `info` | correct as it stands | 214 |

**214 of the 302 diagnostics confirm things are already correct.** Two rules
can only ever emit `info`: `legitimately_empty` (a rice cooker has no battery
capacity, and that is the truth rather than an omission) and `gtin_shared` (a
GTIN two merchants both list is how an agent knows it is comparing like with
like — keep publishing it). A tool that flags everything gets ignored.

| Rule | Severity | What it catches |
|---|---|---|
| `price_format` | blocker | `$2133.03`, `1,849.00` — an agent applying "under $1,500" drops the listing entirely |
| `ram_units` | degrades_match | `16GB` / `16 GB` / `16384MB` are one spec spelled three ways |
| `near_dup_title` | degrades_match | two spellings of one product compete against each other |
| `missing_weight` | degrades_match | "light enough to carry daily" cannot be answered |
| `screen_format` | degrades_match | `14"` is text; `14.0` is comparable |
| `spec_in_title` | degrades_match | `RTX4060` published only inside the title, with no GPU column |
| `brand_casing` | cosmetic | `Lenovo` / `LENOVO` / `lenovo` split one brand facet |
| `legitimately_empty` | info | correctly empty — no action |
| `gtin_shared` | info | cross-merchant match — good, keep it |

Counts are the same whichever way `analyse()` is called: indexes are built over
the whole file and rows are filtered afterwards, so per-merchant runs sum
exactly to the whole-file run and a cross-merchant signal stays visible from
inside one merchant's slice.

### Derived attributes carry their provenance

The catalogue has no GPU column, but `RTX4060` sits inside the Legion 5's
title. The adapter lifts it into a typed field by an exact `RTX|GTX` token and
marks where it came from:

```python
sku.attributes["gpu"]         # "RTX4060"
sku.attributes["gpu_source"]  # "title" — never "published"
```

Lifting a known token into a typed field in the adapter is normalisation. A
*matcher* scanning titles for substrings would be the thing intent matching is
supposed to go beyond. A consumer that will not accept derived evidence for a
hard constraint can require `gpu_source == "published"` and reject it.

## Onboarding API

The console's backend. Same process, its own router.

| Route | Returns |
|---|---|
| `GET /onboard/merchants` | switcher + comparison strip |
| `GET /onboard/report/{merchant}` | diagnostics, worst first, with readiness |
| `POST /onboard/catalog[?merchant=…]` | a retailer's own CSV export (multipart `file`, UTF-8). `merchant` may be omitted when the CSV names exactly one; an id the server does not know is registered as a catalogue-only retailer. Analysed before it is published, stored in `data/uploads/{merchant}.csv` and reloaded on start. 400 with the reason for missing required columns (`sku, merchant, title, category, price`) or no rows for the merchant named |
| `GET /onboard/requests` | the 30 frozen requests: id, utterance, per-merchant won/lost summary |
| `GET /onboard/requests/{id}[?merchant=…]` | the `RequestReport` JSON for one request — every merchant row three-way, or just one with `merchant=` |
| `GET /console/` | Minh's merchant console: static Next.js export from `app/out`, every figure fetched from the routes above |

The console is committed pre-built, so the server needs no Node at the venue.
After changing anything under `app/src`, rebuild and commit `app/out`:
`cd bondlayer/app && npm install && npm run build`. The console's **Ask
BondLayer** bar answers from `GET /onboard/report/{merchant}` alone
(`app/src/lib/ask.ts`, no model). The older no-build dashboard stays at
`/dashboard/` for compatibility but is no longer advertised.

## Intent route

The problem statement's desired outcome is a merchant system that receives the
buyer agent's multi-constraint query, decodes the intent, analyses its
catalogue against it and returns a justified proposal. `catalog.search`
receives a typed plan the agent decoded for itself. This route receives the
sentence.

| Route | Returns |
|---|---|
| `POST /{merchant}/ucp/intent/propose` | body `{"utterance": "…", "limit": 20}`; header `UCP-Agent` must negotiate `org.bondlayer.intent_match` (extends `catalog.search`; declared by voltway and northgear, not by the control) or the call is **406**. Returns `decoded_intent` (one entry per clause with its kind and the merchant's reading, the count of clauses no catalogue column can answer, plain-sentence assumptions, and one clarifying question when nothing names a product) and `proposals` (`product` exactly as `catalog.search` serves it, `resolved` per clause with `evidence_record_id`/`evidence_attribute`/`note`, `unsatisfied`). Only records that verify against the merchant's own key in `keys/` reach the resolver. `extensions` carries the same benefit blocks as search iff `org.bondlayer.benefit_value` also negotiated; absent otherwise. **The merchant receives the shopper's utterance verbatim; it never receives the shopper's valuation policy, benefit weights, or the cross-merchant comparison. Ranking against the shopper's policy stays agent-side.** |

The buyer agent calls it. `bondlayer.agent.merchant_decode.run_with_merchant_decode`
runs `run_request` unchanged, then sends the same sentence to every merchant
that negotiated `org.bondlayer.intent_match` and appends **one** step to the
trace (`Phase.INTENT`, `detail["kind"] == "merchant_decode"`) carrying, per
merchant, the merchant's `decoded_intent` verbatim, its first five proposals
trimmed to id/title/price plus the resolver's per-clause notes, and a
clause-by-clause agreement check against the agent's own decode (same `kind`
and overlapping tokens pair; the rule is spelled out in `agreement`'s
docstring). `scripts/trace_run.py` prints it as the `merchant decode (POST
/ucp/intent/propose)` section between the parsed constraints and the steps; in
`--control` it says the sentence was not sent. It never touches `ranked`,
`bundles` or `constraints`, and `tests/test_merchant_decode.py` pins that the
run is byte-identical to a plain `run_request` apart from the appended step.
The block is *what the merchant understood and proposed*; the ranking is *what
the agent verified and decided*.

## Checkout route

FPT's step 5, "closing the loop through a seamless, API-driven transaction".
The agent's chosen offer becomes an order confirmation that binds the signed
records the agent relied on. The server holds public keys only, so it cannot
sign a new order object: proof rides the merchant's already-signed envelopes,
and the order id is a content hash any party can recompute.

| Route | Returns |
|---|---|
| `POST /{merchant}/ucp/checkout` | body `{"items": [{"sku_id", "quantity"}], "cited_record_ids": […], "agent_ref": null}`; header `UCP-Agent` must negotiate `dev.ucp.shopping.checkout` (base UCP — declared by all three merchants, the control included) or the call is **406**; unknown sku **404**; quantity over a listing's published `stock` **409**. Returns `order` with `order_id` (SHA-256 over `{merchant_id, items, honoured record ids}` — deterministic, stateless, no clock), `status: confirmed_awaiting_payment`, `line_items`, `subtotal`, and `payment: {status: out_of_scope}` — **payment is out of scope and the response declares it; no funds move.** Iff `org.bondlayer.benefit_value` also negotiated: `honoured_benefits` (one verdict per cited record id — honoured only if published by this merchant, signed, unexpired, verifying against the merchant's own key in `keys/`, and applying to a line item by `sku_id` and `fact.scope`; otherwise the failing test in plain words) and `extensions` carrying the full signed envelope of every honoured record, re-verifiable against `signing_keys[]`. Absent otherwise — the control's checkout is a plain UCP order. Nothing the agent did not cite is added. **The merchant receives sku ids, quantities and cited record ids; it still never receives the shopper's valuation policy, benefit weights, or the cross-merchant comparison — an extra body field such as `shopper_policy` is a 422.** |

The agent side calls it: `agent/close_loop.py`. After the ranking,
`close_loop(run, checkout=...)` checks out `run.winner` — one unit of the
winning SKU at the winning merchant, citing exactly the record ids the agent
relied on: verified records that moved the effective cost (credited above $0)
or answered a clause as the resolver's evidence. A record that did not verify
is never sent; one the valuation scoped out of this category was not relied
on and is not sent either. The confirmation lands as one more `Step`
(`detail.kind == "close_loop"`, reusing `Phase.RANKING`) carrying the request,
the merchant's `order` verbatim and its `honoured_benefits` verdicts; a 406 is
a DEGRADED step, a refused verdict is DEGRADED with the merchant's reason in
the summary, and nothing above it on the run changes.
`scripts/trace_run.py` prints it as the `close the loop (POST /ucp/checkout)`
section, the last thing in the trace: with the extension, R01's six cited
records are all honoured and bound into Voltway's order; in `--control`,
CityCircuit's order is a plain UCP order that binds none.
`tests/test_close_loop.py` pins all of it, including that the same run twice
yields the same order id and the two runs' ids differ.

## Records

`data/records/{merchant}.signed.json`, served in the benefit block on the
catalogue call.

A record is signed **iff** it carries both a `signature` and a `key_id` —
`signed` is derived, never authored. Unsigned records are served and flagged,
never filtered: an unverifiable claim has to arrive in order to visibly earn
nothing. `sku_id: null` means the record applies to the whole merchant, so a
returns window attaches to every listing.

Public keys live in `keys/{merchant}.pub.json` and are published in the
profile's `signing_keys[]`. `keys/*.pem` is gitignored and `keys/*.json` is
not: private keys stay out, public keys must ship so a fresh clone verifies
with no network.

## Layout

```
src/bondlayer/
  types.py              shared contract — do not edit on a feature branch
  adapters/catalog.py   CSV in, normalised Sku + Diagnostic out
  ucp/capabilities.py   negotiation: intersection, version, pruning
  ucp/profile.py        /.well-known/ucp and signing_keys[]
  ucp/records.py        published records, signed or not
  ucp/server.py         the three merchants, one response builder
  ucp/onboard.py        onboarding API
```

## Not attempted

Real payment flows · production authentication · live merchant integration ·
protocol certification · cart, checkout and order capabilities.

## Response contract

Captured from the running server, not hand-written. If these disagree with the
code, the code is right and this section is stale — say so.

### `GET /{merchant}/ucp/catalog/search` · `…/lookup`

Query params — search: `q`, `category`, `max_price`, `limit` (≤100).
Lookup: `sku_id` (required). Header: `UCP-Agent`.

```json
{
  "business": { "id": "voltway", "name": "Voltway" },
  "active_capabilities": {
    "dev.ucp.shopping.catalog.search": "2026-04-08",
    "org.bondlayer.benefit_value": "draft"
  },
  "products": [
    {
      "id": "VOL-0001",
      "title": "ThinkBook 14 G3 i5 16 GB 512GB",
      "category": "laptop",
      "price": { "amount": "1455.00", "currency": "AUD" },
      "attributes": {
        "brand": "Lenovo", "cpu": "i5-1335U", "ram_gb": 16,
        "storage_gb": 512, "screen_in": 14.0, "weight_kg": 1.4,
        "battery_wh": 60.0, "gtin": "9312001000011", "condition": "new"
      }
    }
  ],
  "extensions": {
    "org.bondlayer.benefit_value": [
      { "sku_id": "VOL-0001", "issuer": "voltway.example", "records": [] }
    ]
  }
}
```

Contract notes:

- **`extensions` is absent entirely** when the extension did not survive
  negotiation — not empty, absent. Plain UCP is exactly
  `["business", "active_capabilities", "products"]`.
- `price.amount` is a **string** — a quantized decimal, never a float.
- `attributes` keys are present only when the listing has them. `ram_gb` and
  `storage_gb` are ints, `screen_in` / `weight_kg` / `battery_wh` are floats,
  everything else is a string. `gpu` appears with `gpu_source` beside it.
- `merchant` and `model_key` are **stripped** from the wire — the merchant is
  `business.id`, and GTIN is the public cross-merchant key.
- `extensions[…]` is one block **per product, in product order**.
- A record inside `records` is
  `{"record": {…}, "signature": str|null, "key_id": str|null, "signed": bool}`.
  `signed` is derived, never authored.
- A capability the agent did not declare returns **406**, not a degraded 200.

### `GET /onboard/report/{merchant}`

```json
{
  "merchant": "voltway",
  "rows_read": 56, "rows_rejected": 0, "skus": 56,
  "readiness": 78.7, "attributes_fixed": 36,
  "by_severity": { "blocker": 25, "degrades_match": 9, "cosmetic": 3, "info": 74 },
  "by_rule": { "price_format": 25, "gtin_shared": 42, "…": 0 },
  "diagnostics": [
    {
      "row": 4, "sku_id": "VOL-0004", "field": "price",
      "rule": "price_format", "severity": "blocker",
      "found": "$1922.96", "normalised": "1922.96",
      "message": "Use a plain number, e.g. 1499.00. Agents skip this in price filters.",
      "autofixed": true
    }
  ]
}
```

`diagnostics` arrives **pre-sorted worst-first** (blocker → degrades_match →
cosmetic → info, then by row), so the fix list reads top-down without the
client sorting it. `message` is the merchant-facing sentence — render it, don't
compose your own. `readiness` is already rounded to one decimal.

### `GET /onboard/merchants`

```json
[{ "merchant": "citycircuit", "rows_read": 49, "readiness": 82.1, "blockers": 17 }]
```

Sorted by merchant id, for the switcher and the comparison strip.
