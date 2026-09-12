# AgentBridge

**Make any online store transactable by AI shopping agents — with loyalty
value the agent can verify and count — and prove it with a benchmark.**

An AI agent pointed at a normal storefront has to scrape marketing HTML, guess
at prices buried in free text, and click through fragile multi-step forms with
no confirmation step and no idempotency. And the store's loyalty program —
member pricing, warranty perks, points — is invisible to it: prose a machine
cannot weigh against price, so the agent ranks the merchant on shelf price
alone. AgentBridge wraps the store in a small **MCP server** with typed,
validated tools — so an agent (e.g. Claude) can search, quote, order, and
**explicitly confirm** a purchase safely, *and* recognise (or enrol) a loyalty
member so their earned value is **signed, valued, and counted** at the moment
of comparison. The included benchmark runs the same purchase tasks against
both surfaces and prints the before/after uplift.

```
  Claude / any        any UCP-capable
  MCP agent           agent
      │                    │ UCP-Agent: …; capabilities=…
      ▼                    ▼
  ┌─────────────┬──────────────────────┐
  │  MCP server │  UCP head (draft)     │   two protocol heads,
  │  (stdio)    │  capability           │   one core
  │             │  negotiation          │
  ├─────────────┴──────────────────────┤
  │  AgentBridge service                │
  │  search · offer · create_order      │
  │  confirm_order · members · consent  │
  ├────────────────────────────────────┤
  │  Loyalty layer (BondLayer)          │
  │  signed Offer Cards · Ed25519       │
  │  deterministic effective-cost math  │
  └──────────────┬─────────────────────┘
                 │ StoreAdapter interface
  ┌──────────────┴─────────────────────┐
  │ MockStoreAdapter (v1, offline)      │
  │ ShopifyStoreAdapter (roadmap)       │
  └────────────────────────────────────┘
```

**Safety model (v1, implemented for real):**

1. **Idempotency** — `create_order` requires an `idempotency_key`; replaying
   the same key returns the *same* order, never a duplicate (and never
   double-discounts). Reusing a key with a different basket is an explicit error.
2. **Confirmation gate** — `create_order` creates a `PENDING` order and has no
   payment path at all. Only `confirm_order` settles — in **Stripe TEST mode**
   if `STRIPE_TEST_KEY` is set (live keys are refused), otherwise a simulated
   test charge. **No real money can ever move.**
3. **Verified value only** — every loyalty benefit is a signed **Offer Card**
   (facts, conditions, expiry, bounded value ceiling; Ed25519 over the
   canonical card JSON). Unsigned or expired claims are *displayed but never
   valued* — the planted fake "$50 agent bonus" card proves it live.
4. **Consent gate** — `enroll_member` refuses to run without `consent=true`;
   the agent must ask the shopper before joining them to anything.

## The loyalty layer (BondLayer)

Loyalty programs were built for human psychology; an agent evaluates from
zero using only what it can read and verify. This layer makes the retailer's
loyalty value legible:

- `identify_member(email)` — recognise an existing member (demo members:
  `ava@example.com` GOLD, `leo@example.com` SILVER); `enroll_member` signs a
  new shopper up on the spot (BRONZE) — with explicit consent only.
- `get_offer` then returns the **loyalty quote**: every Offer Card with a
  credited/rejected verdict and reason, plus auditable arithmetic, e.g.

  ```
  $42.00 - $4.20 (member_price) - $3.00 (warranty, value)
         - $9.95 (shipping, value) = effective $24.85 (charge $37.80)
  ```

  Price benefits reduce the charge; service benefits (warranty months,
  shipping upgrades) count into **effective cost** — the number the agent
  ranks on instead of shelf price.
- `create_order` settles at the member price, so the offer that won is the
  offer delivered.
- `python console.py` — the merchant visibility console: per session, how
  much value was quoted, credited, and withheld (and why).

Roadmap (stubbed with docstrings, deliberately not v1): Shopify adapter,
atomic multi-line rollback, fraud scoring, the LLM policy converter with a
human approval gate, and cross-merchant effective-cost ranking.

## The UCP head (draft-style)

MCP is how Claude Desktop shops here; the **UCP head** is the protocol
story: the same store served over HTTP with real **capability
negotiation** (name intersection + extension pruning, per ucp.dev
core-concepts). The signed benefit records ride as a vendor extension —
`org.bondlayer.benefit_value`, extending `catalog.lookup` — so:

- an agent that declares the extension gets signed Offer Cards + the
  effective-cost valuation attached to every lookup;
- an agent that has never heard of it gets plain, valid UCP catalogue
  data and **nothing breaks** — the protocol prunes the extension, not a
  special baseline code path;
- the merchant's Ed25519 public key is published in
  `/.well-known/ucp`, so any agent can verify every card from wire data
  alone (checkout with idempotency + the confirmation gate included).

```bash
python demo_ucp.py           # the whole story, offline, ~5 seconds
python -m agentbridge.ucp    # or run the head standalone and curl it
```

The demo shows the same `catalog.lookup` twice — the only difference is
one capability in the `UCP-Agent` header — then verifies a signature
agent-side, proves tamper detection, and settles a member checkout at
the member price.

> **Honesty label:** UCP-*draft-style*, not certified conformance. The
> negotiation semantics follow the published core-concepts; JSON shapes
> approximate the draft. No protocol certification is claimed (per the
> proposal's §6.5 boundaries).

## The live experiment: does a real model credit verified value?

`compare_llm.py` is the discovery-time test (mirroring the team spike's
`compare`): three merchants sell a comparable charger — **harbor-tech**
($42.00, signed benefit records + GOLD member linked), **volt-depot**
($38.50, plain UCP), and **sparkline** ($39.95, the adversary: declares
the extension, publishes no key, so its "$50 bonus!" arrives unsigned).
The same agent, same system prompt, runs twice; only its declared
capability set differs, so the BEFORE payload is the AFTER payload pruned
by ordinary negotiation — not a strawman.

```bash
python compare_llm.py --dry-run     # inspect both payload sets, no key needed
python compare_llm.py               # 1 live run per condition (OPENAI_API_KEY)
python compare_llm.py --repeats 5   # tally across shuffled merchant orderings
```

Expected: BEFORE picks volt-depot on list price; AFTER picks harbor-tech
on out-of-pocket cost ($37.80 < $38.50 for the member, before service
value) while refusing sparkline's unsigned claim. A deterministic
cross-check prints the arithmetic the model should reproduce. Read the
transcripts before quoting the tally — the agent's prompt asks for
total-cost reasoning but never mentions this product, so the result is a
finding about the data, not a scripted outcome.

## Run the mock demo in 3 commands

```bash
pip install -r requirements.txt
python benchmark.py --simulate
python run_server.py
```

No API keys, no network, no setup — the mock store is in-memory. The third
command starts the MCP server on stdio (for Claude Desktop below; Ctrl+C to
stop).

## Connect Claude Desktop

Add this to `claude_desktop_config.json`
(Windows: `%APPDATA%\Claude\claude_desktop_config.json`,
macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`),
adjusting the path to where you cloned the repo:

```json
{
  "mcpServers": {
    "agentbridge": {
      "command": "python",
      "args": ["D:\\DemoMCP\\MCPAgentShoppingPython\\run_server.py"]
    }
  }
}
```

Restart Claude Desktop, then try:

> *"Find me a blue hoodie in size M under $50 and buy two."*

Watch Claude call `search_products` → `get_offer` → `create_order` (PENDING,
no charge) → `confirm_order` (test-mode settle). Then the loyalty money shot:

> *"I'm ava@example.com — buy me the 65W GaN charger with my membership."*

Claude calls `identify_member` first, `get_offer` shows the signed benefit
cards and the effective-cost arithmetic (and flags the unsigned "$50 bonus"
card as unverifiable), and the order settles at the member price, $37.80
instead of $42.00. Every call is logged as a JSON line to `agentbridge.log` —
run `python console.py` afterwards for the merchant's view.

## Run the benchmark

```bash
python benchmark.py            # live agent if ANTHROPIC_API_KEY is set, else simulated
python benchmark.py --simulate # deterministic, fully offline
python benchmark.py --live     # real Claude agent via the Anthropic API
```

Six purchase tasks run twice: **Run A** against a deliberately agent-hostile
raw HTML store (prices in marketing free text, prose stock warnings, opaque
multi-step forms, instant charge, no idempotency — and a loyalty club that
exists only as marketing copy with no login), **Run B** through the
AgentBridge tools. Both hit the *same* in-memory backend, and success is
judged by one strict checker inspecting the real order ledger — a task passes
only if exactly the right confirmed order exists (duplicates fail) and the
agent's answer is correct. The loyalty task passes only if the member's
verified credit actually reached the settled amount.

Example output (simulated mode):

```
Task                                  Baseline       AgentBridge
------------------------------------------------------------------
blue M hoodie <$50, buy 2          FAIL (4 st)       PASS (4 st)
buy cheapest in-stock item         PASS (9 st)       PASS (4 st)
return policy + buy jacket         FAIL (6 st)       PASS (5 st)
out-of-stock safety                PASS (5 st)       PASS (2 st)
3 tees, exact total                FAIL (6 st)       PASS (4 st)
member price via loyalty           FAIL (7 st)       PASS (5 st)
------------------------------------------------------------------
Success rate                               33%              100%
Avg steps per task                         6.2               4.0
Valid confirmed orders                     4/5               5/5
```

In `--simulate` mode both agents are deterministic scripts — but honest ones:
the baseline script genuinely fetches and parses the hostile HTML (and
genuinely falls into its traps), and the MCP script genuinely calls the tools.
In `--live` mode the same tasks are driven by a real Claude agent with tool
use, and results vary run to run.

You can also browse the hostile store yourself:
`python -m agentbridge.hostile` → http://127.0.0.1:8017

## Project structure

```
agentbridge/
  models.py        Pydantic models: Product, Offer, Order, Member, OfferCard,
                   LoyaltyQuote (prices in int cents)
  loyalty.py       The BondLayer core: members, signed Offer Cards (Ed25519),
                   deterministic effective-cost valuation
  service.py       The 8 tool implementations (shared by MCP server & benchmark)
  server.py        MCP server (official `mcp` SDK, stdio transport)
  ucp.py           The UCP head: capability negotiation + benefit_value extension
  hostile.py       The agent-hostile baseline store (what "unwrapped" looks like)
  payments.py      Test-mode-only settlement (Stripe test key or simulation)
  logging_config.py JSON-line structured logs -> stderr + agentbridge.log
  adapters/
    base.py        StoreAdapter interface — implement this to wrap a real store
    mock.py        In-memory store: ~15 products, idempotency, confirmation gate
    shopify.py     Roadmap stub mapping each method to a Shopify Admin API call
benchmark.py       The A/B benchmark
console.py         Merchant visibility console (quoted / credited / withheld)
demo_ucp.py        The UCP negotiation demo (one header, two worlds)
run_server.py      Launcher for Claude Desktop
```

## Environment variables (all optional)

Copy `.env.example` to `.env`:

| Variable | Effect if set | Fallback if unset |
|---|---|---|
| `ANTHROPIC_API_KEY` | benchmark drives a real Claude agent | `--simulate` scripted agents |
| `ANTHROPIC_MODEL` | model for live runs | `claude-sonnet-5` |
| `STRIPE_TEST_KEY` | `confirm_order` creates a Stripe **test-mode** PaymentIntent (`sk_test_` enforced) | simulated test charge (`ch_sim_…`) |
