# Phase 0 data — the gate is open

Everything downstream can start. Authored 12/09/2026 on `feat/nha-eval-data`.

| File | What | Who needs it |
|---|---|---|
| `eval/taxonomy.md` | The four clause kinds and why the split is the product | Hieu (labels), everyone (pitch) |
| `eval/requests.json` | **FROZEN** 30 requests, 80 constraints, gold answers | Hieu (tuning target), Nha (Day 2 eval run) |
| `catalog/electronics.csv` | 62 distinct products, 148 listings, 3 merchants, deliberate attribute noise | Nguyen (adapter), Hieu (matching) |
| `policies/*.md` | Retailer prose with facts buried in sentences | Hieu (converter) |
| `policies/manifests.json` | Who publishes what, incl. the planted unsigned claim | Nguyen (serving), Bach (signing) |

## Do not quote a defect count

An earlier version of this file said "34 planted defects". That number described
the authored `PRODUCTS` table in `scripts/make_catalog.py`, not the 148-row CSV
it emits -- each authored variant fans out across every merchant carrying that
product. The figure was wrong for the emitted file and should not appear in the
pitch, the README or the deck.

The authoritative count is whatever the catalogue adapter's
`analyse() -> CatalogReport` measures, because that applies the adapter's own
rule definitions. Independent counts genuinely disagree: "price format" alone
lands between 56 and 98 depending on whether a bare integer is a defect. Quote
the adapter's report, or quote nothing.

### Verified figures

Measured against `CsvCatalogAdapter` at `3a05d6e`, run independently rather than
taken on report.

Whole file — 148 listings, **299 diagnostics**, readiness 81.7:

| Severity | Count | | Rule | Count |
|---|---|---|---|---|
| blocker | **56** | | price_format | 56 |
| degrades_match | 22 | | gtin_shared | 129 |
| cosmetic | 7 | | legitimately_empty | 85 |
| info | 214 | | ram_units | 13 |
| | | | near_dup_title | 5 |
| | | | brand_casing / screen_format / missing_weight | 5 / 3 / 3 |

Per merchant: voltway 56 SKUs, 110 diagnostics, readiness **79.0** ·
citycircuit 49, 104, **82.6** · northgear 43, 85, **84.1**.

Per-merchant runs sum exactly to the whole-file run — 110 + 104 + 85 = 299,
with every rule matching and `gtin_shared` splitting 42 + 49 + 38 = 129. A
figure means the same thing whichever run produced it.

That was not always true. Until `3a05d6e`, `analyse()` filtered rows to the
merchant *before* building its indexes, so a shared GTIN was invisible from
inside one merchant's slice and the canonical title was decided by whichever
rows survived the filter. Since the onboarding console runs per merchant, its
"also listed by voltway" line could never have rendered. Two regression tests
now hold the invariant. Recorded because it is the kind of bug that comes back.

**The sentence for the pitch:**

> 34 authored defect variants across 62 products expand to 299 diagnostics
> across the emitted 148-row catalogue, 56 of them blockers that make a listing
> invisible to a filter an agent will apply.

The expansion is the point: one bad habit in a source system becomes hundreds of
unreadable listings downstream. That is the adoption story in one number.

Do **not** write "214 diagnostics, of which 56 are blockers" — 214 is the info
count, and the blockers are a separate severity, not a subset of it.

And say the quiet part out loud: 214 of the 299 are INFO. Two rules can only
ever emit INFO — `legitimately_empty` and `gtin_shared` — so a merchant can tell
"you didn't fill this in" apart from "this is empty because it should be". A
retailer flagged for a rice cooker having no battery capacity stops reading the
report. Worth saying to a sceptical judge before they ask.

## Rules

- **`eval/requests.json` is frozen.** Do not regenerate it. Assumption A2 claims
  it was frozen before the enriched feed existed and the commit timestamp is the
  only proof. `scripts/make_eval.py` is kept for audit, not for re-running.
- The catalogue **is** regenerable — `python scripts/make_catalog.py` is
  deterministic and produces identical bytes. But gold sets in the frozen eval
  set resolve to SKU ids, so regenerating with different products would break
  them. Don't change `PRODUCTS`.

## The three merchants

| | Role | Extension | Records | Shelf price |
|---|---|---|---|---|
| **voltway** | BondLayer | yes | 12 (9 priced, 3 values) | ~4% above base — never the cheapest |
| **citycircuit** | control | no | 0 by design | ~3% below base |
| **northgear** | competitor | yes | 5 signed + **1 planted unsigned** | at base |

Voltway is not the cheapest anywhere. It has to win on effective cost or the
demo proves nothing.

CityCircuit having zero records is not a strawman — it genuinely has a 30-day
returns policy and a points programme. They are simply not legible to an agent.
That is the status quo the whole proposal argues against.

## Set pieces built into the data

- **R01** — the demo query, one clause of each kind
- **R21** — the tie-break. Voltway is 4th cheapest at $1,142.96 against the
  control's $1,066. Benefit records have to close a $77 gap on effective cost.
- **R12** — "the most sustainable phone you sell". NorthGear's greenwashing
  claim is unsigned and must not win it; Voltway's claims less and publishes an
  assured figure, so it signs. This is gap 5's demo moment.
- **R18 / R19 / R20** — near-duplicate traps. Substring matching returns spacing
  variants as distinct products.
- **R16 / R17** — deliberately unsatisfiable clauses, to be flagged honestly.
- **R28** — a warranty add-on as the product. The control stocks none, so it
  cannot answer at all.
- **R06 / R07 / R24** — bundle intents. R07 is the problem statement's own
  worked example, near-verbatim.
