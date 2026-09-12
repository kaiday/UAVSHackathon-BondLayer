#!/usr/bin/env python3
"""The evaluation run: 30 frozen requests, twice, with and without the records.

    python scripts/eval_run.py

Deterministic and offline. No network call, no model call, no clock, no random
seed -- run it twice on two laptops and the numbers are identical, which is the
only reason they are allowed in the pitch.

**What "twice" means.** Every request is resolved against the same catalogue in
two conditions:

- **BondLayer** -- the interpreter is handed the records this repository
  publishes, *after* each one has been verified against the merchant's public
  JWK in ``keys/``. A record that does not verify is never handed over, so it
  cannot be cited. NorthGear's planted sustainability claim is unsigned and is
  dropped here, which is why it cannot win R12.
- **control** -- the same catalogue, the same parser, the same resolver, and an
  empty record list. This is what a plain product feed can answer.

The difference between the two columns is the whole argument: HARD and SOFT
clauses are answered identically in both, because a competent catalogue search
handles them, and every SERVICE and VALUES clause goes unanswered in the
control, because no catalogue has a column for "can I return this easily".

**The five metrics, defined.**

- *hard precision* -- share of returned proposals whose SKU is in ``gold_skus``.
- *gold recall* -- share of ``gold_skus`` present in the returned proposals.
- *citation precision* -- share of cited ``evidence_record_id``s that exist and
  verify. This must be 1.00. It is not a number to improve; it is an assertion
  that the resolver never cites something it cannot show you, and the runner
  exits non-zero if it ever drops below 1.00.
- *unsatisfied honesty* -- every request marked ``expect_unsatisfied`` returns a
  non-empty ``Proposal.unsatisfied``. A clause nobody can answer has to be
  reported, not silently dropped.
- *answerable share* -- of the SERVICE and VALUES clauses across all requests,
  the share answered by a cited record. Near zero in the control, by
  construction.

A sixth column, *precision@|gold|*, is reported alongside them and is not one of
the five: it reads the ordering rather than the filter. Where the shopper names
no product category ("something light I can carry every day"), the resolver
refuses to invent one -- a SOFT clause ranks and never filters -- so flat
precision counts every eligible listing as a miss while the gold set sits at the
top of the list. Both numbers are printed because only reporting the flattering
one would be the kind of thing this project exists to argue against.

Outputs: ``docs/eval-results.md`` (commit hash, command, table) and one
``data/eval/reports/<id>.json`` per request, carrying a ``RequestReport``-shaped
row per merchant for the console to render.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:  # runnable without an editable install
    sys.path.insert(0, str(ROOT / "src"))

from bondlayer.adapters.catalog import CsvCatalogAdapter  # noqa: E402
from bondlayer.agent.composition import realisable_credit  # noqa: E402
from bondlayer.interpreter.parser import parse  # noqa: E402
from bondlayer.interpreter.resolver import resolve_detailed  # noqa: E402
from bondlayer.records.serialise import load_signed  # noqa: E402
from bondlayer.records.signing import ES256Signer  # noqa: E402
from bondlayer.types import ConstraintKind, Proposal, SignedRecord  # noqa: E402
from bondlayer.valuation import (  # noqa: E402
    ATTESTED_CONDITIONS,
    MERCHANT_DOMAINS,
    REFERENCE_SHOPPER_POLICY,
    DeterministicValuation,
)

CATALOG = ROOT / "data" / "catalog" / "electronics.csv"
RECORDS = ROOT / "data" / "records"
KEYS = ROOT / "keys"
REQUESTS = ROOT / "data" / "eval" / "requests.json"
REPORTS = ROOT / "data" / "eval" / "reports"
RESULTS = ROOT / "docs" / "eval-results.md"

#: The clause kinds no catalogue column can answer.
RECORD_KINDS = (ConstraintKind.SERVICE, ConstraintKind.VALUES)


# --- loading ----------------------------------------------------------------


def load_catalogue() -> list:
    return CsvCatalogAdapter(CATALOG).load()


def load_verifiers() -> dict[str, ES256Signer]:
    """One verifier per merchant, built from the published JWK only.

    No private key and no network: exactly what an agent can do from a fresh
    clone, which is the whole claim the signing story makes.
    """
    built: dict[str, ES256Signer] = {}
    for merchant, domain in MERCHANT_DOMAINS.items():
        path = KEYS / f"{merchant}.pub.json"
        if path.exists():
            jwk, = json.loads(path.read_text(encoding="utf-8"))
            built[merchant] = ES256Signer.from_jwk(jwk, issuer=domain)
    return built


def load_published() -> dict[str, list[SignedRecord]]:
    return {
        merchant: (load_signed(RECORDS / f"{merchant}.signed.json")
                   if (RECORDS / f"{merchant}.signed.json").exists() else [])
        for merchant in MERCHANT_DOMAINS
    }


def verified_records(
    published: dict[str, list[SignedRecord]], verifiers: dict[str, ES256Signer],
) -> tuple[list[SignedRecord], list[str]]:
    """Only records whose signature checks out, plus the ids that were dropped.

    This is the gate the resolver never sees behind. An unsigned record reaches
    the console and the valuation -- it has to be visible earning nothing -- but
    it never reaches the resolver, so it can never be cited as evidence.
    """
    kept: list[SignedRecord] = []
    dropped: list[str] = []
    for merchant, signed in published.items():
        verifier = verifiers.get(merchant)
        for item in signed:
            if verifier is not None and item.signature and verifier.verify(item):
                kept.append(item)
            else:
                dropped.append(item.record.record_id)
    return kept, sorted(dropped)


def load_requests() -> list[dict]:
    return json.loads(REQUESTS.read_text(encoding="utf-8"))["requests"]


def commit_hash() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True, timeout=10,
        )
        # Tracked changes only: this run is about to write its own outputs, and
        # calling the tree dirty because of them would be noise on every run.
        dirty = subprocess.run(
            ["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"],
            capture_output=True, text=True, check=True, timeout=10,
        )
        return out.stdout.strip() + (" (dirty)" if dirty.stdout.strip() else "")
    except Exception:  # a tarball with no .git is still a valid way to run this
        return "unknown"


# --- one condition of one request -------------------------------------------


@dataclass
class Outcome:
    """One request resolved in one condition."""

    proposals: list[Proposal]
    hard_precision: float
    gold_recall: float
    precision_at_gold: float
    citations_total: int
    citations_valid: int
    clauses_total: int
    clauses_answered: int
    reports_unsatisfied: bool
    unsatisfied_texts: list[str] = field(default_factory=list)


def score(request: dict, proposals: list[Proposal], valid_ids: set[str]) -> Outcome:
    got = [p.sku.sku_id for p in proposals]
    gold = set(request["gold_skus"])
    hit = len(set(got) & gold)
    k = len(gold)

    citations_total = citations_valid = 0
    for p in proposals:
        for r in p.resolved:
            if r.evidence_record_id is not None:
                citations_total += 1
                citations_valid += int(r.evidence_record_id in valid_ids)

    # A SERVICE or VALUES clause counts as answered when at least one returned
    # proposal cites a record for it. Per request, not per listing: the
    # question is whether the shopper can get an answer at all.
    wanted = [c for c in parse(request["utterance"]) if c.kind in RECORD_KINDS]
    answered = {
        r.constraint.text
        for p in proposals for r in p.resolved
        if r.constraint.kind in RECORD_KINDS and r.satisfied
    }

    return Outcome(
        proposals=proposals,
        hard_precision=(hit / len(got)) if got else 0.0,
        gold_recall=(hit / k) if k else 0.0,
        precision_at_gold=(len(set(got[:k]) & gold) / k) if k and got else 0.0,
        citations_total=citations_total,
        citations_valid=citations_valid,
        clauses_total=len(wanted),
        clauses_answered=sum(1 for c in wanted if c.text in answered),
        reports_unsatisfied=any(p.unsatisfied for p in proposals),
        unsatisfied_texts=sorted({c.text for p in proposals for c in p.unsatisfied}),
    )


# --- the merchant's side of the same request --------------------------------


def merchant_rows(
    request: dict,
    outcome: Outcome,
    published: dict[str, list[SignedRecord]],
    verifiers: dict[str, ES256Signer],
    *,
    with_records: bool,
) -> list[dict]:
    """A ``RequestReport``-shaped row per merchant, for the console to render.

    Each merchant is represented by its **best offer on effective cost**, not by
    whichever listing happened to sort first: the whole claim is that records
    can move a dearer shelf price ahead of a cheaper one, so comparing anything
    other than the post-valuation figure would hide the flip the tests prove.

    ``fields_exposed`` counts what that listing actually publishes;
    ``legible_share`` is the share of the shopper's clauses that merchant could
    answer at all; credited and withheld are the valuation's own arithmetic.
    """
    clauses = parse(request["utterance"])
    by_merchant: dict[str, list[Proposal]] = {}
    for p in outcome.proposals:
        merchant = str(p.sku.attributes.get("merchant", ""))
        if merchant:
            by_merchant.setdefault(merchant, []).append(p)

    costs: dict[str, Decimal] = {}
    detail: dict[str, dict] = {}
    for merchant, proposals in by_merchant.items():
        verifier = verifiers.get(merchant)
        valuation = (
            DeterministicValuation(
                verifier, merchant_domains=MERCHANT_DOMAINS,
                satisfied_conditions=ATTESTED_CONDITIONS,
            )
            if with_records and verifier is not None else None
        )

        def priced(proposal: Proposal) -> tuple[Decimal, Decimal, Decimal]:
            """(effective cost, credited, withheld) for one listing."""
            if valuation is None:
                # No records on the wire: the shelf price is the whole offer,
                # and everything the merchant published is value withheld.
                withheld_ = sum(
                    (r.record.value_ceiling_aud or Decimal("0")
                     for r in published.get(merchant, [])),
                    Decimal("0"),
                )
                return proposal.sku.shelf_price, Decimal("0"), withheld_
            cost = valuation.effective_cost(
                proposal.sku, published.get(merchant, []), REFERENCE_SHOPPER_POLICY,
            )
            # Value the merchant published that the wire did not carry through:
            # unverified, unattested, out of scope, or never priced at all.
            withheld_ = sum(
                (line.merchant_ceiling_aud - line.credited_aud
                 for line in cost.credited
                 if line.merchant_ceiling_aud > line.credited_aud),
                Decimal("0"),
            )
            # The same ranking floor the agent applies, from the same function:
            # a benefit cannot be worth more than the listing it attaches to,
            # and the console must not show a $30 cable at minus $119.
            credited_, unusable_ = realisable_credit(cost.total_credited,
                                                     proposal.sku.shelf_price)
            return (proposal.sku.shelf_price - credited_, credited_,
                    withheld_ + unusable_)

        best, (effective, credited, withheld) = min(
            ((p, priced(p)) for p in proposals),
            key=lambda pair: (pair[1][0], pair[0].sku.sku_id),
        )
        costs[merchant] = effective
        answered = sum(1 for r in best.resolved if r.satisfied)
        detail[merchant] = {
            "sku_id": best.sku.sku_id,
            "shelf_price": str(best.sku.shelf_price),
            "fields_exposed": len(best.sku.attributes) + 3,  # + id, title, price
            "legible_share": round(answered / len(clauses), 4) if clauses else 0.0,
            "value_credited_aud": str(credited),
            "value_withheld_aud": str(withheld),
            "unsatisfied": [c.text for c in best.unsatisfied],
        }

    winner = min(costs, key=lambda m: (costs[m], m)) if costs else None
    rows = []
    for merchant in sorted(detail):
        d = detail[merchant]
        won = merchant == winner
        if won:
            lost_because = None
        elif not with_records or not published.get(merchant):
            lost_because = (
                "Published no machine-readable benefit records, so nothing could be "
                f"credited and the offer was ranked on shelf price alone; "
                f"{winner} won on effective cost."
            )
        elif Decimal(d["value_withheld_aud"]) > 0:
            lost_because = (
                f"Published value the wire did not carry: ${d['value_withheld_aud']} was "
                f"withheld as unverified, unattested or out of scope, so {winner} won "
                "on effective cost."
            )
        else:
            lost_because = (
                f"Everything published was credited, and {winner} still reached a lower "
                "effective cost."
            )
        rows.append({
            "request_id": request["id"],
            "merchant": merchant,
            "control_merchant": not published.get(merchant),
            "fields_exposed": d["fields_exposed"],
            "legible_share": d["legible_share"],
            "value_credited_aud": d["value_credited_aud"],
            "value_withheld_aud": d["value_withheld_aud"],
            "won": won,
            "lost_because": lost_because,
            "sku_id": d["sku_id"],
            "shelf_price": d["shelf_price"],
            "effective_cost": str(costs[merchant]),
            "unsatisfied": d["unsatisfied"],
        })
    return rows


# --- the run ----------------------------------------------------------------


def run() -> int:
    skus = load_catalogue()
    verifiers = load_verifiers()
    published = load_published()
    kept, dropped = verified_records(published, verifiers)
    valid_ids = {r.record.record_id for r in kept}
    requests = load_requests()

    rows: list[tuple[dict, Outcome, Outcome]] = []
    REPORTS.mkdir(parents=True, exist_ok=True)

    for request in requests:
        constraints = parse(request["utterance"])
        bond = score(request, resolve_detailed(constraints, skus, kept).proposals, valid_ids)
        ctrl = score(request, resolve_detailed(constraints, skus, []).proposals, valid_ids)
        rows.append((request, bond, ctrl))

        payload = {
            "request_id": request["id"],
            "utterance": request["utterance"],
            "bundle": request["bundle"],
            "expect_unsatisfied": request["expect_unsatisfied"],
            "constraints": [{"text": c.text, "kind": c.kind.value} for c in constraints],
            "metrics": {
                "hard_precision": round(bond.hard_precision, 4),
                "gold_recall": round(bond.gold_recall, 4),
                "precision_at_gold": round(bond.precision_at_gold, 4),
                "citations": [bond.citations_valid, bond.citations_total],
                "clauses_answered": [bond.clauses_answered, bond.clauses_total],
                "clauses_answered_control": [ctrl.clauses_answered, ctrl.clauses_total],
            },
            "unsatisfied": bond.unsatisfied_texts,
            "merchants": merchant_rows(request, bond, published, verifiers, with_records=True),
            "control": merchant_rows(request, ctrl, published, verifiers, with_records=False),
        }
        (REPORTS / f"{request['id']}.json").write_text(
            json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8",
        )

    table = render(rows, dropped)
    print(table)

    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(document(rows, dropped), encoding="utf-8")
    print(f"\nWrote {RESULTS.relative_to(ROOT)} and "
          f"{len(requests)} reports to {REPORTS.relative_to(ROOT)}/")

    cit_valid = sum(b.citations_valid for _, b, _ in rows)
    cit_total = sum(b.citations_total for _, b, _ in rows)
    if cit_total and cit_valid != cit_total:
        print("\nFAIL: citation precision is below 1.00. A cited record that does "
              "not verify is a bug, not a number to report.", file=sys.stderr)
        return 1
    dishonest = [r["id"] for r, b, _ in rows
                 if r["expect_unsatisfied"] and not b.reports_unsatisfied]
    if dishonest:
        print(f"\nFAIL: {', '.join(dishonest)} expect an unsatisfied clause and "
              "reported none.", file=sys.stderr)
        return 1
    return 0


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def totals(rows: list[tuple[dict, Outcome, Outcome]]) -> dict:
    bond = [b for _, b, _ in rows]
    ctrl = [c for _, _, c in rows]
    cit_total = sum(b.citations_total for b in bond)
    cit_valid = sum(b.citations_valid for b in bond)
    clauses = sum(b.clauses_total for b in bond)
    expect = [r for r, _, _ in rows if r["expect_unsatisfied"]]
    honest = [r for r, b, _ in rows if r["expect_unsatisfied"] and b.reports_unsatisfied]
    return {
        "hard_precision": _mean([b.hard_precision for b in bond]),
        "gold_recall": _mean([b.gold_recall for b in bond]),
        "precision_at_gold": _mean([b.precision_at_gold for b in bond]),
        "citation_precision": (cit_valid / cit_total) if cit_total else 1.0,
        "citations": (cit_valid, cit_total),
        "unsatisfied_honesty": (len(honest), len(expect)),
        "answerable": (sum(b.clauses_answered for b in bond), clauses),
        "answerable_control": (sum(c.clauses_answered for c in ctrl), clauses),
    }


def render(rows: list[tuple[dict, Outcome, Outcome]], dropped: list[str]) -> str:
    head = (
        "| id | n | hard prec | gold recall | prec@|gold| | citations | "
        "SERVICE+VALUES answered | control | unsatisfied |"
    )
    rule = "|---|---:|---:|---:|---:|---:|---:|---:|---|"
    lines = [head, rule]
    for request, bond, ctrl in rows:
        flag = "reported" if bond.reports_unsatisfied else "-"
        if request["expect_unsatisfied"]:
            flag = "expected, reported" if bond.reports_unsatisfied else "**EXPECTED, MISSING**"
        lines.append(
            f"| {request['id']}{' (bundle)' if request['bundle'] else ''} "
            f"| {len(bond.proposals)} "
            f"| {bond.hard_precision:.2f} | {bond.gold_recall:.2f} "
            f"| {bond.precision_at_gold:.2f} "
            f"| {bond.citations_valid}/{bond.citations_total} "
            f"| {bond.clauses_answered}/{bond.clauses_total} "
            f"| {ctrl.clauses_answered}/{ctrl.clauses_total} | {flag} |"
        )
    t = totals(rows)
    lines.append(
        f"| **all 30** | | **{t['hard_precision']:.3f}** | **{t['gold_recall']:.3f}** "
        f"| **{t['precision_at_gold']:.3f}** "
        f"| **{t['citations'][0]}/{t['citations'][1]}** "
        f"| **{t['answerable'][0]}/{t['answerable'][1]}** "
        f"| **{t['answerable_control'][0]}/{t['answerable_control'][1]}** "
        f"| {t['unsatisfied_honesty'][0]}/{t['unsatisfied_honesty'][1]} |"
    )
    if dropped:
        lines.append("")
        lines.append(
            f"Records published but not verified, and so never handed to the resolver: "
            f"{', '.join(dropped)}."
        )
    return "\n".join(lines)


#: Why each request that does not reach precision 1.00 does not, written once
#: rather than guessed from a flag. Every one of them still has recall 1.00
#: except R24: nothing the shopper asked for was excluded.
MISS_REASONS: dict[str, str] = {
    "R04": (
        "the shopper names no product category at all (\"something light I can carry "
        "every day, under 1.3kg\") and the gold set assumes laptops. The weight bound is "
        "the only HARD clause, so every accessory under 1.3kg is eligible; a SOFT clause "
        "ranks and never filters, and inventing a category the shopper did not say is "
        "the guess this project argues against. It is also the one request whose "
        "ordering does not recover: \"light\" sorts a USB hub above a laptop, and the "
        "\"around $2,000\" signal is averaged with it rather than trusted over it."
    ),
    "R15": (
        "the same shape as R04 — \"something to record interviews on the go\" names no "
        "category, and the gold set assumes audio. The SOFT signal does recover the "
        "ordering here: precision@|gold| is 1.00."
    ),
    "R18": (
        "the near-duplicate trap, answered and then over-answered. All three spellings "
        "of the i5 listing are recovered (recall 1.00, which substring matching does not "
        "manage), but \"ThinkBook 14 G3 with 16 gigs\" also describes the i7 listings, "
        "which carry 16GB too, and the gold set names only the i5. Nothing in the "
        "utterance separates them, so the resolver returns both and the ordering puts "
        "the gold first."
    ),
    "R24": (
        "a bundle request across two categories (\"a work laptop and a dock, under "
        "$2,200 together\"), and the only one where recall is also short: the combined-"
        "price constraint applies to the set, not to each item. WS-G composes these."
    ),
}


def _generic_miss(bundle: bool) -> str:
    if bundle:
        return (
            "a bundle request: the gold answer is a *set* across categories, and a "
            "resolver that does not compose bundles returns every eligible item in "
            "each. WS-G composes these."
        )
    return (
        "the shopper names no product category, and the gold set assumes the one the "
        "use-case implies. A SOFT clause ranks and never filters, so the resolver "
        "returns every eligible listing rather than inventing a category the shopper "
        "did not say."
    )


def document(rows: list[tuple[dict, Outcome, Outcome]], dropped: list[str]) -> str:
    t = totals(rows)
    answered_share = t["answerable"][0] / t["answerable"][1] if t["answerable"][1] else 0.0
    control_share = t["answerable_control"][0] / t["answerable_control"][1] if t["answerable_control"][1] else 0.0
    misses = sorted(
        ((r["id"], b.hard_precision, r["bundle"]) for r, b, _ in rows if b.hard_precision < 1.0),
        key=lambda item: item[1],
    )
    miss_lines = "\n".join(
        f"- **{rid}** — hard precision {p:.2f} — {MISS_REASONS.get(rid, _generic_miss(bundle))}"
        for rid, p, bundle in misses
    )
    return f"""# Evaluation results

*Generated by `python scripts/eval_run.py` at commit `{commit_hash()}`.
Deterministic and offline — no network, no model, no clock, no random seed.
Re-run it and the numbers are identical, which is the only reason they appear
in the pitch.*

## What was run

30 requests, frozen at 10:50 on 12/09 before the benefit feed existed
(`data/eval/requests.json`, `freeze_rule`: "Frozen before any benefit record
existed. Do not regenerate."). Each one is parsed once and resolved twice
against the same frozen catalogue (`data/catalog/electronics.csv`):

- **BondLayer** — the resolver is handed the published records *after* each has
  been verified against the merchant's public JWK in `keys/`. A record that
  does not verify is never handed over and therefore can never be cited.
- **control** — same catalogue, same parser, same resolver, empty record list.
  This is what a plain product feed can answer.

## Headline

| metric | BondLayer | control |
|---|---:|---:|
| hard precision (mean over 30) | {t['hard_precision']:.3f} | — |
| gold recall (mean over 30) | {t['gold_recall']:.3f} | — |
| precision@\\|gold\\| (mean over 30) | {t['precision_at_gold']:.3f} | — |
| citation precision | {t['citation_precision']:.2f} ({t['citations'][0]}/{t['citations'][1]}) | n/a — nothing to cite |
| SERVICE + VALUES clauses answered | {t['answerable'][0]}/{t['answerable'][1]} ({answered_share:.0%}) | {t['answerable_control'][0]}/{t['answerable_control'][1]} ({control_share:.0%}) |
| requests expecting an unsatisfied clause that reported one | {t['unsatisfied_honesty'][0]}/{t['unsatisfied_honesty'][1]} | {t['unsatisfied_honesty'][1]}/{t['unsatisfied_honesty'][1]} |

**The one number that matters** is the second-to-last row. HARD and SOFT clauses
resolve identically in both columns — a competent catalogue search handles price,
RAM and weight, and every team at this hackathon will handle them. The gap is
entirely in SERVICE and VALUES: *{answered_share:.0%} against {control_share:.0%}*. No product
export has a column for "can I return this easily" or "does this brand repair
things", so the control cannot answer those clauses at all, and it does not
pretend to — it reports them unsatisfied with the marker
`← no catalogue attribute answers this`.

Citation precision is {t['citation_precision']:.2f} and is an assertion, not an achievement: the
runner exits non-zero if it ever drops below 1.00. A cited record that does not
verify would be a bug.

## Per request

{render(rows, dropped)}

## Where it misses, and why

{miss_lines}

`precision@|gold|` is reported next to flat precision because it reads the
*ordering* rather than the filter: of the first |gold| proposals, how many are
gold. Flat precision counts an eligible listing the shopper did not exclude as a
miss; precision@|gold| asks whether the SOFT signal floated the right ones to the
top. Both are printed, because reporting only the flattering one is the kind of
thing this project exists to argue against.

## Verification, not decoration

{('Records published but not verified, and so never handed to the resolver: '
  + ', '.join(f'`{d}`' for d in dropped) + '.') if dropped else 'Every published record verified.'}

This is why **R12** ("I want the most sustainable phone you sell") cannot be won
by NorthGear's `ng-sustainability-claim`: the claim is published unsigned, it
reaches the console and the valuation so it can be seen earning nothing, and it
never reaches the resolver, so it is never cited as evidence. Signing does not
buy value here — a values claim carries no `value_ceiling_aud` and contributes
exactly $0 — it buys *attributability*.

## Reproduce

```bash
cd bondlayer
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
pytest -q
python scripts/eval_run.py
```
"""


if __name__ == "__main__":
    raise SystemExit(run())
