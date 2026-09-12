# Phase 0 data — the gate is open

Everything downstream can start. Authored 12/09/2026 on `feat/nha-eval-data`.

| File | What | Who needs it |
|---|---|---|
| `eval/taxonomy.md` | The four clause kinds and why the split is the product | Hieu (labels), everyone (pitch) |
| `eval/requests.json` | **FROZEN** 30 requests, 80 constraints, gold answers | Hieu (tuning target), Nha (Day 2 eval run) |
| `catalog/electronics.csv` | 62 distinct products, 148 listings, 3 merchants, 34 planted defects | Nguyen (adapter), Hieu (matching) |
| `policies/*.md` | Retailer prose with facts buried in sentences | Hieu (converter) |
| `policies/manifests.json` | Who publishes what, incl. the planted unsigned claim | Nguyen (serving), Bach (signing) |

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
