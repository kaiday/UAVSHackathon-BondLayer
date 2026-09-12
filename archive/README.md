# archive/ — pre-hackathon spikes, kept for reference only

**Nothing in this directory is submission code.** The two folders under
`pre-hackathon-spikes/` are Round 1 feasibility spikes. They are kept in the
repository so the design trail is auditable, and for no other reason. The
Round 2 product is `bondlayer/` (merchant side) and `round2/chat-app/` (the
buyer-agent stand-in), both written inside the competition window.

The Rulebook forbids submitting code written before 09:00 on 12/09/2026. The
spikes are labelled so that no judge, and no team member, mistakes them for
the product. Moved here on the evening of 12/09 under steering ruling D5
(`round2/DAY2-PLAN.md` §2).

## What is here

| Folder | What it is | Commit | Files |
|---|---|---|---|
| `pre-hackathon-spikes/bach-demo/` | **BondLayer demo spike.** A UCP extension (`org.bondlayer.benefit_value`) served by three toy merchants selling outdoor jackets (Alpine / Peak / Ridgeway), Ed25519 signing via PyNaCl, a fixture-first LLM shopper agent, a deterministic valuation library and a two-pane web demo with an on/off switch. Its own README opens with "This is not submission code". | `e360df4` — authored and committed **02/09/2026 16:17 (+07:00)**, author `unknown`, message "team init demo" | 92 |
| `pre-hackathon-spikes/demo/` | **AgentBridge spike.** An MCP server plus a draft-style UCP head over one mock-store core: idempotent `create_order` → `confirm_order` in test mode, signed loyalty "Offer Cards", a hostile-HTML baseline and an A/B benchmark. Its `DECISIONS.md` opens with "this is pre-work, not submission code". | `42b7b4b` — authored and committed **12/09/2026 09:45 (+10:00)**, author `ManhDay`, message "mike-demo" | 40 |

Both figures come from `git log --format='%h %an %ad %cd %s' --date=iso -- <folder>`; each folder
has exactly one commit in its history on every ref.

A note on the second date. `demo/` reached this repository 45 minutes after the
09:00 cutoff. Its `DECISIONS.md` declares it pre-work written before the window,
and the team treats it exactly as it treats `bach-demo/`: reference only, never
imported, never copied. If a judge asks, that is the honest answer — it was
committed late, and it is not in the product.

## No submitted code imports from them

Checked on 12/09 after the move, over every Python tree that ships:

```
grep -rn -e 'agentbridge' -e 'bach_demo' -e 'bach-demo' -e 'pre-hackathon-spikes' \
        -e 'from demo' -e 'import demo' \
        bondlayer/src bondlayer/tests bondlayer/scripts bondlayer/run_server.py bondlayer/app \
        round2/chat-app/src round2/chat-app/tests round2/valuation round2/tests round2/demo_issue_13.py
# -> no matches (grep exit 1)
```

`bondlayer/WORKPLAN.md` states the clean-room rule the product was built under:
*"Every file in `bondlayer/` is written on 12–13/09/2026, inside the competition
window. Nothing is copied from `bach-demo/` or `demo/`."* The spikes carry their
own `requirements.txt` (PyNaCl, Streamlit, `mcp`, `stripe`, `anthropic`); none of
those are dependencies of `bondlayer/`.

## What was carried forward, as the rules allow

The Rulebook permits pre-work in the form of specification, design, data design
and prompts. What the Round 2 product took from the spikes is ideas, re-derived
and re-implemented on the day:

- **The extension design.** A signed benefit record is *facts under the
  customer's policy with the merchant's figure applied as a ceiling*; a record
  is signed iff it carries a signature and a key id; `sku_id: null` means the
  whole merchant. Spec: `bach-demo/docs/benefit-value-schema.md`. Round 2
  re-specified it in `bondlayer/docs/stage1-agent-ready-catalog.md` with
  **ES256 over canonical JSON** (the spike used Ed25519) and an electronics
  vertical (the spike used jackets).
- **Where the extension attaches.** `org.bondlayer.benefit_value` extends
  `catalog.search` / `catalog.lookup`, never `checkout`, because UCP's own
  loyalty extension only exists after the merchant is chosen. Finding 3 of
  `bach-demo/docs/ucp-findings.md`, cited by the Round 2 stage-1 document.
- **The two invariants.** Inflating a declared ceiling changes nothing;
  an unsigned claim is displayed and never valued. Both spikes found the first
  one by breaking it (`bach-demo/README.md`, `demo/DECISIONS.md` D3). Round 2
  holds them as tests in `bondlayer/tests/test_invariants.py`, written fresh.
- **The control is negotiation, not sabotage.** The "before" is the same
  server with the extension pruned by ordinary capability negotiation because
  the agent did not declare it — one code path (`demo/DECISIONS.md` D5,
  `bach-demo/README.md`). Round 2's CityCircuit is this: same server, extension
  absent from its manifest.
- **The demo script.** Same shopper request twice; the only difference is one
  capability in the `UCP-Agent` header; show the wire, then the flip. Round 2's
  chat app and trace CLI follow that shape.
- **Synthetic data design.** Deliberately messy merchant exports with recorded
  repairs, and policy prose converted to records behind a human approval gate.
  Round 2's `data/catalog/electronics.csv` (148 rows, authored 12/09) and the
  adapter's diagnostics are new data built on that idea; no data file was copied.
- **Prompt posture.** A shopper-agent system prompt that never names BondLayer,
  so the flip is a finding about the data, not a scripted outcome. Round 2 goes
  further: ranking is deterministic and the model, if present, writes prose only.

What was *not* carried: any Python, the jacket catalogue, the recorded LLM
fixtures, the Streamlit UI, the MCP server, the payments leg, the benchmark.

## Running them

Don't, for the demo. If you must inspect one, each folder has its own README and
`requirements.txt`; they are independent of `bondlayer/` and of each other.
