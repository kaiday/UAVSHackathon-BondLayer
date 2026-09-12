"""Author the frozen evaluation set.

30 multi-constraint requests with gold answers, labelled against the taxonomy in
data/eval/taxonomy.md. Gold SKU sets are resolved from the catalogue at build
time so they cannot drift out of sync with it.

FREEZE RULE: this runs once, its output is committed, and neither is touched
again. Assumption A2 claims the evaluation set was frozen before the enriched
feed existed; the commit timestamp is the only proof of that, and re-running
this after the interpreter is tuned would destroy the claim.

Run:  python scripts/make_eval.py
Out:  data/eval/requests.json
"""

from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "catalog" / "electronics.csv"
OUT = ROOT / "data" / "eval" / "requests.json"

H, S, SV, V = "HARD", "SOFT", "SERVICE", "VALUES"


def load() -> list[dict]:
    rows = list(csv.DictReader(CATALOG.open(encoding="utf-8")))
    for r in rows:
        raw = r["price"].replace("$", "").replace(",", "").strip()
        r["_price"] = Decimal(raw)
    return rows


def by(rows, **kw) -> list[str]:
    """SKUs matching every given field, plus optional max_price/min_ram."""
    maxp = kw.pop("max_price", None)
    keys = kw.pop("model_keys", None)
    out = []
    for r in rows:
        if keys is not None and r["model_key"] not in keys:
            continue
        if maxp is not None and r["_price"] > Decimal(str(maxp)):
            continue
        if all(r.get(k) == v for k, v in kw.items()):
            out.append(r["sku"])
    return sorted(out)


# (id, utterance, [(text, kind)], gold_spec, notes)
# gold_spec is resolved against the catalogue below.
SPEC = [
    ("R01", "A laptop under $1,500 I can return easily if it turns out not to suit my work, from a brand that actually repairs things",
     [("under $1,500", H), ("suits my work", S), ("I can return it easily", SV), ("a brand that actually repairs things", V)],
     dict(category="laptop", max_price=1500),
     "THE DEMO QUERY. One clause of each kind. The last two are unanswerable from the catalogue alone."),

    ("R02", "I need a laptop for design work, no more than $2,500, and I want decent cover if it breaks in year two",
     [("no more than $2,500", H), ("for design work", S), ("cover if it breaks in year two", SV)],
     dict(category="laptop", max_price=2500),
     "Warranty clause resolves to a warranty benefit record, not a catalogue field."),

    ("R03", "Cheapest 16GB laptop you have",
     [("16GB", H), ("cheapest", S)],
     dict(category="laptop"),
     "Control case: fully answerable from the catalogue. A plain feed should do fine here, and that is the point."),

    ("R04", "Something light I can carry every day, under 1.3kg, budget around $2,000",
     [("under 1.3kg", H), ("around $2,000", S), ("carry every day", S)],
     dict(category="laptop"),
     "'around' makes budget SOFT; 'under 1.3kg' stays HARD. Taxonomy rule 3."),

    ("R05", "A phone under $1,000 from a company that lets you fix it yourself",
     [("under $1,000", H), ("lets you fix it yourself", V)],
     dict(category="phone", max_price=1000),
     "Repairability is a VALUES claim: signed, cited, worth $0."),

    ("R06", "Everything I need to start a podcast, under $1,200 all up",
     [("under $1,200 all up", H), ("everything to start a podcast", S)],
     dict(category="audio"),
     "BUNDLE. Gold is a set. Combined price is the constraint, not per-item price."),

    ("R07", "Beginner-friendly podcasting gear, I've never recorded anything before",
     [("beginner-friendly", S), ("podcasting gear", S)],
     dict(category="audio"),
     "BUNDLE. The problem statement's own worked example, near-verbatim."),

    ("R08", "A vacuum under $1,000 with a long warranty",
     [("under $1,000", H), ("vacuum", H), ("long warranty", SV)],
     dict(category="appliance", max_price=1000),
     "Warranty length differs by merchant and is only visible as a record."),

    ("R09", "Coffee machine, under $800, must be returnable if I don't get on with it",
     [("under $800", H), ("coffee machine", H), ("returnable if I don't get on with it", SV)],
     dict(category="appliance", max_price=800),
     "Return window is the deciding clause."),

    ("R10", "A 32GB laptop for video editing, money is not really the issue",
     [("32GB", H), ("for video editing", S)],
     dict(category="laptop"),
     "No budget clause at all. Interpreter must not invent one."),

    ("R11", "Monitor for a home office, around $800, delivered free if possible",
     [("monitor", H), ("around $800", S), ("delivered free if possible", SV)],
     dict(category="accessory"),
     "Delivery threshold is a benefit record."),

    ("R12", "I want the most sustainable phone you sell",
     [("phone", H), ("most sustainable", V)],
     dict(category="phone"),
     "Pure VALUES ranking. Contributes no dollars; decided entirely on signed claims. northgear's greenwashing claim is unsigned and must not win this."),

    ("R13", "Laptop under $1,200, 16GB, and I want to be able to trade in my old one",
     [("under $1,200", H), ("16GB", H), ("trade in my old one", SV)],
     dict(category="laptop", max_price=1200),
     "Trade-in credit is a priced benefit record."),

    ("R14", "A headset for calls under $300",
     [("under $300", H), ("headset for calls", S)],
     dict(category="audio", max_price=300),
     "Simple two-clause baseline."),

    ("R15", "Something to record interviews on the go, under $500, easy to return if the audio is no good",
     [("under $500", H), ("record interviews on the go", S), ("easy to return", SV)],
     dict(category="audio", max_price=500),
     "Use-case clause is SOFT and must resolve to inferred attributes, stated."),

    ("R16", "A laptop that will still be supported in five years",
     [("laptop", H), ("still supported in five years", V)],
     dict(category="laptop"),
     "UNSATISFIABLE by design. No merchant publishes a support-lifetime claim. Must appear in unsatisfied, not be silently dropped."),

    ("R17", "Under $600, a phone, and it must be carbon neutral",
     [("under $600", H), ("phone", H), ("carbon neutral", V)],
     dict(category="phone", max_price=600),
     "UNSATISFIABLE VALUES clause on a satisfiable product set. Partial answer plus honest flag."),

    ("R18", "The ThinkBook 14 G3 with 16 gigs",
     [("ThinkBook 14 G3", H), ("16 gigs", H)],
     dict(model_keys={"tb14g3-i5"}),
     "NEAR-DUPLICATE TRAP. Three listings, two of them differing only in spacing. Substring matching returns all three as distinct products; a real matcher collapses them by GTIN."),

    ("R19", "A ThinkBook 14, i7, 1TB",
     [("ThinkBook 14", H), ("i7", H), ("1TB", H)],
     dict(model_keys={"tb14g4-i7"}),
     "Generation trap: G3 and G4 differ by one character in the title."),

    ("R20", "XPS 13 with 16GB",
     [("XPS 13", H), ("16GB", H)],
     dict(model_keys={"xps13-9340"}),
     "Second near-duplicate pair, formatted differently."),

    ("R21", "A laptop under $1,600 — I'd rather pay a bit more if the returns are genuinely painless",
     [("under $1,600", H), ("returns genuinely painless", SV)],
     dict(category="laptop", max_price=1600),
     "TIE-BREAK. Shelf prices are close; only the return-window record separates them. This is the effective-cost story in one request."),

    ("R22", "Rice cooker, cheapest one, but I want it to last",
     [("rice cooker", H), ("cheapest", S), ("I want it to last", V)],
     dict(category="appliance"),
     "Durability is a VALUES claim, not a spec."),

    ("R23", "Portable SSD, 2TB, delivered this week",
     [("2TB", H), ("portable SSD", H), ("delivered this week", SV)],
     dict(category="accessory"),
     "Delivery speed is a service clause with no catalogue column."),

    ("R24", "A work laptop and a dock, under $2,200 together",
     [("under $2,200 together", H), ("work laptop", S), ("dock", H)],
     dict(category="laptop"),
     "BUNDLE across two categories. Combined-price constraint."),

    ("R25", "Gaming laptop, 32GB, RTX, under $3,000",
     [("32GB", H), ("RTX", H), ("under $3,000", H), ("gaming", S)],
     dict(category="laptop", max_price=3000),
     "All-HARD request. Baseline for filter correctness."),

    ("R26", "I'm on a tight budget but I hate throwing things away — phone, under $700",
     [("under $700", H), ("phone", H), ("hate throwing things away", V)],
     dict(category="phone", max_price=700),
     "VALUES clause phrased as sentiment, not as a spec word. Tests decoding rather than keyword pickup."),

    ("R27", "Microphone under $200 that I can send back if it doesn't suit my voice",
     [("under $200", H), ("microphone", H), ("send back if it doesn't suit", SV)],
     dict(category="audio", max_price=200),
     "Cheap item where the return window is worth a meaningful fraction of the price."),

    ("R28", "Two-year cover on a laptop I already own",
     [("two-year cover", H), ("laptop", H)],
     dict(category="warranty"),
     "Service SKU as the product itself. citycircuit stocks none, so it cannot answer at all."),

    ("R29", "Best value 14 inch laptop with 16GB, and I do care where it's made",
     [("14 inch", H), ("16GB", H), ("best value", S), ("I care where it's made", V)],
     dict(category="laptop"),
     "Four clauses, all four kinds represented across the set. Screen size is formatted three different ways in the catalogue."),

    ("R30", "Anything under $100 that would make a good gift",
     [("under $100", H), ("a good gift", S)],
     dict(max_price=100),
     "Deliberately vague. Per the workshop steer, must return a best-understanding recommendation with the assumption stated -- never a hard failure."),
]


def main() -> None:
    rows = load()
    out = []
    for rid, utterance, clauses, gold_spec, notes in SPEC:
        gold = by(rows, **dict(gold_spec))
        out.append({
            "id": rid,
            "utterance": utterance,
            "constraints": [{"text": t, "kind": k} for t, k in clauses],
            "gold_skus": gold,
            "gold_model_keys": sorted({r["model_key"] for r in rows if r["sku"] in set(gold)}),
            "bundle": rid in {"R06", "R07", "R24"},
            "expect_unsatisfied": rid in {"R16", "R17"},
            "notes": notes,
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "frozen": "2026-09-12",
        "freeze_rule": "Frozen before any benefit record existed. Do not regenerate.",
        "taxonomy": "data/eval/taxonomy.md",
        "catalogue": "data/catalog/electronics.csv",
        "count": len(out),
        "requests": out,
    }, indent=2), encoding="utf-8")

    kinds = [c["kind"] for r in out for c in r["constraints"]]
    from collections import Counter
    print(f"wrote {len(out)} requests -> {OUT}")
    print("constraints:", len(kinds), Counter(kinds))
    print("bundles:", sum(1 for r in out if r["bundle"]))
    print("expect unsatisfied:", sum(1 for r in out if r["expect_unsatisfied"]))
    empty = [r["id"] for r in out if not r["gold_skus"]]
    if empty:
        print("WARNING empty gold sets:", empty)


if __name__ == "__main__":
    main()
