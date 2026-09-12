# `feat/minh-surfaces` — Ha Anh Minh Truong (UX/UI Designer)

**All three delivered surfaces live on this branch.** They land in phase order,
because each one is only worth building once the thing behind it is real.

| # | Surface | Phase | Shows |
|---|---|---|---|
| 1 | **Console log** — AI chain of thought | 1 | constraints parsed → records cited → arithmetic → ranking |
| 2 | **User chat** — buyer-agent stand-in | 1 | the query going in, the justification coming back |
| 3 | **Merchant dashboard** | 2–3 | fields exposed · legible share · value credited · value withheld · why we lost |

## Build the console log first

This is counter-intuitive for a designer and it is deliberate. FPT wrote:
*"visual polish of human-facing dashboards is a **lower** priority than the
logic of the machine-to-machine interaction."*

So the surface that **exposes the logic** outranks the surface that summarises
the business outcome. Build the console log first, make the reasoning legible,
and only then make anything pretty.

What it renders, as a readable trace rather than a log dump:

```
intent    "a laptop under $1,500 I can return easily…"
parsed    HARD  price ≤ 1500
          SOFT  performance: design work
          SERVICE  easy returns        ← no catalogue attribute answers this
          VALUES   brand repairs things ← no catalogue attribute answers this
matched   SKU-0042, SKU-0117, SKU-0091
cited     SERVICE  → record r-88fa (return_window: 60 days)  ✓ verified
          VALUES   → record r-2c10 (warranty_months: 36)      ✓ verified
          —        → record r-ffff ($50 agent bonus)          ✗ unsigned · valued 0
cost      shelf 1,499.00 − credited 214.00 = effective 1,285.00
ranked    SKU-0117 wins on effective cost despite a higher shelf price
```

Those two `← no catalogue attribute answers this` markers are the product
thesis rendered on screen. Do not let them get designed away.

## User chat — scope discipline matters here

A shopper types a need; the simulated agent turns it into a structured UCP
request.

**Label it as the buyer-agent stand-in.** FPT put *"building a consumer-facing
AI shopping assistant"* explicitly out of scope — the focus must stay on how the
business adapts to the consumer's agent. This chat is our **test harness**
(assumption A2: the agent is a stand-in with a neutral prompt and no knowledge
of our system), not our product.

Same pixels either way; the framing is what keeps us in scope. Put the label in
the UI, not just in the script — a judge reading the screen should never think
we built a shopping assistant.

## Merchant dashboard

Exactly four figures per agent request, per §5.2 component 8:

1. fields exposed
2. share of the real offer that was legible
3. verified value the agent could credit
4. benefits withheld by the wire

Plus **why it lost** — that is the line an e-commerce lead actually buys, and it
is the difference between "the retailer learns from a lost comparison rather
than only from a lost sale."

## The switch is the demo

Two panes, one toggle: **control merchant vs BondLayer merchant.** Same query,
same code path, visibly different outcome. Nguyen serves both from one server
with enrichment off for the control, so the only variable is the data exposed.

Design the toggle as the centrepiece. It is the moment the pitch turns.

## Constraints

- **Runs from seeded state, no network call.** Venue wifi is shared by twenty
  teams and a live call will fail on stage.
- Round 2 still scores UX at 20, so this needs to be clean and consistent — just
  never at the cost of the logic being visible.
- Day 2 09:15–11:00 is the UX pass. Day 1 is for making it true, not pretty.

## Working against the gate

Real data lands ~12:00. Until then build all three against fixture JSON shaped
like `Proposal`, `EffectiveCost` and `RequestReport` in `types.py`. Those shapes
are frozen, so nothing you build against them is wasted.

## Done when

The demo query runs end to end through chat → console log → dashboard, from
seeded state, with the control/BondLayer toggle switching the outcome live.
