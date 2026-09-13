# Shopping insights

The merchant-facing page remains at `/console/requests/`, now labelled **Shopping
insights**. Select a merchant, reporting period and comparison view. All figures
come from `GET /onboard/insights/{merchant}?days=30&mode=enabled`.

## What the merchant sees

- **Shopping requests observed:** saved comparison runs that include this merchant.
- **Requests with offers:** runs where the merchant had an offer in the comparison.
- **Requests with unanswered needs:** runs whose merchant-specific report lists
  at least one unsatisfied requirement.
- **Checkout confirmations:** confirmed checkout responses addressed to this
  merchant. These count responses, not unique orders, paid sales or revenue.
- **Agent selection:** only when the saved agent report explicitly establishes a
  selection. Missing outcomes stay unknown.
- **Demand:** categories, stated budget ceilings and requirements from the
  recorded request. Counts are distinct requests within each topic; a request
  can mention several topics.
- **Improvements:** observed data gaps, missing policy evidence, unverifiable or
  expired benefits and eligibility issues. Each links to supporting requests
  and an action in Catalogue or Benefit records.

The default is **Benefits enabled**. Baseline comparisons are separate runs and
can be viewed independently or combined with **All comparison runs**. These
counts must never be described as unique shoppers or all customer demand.

## Evidence and limitations

New reports capture requirement checks, benefit decisions, missing fields and
checkout evidence in each merchant row's `observation` object. Evidence is
captured when the comparison runs; current catalogue data is not used to invent
past causes. Older summary reports still appear with their available evidence,
but their missing detail is acknowledged.

"Eligibility unknown" means the shopper's eligibility could not be established.
"Not eligible" requires an explicit rejection in the saved comparison. A missing
policy record does not establish that the business lacks the underlying benefit.
No matching offer alone does not distinguish an assortment gap from a data gap.

Insights include only live reports, scoped to the selected merchant, using the
latest 500 retained reports for that merchant. Historical benchmark scenarios
are excluded. Dates must be timezone-aware; undated and future-dated reports do
not count. The period is rolling (7, 30 or 90 days), or all retained history.

Technical identifiers and the original recorded reasons are available under
**Technical details** on each request. The insights API returns only the selected
merchant's offer and evidence, without other merchants' prices or order details.

Aggregation is deterministic and makes no model or external network calls.
