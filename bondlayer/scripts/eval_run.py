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

**Decode accuracy**, reported separately from the five. FPT's top-weighted
criterion is how well the system *decodes* the shopper's need, and none of the
five measures the decode itself. So each request's ``parse(utterance)`` is also
scored against the ``constraints`` a human labelled in ``requests.json``: parsed
clauses are matched one-to-one to gold clauses of the same kind by token
overlap (lowercase alphanumeric tokens, a stated stopword set, a two-rule
stemmer), giving *decode precision* (matched / parsed) and *decode recall*
(matched / gold); a second text-only matching reports *kind confusions* -- the
clause was found and labelled the wrong kind. It is written to the same
document, the same reports, and stdout. It is a measure of the deterministic
rules parser against human labels, not of resolution. See ``decode_score``.

Outputs: ``docs/eval-results.md`` (commit hash, command, table) and one
``data/eval/reports/<id>.json`` per request, carrying a ``RequestReport``-shaped
row per merchant for the console to render.
"""

from __future__ import annotations

import json
import re
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
from bondlayer.bundle import compose as compose_bundles  # noqa: E402
from bondlayer.bundle import role_of  # noqa: E402
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


# --- decode accuracy: the parser against the human labels -------------------
#
# Everything in this section is additive and self-contained. It reads the gold
# ``constraints`` already frozen in ``requests.json`` and the parser's output,
# and it touches neither. If the parser is wrong, the number says so.

#: Dropped before matching. Deliberately tiny and stated in full: function
#: words that appear on one side of a clause boundary and not the other
#: ("I can return it easily" vs "can return easily").
DECODE_STOPWORDS = frozenset({
    "a", "an", "the", "i", "it", "to", "my", "that", "if", "from", "and", "is", "of",
})

#: Two clauses of the same kind match when their token sets overlap and either
#: the Jaccard similarity reaches this floor or one set is a subset of the other.
DECODE_JACCARD_FLOOR = 0.34


def _decode_stem(token: str) -> str:
    """The whole stemmer: strip one trailing ``ing``, else one trailing ``s``.

    Only when at least three characters remain, so "thing" keeps its "ing"
    and "gigs" becomes "gig". "suits my work" and "not to suit my work" have to
    meet; anything cleverer than this is a second parser, and the point is to
    measure the one we have.
    """
    if token.endswith("ing") and len(token) - 3 >= 3:
        return token[:-3]
    if token.endswith("s") and len(token) - 1 >= 3:
        return token[:-1]
    return token


def _decode_tokens(text: str) -> frozenset[str]:
    """Lowercase alphanumeric runs, minus the stopwords, stemmed."""
    raw = re.findall(r"[a-z0-9]+", text.lower())
    return frozenset(_decode_stem(t) for t in raw if t not in DECODE_STOPWORDS)


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _clause_kind(clause) -> str:
    """The kind as a lowercase string, whatever the source spelled it as.

    Gold clauses are dicts with ``"kind": "HARD"``; parsed clauses are
    ``Constraint`` objects with a ``ConstraintKind`` whose value is ``"hard"``.
    """
    kind = clause["kind"] if isinstance(clause, dict) else clause.kind
    return str(getattr(kind, "value", kind)).lower()


def _clause_text(clause) -> str:
    return clause["text"] if isinstance(clause, dict) else clause.text


def _decode_pairs(gold: list, parsed: list, *, by_kind: bool) -> list[tuple[int, int]]:
    """Greedy one-to-one matching, highest Jaccard first, then index order.

    A candidate pair needs a non-empty token intersection and either Jaccard
    at or above ``DECODE_JACCARD_FLOOR`` or a subset relation in either
    direction. With ``by_kind`` the kinds must also agree; without it the
    match is on text alone, which is the pass that exposes a clause the parser
    found but labelled the wrong kind.
    """
    g_tokens = [_decode_tokens(_clause_text(c)) for c in gold]
    p_tokens = [_decode_tokens(_clause_text(c)) for c in parsed]
    candidates: list[tuple[float, int, int]] = []
    for gi, gt in enumerate(g_tokens):
        for pi, pt in enumerate(p_tokens):
            if by_kind and _clause_kind(gold[gi]) != _clause_kind(parsed[pi]):
                continue
            if not (gt & pt):
                continue
            j = _jaccard(gt, pt)
            if j >= DECODE_JACCARD_FLOOR or gt <= pt or pt <= gt:
                candidates.append((j, gi, pi))
    candidates.sort(key=lambda c: (-c[0], c[1], c[2]))
    used_g: set[int] = set()
    used_p: set[int] = set()
    pairs: list[tuple[int, int]] = []
    for _, gi, pi in candidates:
        if gi in used_g or pi in used_p:
            continue
        used_g.add(gi)
        used_p.add(pi)
        pairs.append((gi, pi))
    return sorted(pairs)


@dataclass
class Decode:
    """One request's parse, scored against the human-labelled constraints.

    ``precision`` and ``recall`` come from the kind-aware matching: a parsed
    clause counts only if a gold clause of the same kind says the same thing.
    ``kind_confusions`` come from a second, text-only matching: pairs that say
    the same thing but disagree on kind. ``kind_accuracy`` is the share of
    text-matched pairs whose kinds agree -- under the kind-aware matching it
    would be 1.0 by construction, so it is computed over the text-only pairs,
    where it can actually be wrong.
    """

    gold: list[dict]
    parsed: list[dict]
    pairs: list[dict]
    precision: float
    recall: float
    kind_accuracy: float
    kind_confusions: list[dict]
    misses: list[dict]
    extras: list[dict]

    @property
    def matched(self) -> int:
        return len(self.pairs)

    @property
    def perfect(self) -> bool:
        return self.precision == 1.0 and self.recall == 1.0 and not self.kind_confusions

    def as_json(self) -> dict:
        return {
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "kind_accuracy": round(self.kind_accuracy, 4),
            "matched": self.matched,
            "gold_total": len(self.gold),
            "parsed_total": len(self.parsed),
            "perfect": self.perfect,
            "pairs": self.pairs,
            "misses": self.misses,
            "extras": self.extras,
            "kind_confusions": self.kind_confusions,
        }


def decode_score(gold: list, parsed: list) -> Decode:
    """Score ``parse(utterance)`` against the request's gold ``constraints``.

    Deterministic: no clock, no randomness, no model. The only inputs are the
    two clause lists.
    """
    gold_out = [{"text": _clause_text(c), "kind": _clause_kind(c).upper()} for c in gold]
    parsed_out = [{"text": _clause_text(c), "kind": _clause_kind(c)} for c in parsed]

    kind_pairs = _decode_pairs(gold, parsed, by_kind=True)
    matched = len(kind_pairs)
    # Emitting nothing produces no false positive: precision is 1.0 (vacuously)
    # and recall, not precision, scores what was missed. Emitting clauses the
    # labeller never wrote scores 0 / n = 0.0.
    precision = (matched / len(parsed)) if parsed else 1.0
    # Nothing labelled means nothing to miss: recall is 1.0 and precision, not
    # recall, scores whatever the parser invented.
    recall = (matched / len(gold)) if gold else 1.0

    text_pairs = _decode_pairs(gold, parsed, by_kind=False)
    confusions = [
        {
            "gold": gold_out[gi]["text"], "gold_kind": gold_out[gi]["kind"],
            "parsed": parsed_out[pi]["text"], "parsed_kind": parsed_out[pi]["kind"],
        }
        for gi, pi in text_pairs
        if gold_out[gi]["kind"].lower() != parsed_out[pi]["kind"]
    ]
    kind_accuracy = (
        (len(text_pairs) - len(confusions)) / len(text_pairs) if text_pairs else 1.0
    )

    matched_g = {gi for gi, _ in kind_pairs}
    matched_p = {pi for _, pi in kind_pairs}
    return Decode(
        gold=gold_out,
        parsed=parsed_out,
        pairs=[
            {
                "gold": gold_out[gi]["text"], "gold_kind": gold_out[gi]["kind"],
                "parsed": parsed_out[pi]["text"], "parsed_kind": parsed_out[pi]["kind"],
            }
            for gi, pi in kind_pairs
        ],
        precision=precision,
        recall=recall,
        kind_accuracy=kind_accuracy,
        kind_confusions=confusions,
        misses=[gold_out[i] for i in range(len(gold_out)) if i not in matched_g],
        extras=[parsed_out[i] for i in range(len(parsed_out)) if i not in matched_p],
    )


def decode_totals(decodes: dict[str, Decode]) -> dict:
    values = [decodes[k] for k in sorted(decodes)]
    return {
        "precision": _mean([d.precision for d in values]),
        "recall": _mean([d.recall for d in values]),
        "kind_accuracy": _mean([d.kind_accuracy for d in values]),
        "confusions": sum(len(d.kind_confusions) for d in values),
        "perfect": (sum(1 for d in values if d.perfect), len(values)),
        "gold_total": sum(len(d.gold) for d in values),
        "parsed_total": sum(len(d.parsed) for d in values),
        "matched": sum(d.matched for d in values),
    }


def _decode_cell(items: list[dict]) -> str:
    return "; ".join(f"{i['text']} ({i['kind']})" for i in items) if items else "—"


def _confusion_cell(items: list[dict]) -> str:
    if not items:
        return "—"
    return "; ".join(
        f"{i['gold']} ({i['gold_kind']}) → {i['parsed']} ({i['parsed_kind']})" for i in items
    )


def render_decode(rows: list[tuple[dict, Outcome, Outcome]],
                  decodes: dict[str, Decode]) -> str:
    """The per-request decode table, all 30 rows, with the aggregate last."""
    head = ("| id | gold | parsed | matched | decode prec | decode recall "
            "| kind confusions | misses (gold, unmatched) | extras (parsed, unmatched) |")
    rule = "|---|---:|---:|---:|---:|---:|---|---|---|"
    lines = [head, rule]
    for request, _bond, _ctrl in rows:
        d = decodes[request["id"]]
        lines.append(
            f"| {request['id']} | {len(d.gold)} | {len(d.parsed)} | {d.matched} "
            f"| {d.precision:.2f} | {d.recall:.2f} "
            f"| {_confusion_cell(d.kind_confusions)} "
            f"| {_decode_cell(d.misses)} | {_decode_cell(d.extras)} |"
        )
    t = decode_totals(decodes)
    lines.append(
        f"| **all {len(decodes)}** | **{t['gold_total']}** | **{t['parsed_total']}** "
        f"| **{t['matched']}** | **{t['precision']:.3f}** | **{t['recall']:.3f}** "
        f"| **{t['confusions']}** | | perfect decodes: **{t['perfect'][0]}/{t['perfect'][1]}** |"
    )
    return "\n".join(lines)


#: Why each request that does not decode perfectly does not, written once. A
#: note is rendered only while its request is still imperfect, so a parser fix
#: retires the note with the miss. None of these is fixed here: the parser is
#: another owner's file, and the gold is frozen.
DECODE_NOTES: dict[str, str] = {
    "R02": (
        "the parser emits `laptop` as a HARD clause and the labeller did not list it. "
        "The labels are not consistent on this: R16 and R28 do label the bare category "
        "noun. The gold is frozen, so this reads as an extra."
    ),
    "R03": (
        "the same category-noun extra as R02: `laptop` is decoded and not labelled."
    ),
    "R04": (
        "`light` is decoded as its own SOFT clause; the labeller folded it into "
        "\"carry every day\". One extra, nothing missed."
    ),
    "R10": (
        "two extras: the unlabelled category noun `laptop`, and \"money is not really "
        "the issue\", which the parser reads as a SOFT budget hedge and the labeller "
        "treated as no constraint at all. Nothing missed."
    ),
    "R14": (
        "a kind confusion: the labeller wrote \"headset for calls\" as one SOFT "
        "use-case clause; the parser decodes `headset` as a HARD category and drops "
        "\"for calls\" entirely. Kind-aware matching therefore scores it as one miss "
        "and one extra; the text-only pass names the confusion (SOFT → hard)."
    ),
    "R24": (
        "a kind confusion of the same shape as R14: \"work laptop\" is labelled SOFT "
        "(the *work* is the use-case) and decoded as the HARD category `laptop`, with "
        "\"work\" lost. The bundle's combined-price clause and `dock` both match."
    ),
    "R25": (
        "the unlabelled category noun `laptop` again; the four labelled clauses, "
        "including `gaming` as SOFT, all match."
    ),
    "R29": (
        "the unlabelled category noun `laptop`; \"I care where it's made\" matches "
        "the parser's \"where it's made\" as a subset."
    ),
}


def decode_section(rows: list[tuple[dict, Outcome, Outcome]],
                   decodes: dict[str, Decode]) -> str:
    """The ``## Decode accuracy`` section of the results document."""
    t = decode_totals(decodes)
    imperfect = [(r["id"], decodes[r["id"]]) for r, _, _ in rows if not decodes[r["id"]].perfect]
    perfect_ids = [r["id"] for r, _, _ in rows if decodes[r["id"]].perfect]
    notes = "\n".join(
        f"- **{rid}** — precision {d.precision:.2f}, recall {d.recall:.2f} — "
        f"{DECODE_NOTES.get(rid, 'no note written for this miss yet; read the misses and extras columns above.')}"
        for rid, d in imperfect
    ) or "- Every request decodes perfectly."
    return f"""## Decode accuracy

FPT's top-weighted criterion is how well the merchant's system *decodes* the
shopper's nuanced need. The tables above score *resolution* — what came back
from the catalogue and the records. This one scores the decode on its own:
`interpreter.parse(utterance)` against the `constraints` a human labelled in
`data/eval/requests.json` (text and kind), for all 30 frozen requests.

**What it does.** Each parsed clause is matched one-to-one to a gold clause,
highest Jaccard first, when the kinds agree (compared lowercase) *and* the
token sets overlap with Jaccard ≥ {DECODE_JACCARD_FLOOR} or one set is a subset of
the other. Tokens are lowercase alphanumeric runs, minus the stopwords
`{', '.join(sorted(DECODE_STOPWORDS))}`, then stemmed by stripping one trailing
`ing`, else one trailing `s`, only when three or more characters remain — so
"suits my work" meets the parser's "not to suit my work", "repairs things"
becomes `repair thing`, "16 gigs" becomes `16 gig`, and "thing" keeps its `ing`. *Decode precision* is matched ÷ parsed,
*decode recall* is matched ÷ gold. A second, text-only matching ignores kind;
a pair it finds whose kinds differ is a **kind confusion** — the parser found the
clause and labelled it wrong — and *kind accuracy* is the share of text-matched
pairs whose kinds agree. A request is a **perfect decode** when precision and
recall are both 1.00 and there is no confusion.

**What it does not show.** It measures a deterministic rules parser against
30 human labels; it is not a resolution metric, and a clause that matches on
tokens can still resolve to the wrong attribute. An *extra* is a clause the
parser emitted that the labeller did not write down, and on this set that is
almost always the bare category noun (`laptop`), which the labels list on some
requests and not others — the gold is frozen, so the inconsistency is reported,
not corrected. A *miss* is a labelled clause the parser did not emit at all,
or emitted under a different kind. Nothing here is tuned to the gold: the
stopword list and the stemmer are stated in full above and pinned by
`tests/test_decode_metric.py`.

| decode metric | value |
|---|---:|
| decode precision (mean over {len(decodes)}) | {t['precision']:.3f} |
| decode recall (mean over {len(decodes)}) | {t['recall']:.3f} |
| kind accuracy (mean over {len(decodes)}, text-matched pairs) | {t['kind_accuracy']:.3f} |
| kind confusions (total) | {t['confusions']} |
| perfect decodes | {t['perfect'][0]}/{t['perfect'][1]} |
| clauses: gold / parsed / matched | {t['gold_total']} / {t['parsed_total']} / {t['matched']} |

{render_decode(rows, decodes)}

### Known parser misses, reported not fixed

{notes}

Perfect decodes ({len(perfect_ids)}): {', '.join(perfect_ids) if perfect_ids else 'none'}.

"""


# --- end of decode accuracy --------------------------------------------------


# --- bundling: scoring a set against a gold set -----------------------------


@dataclass
class BundleScore:
    """One ``(bundle)`` request's composed set, scored against its gold set.

    Flat precision and recall score a *list*; three of these requests have a
    *set* for an answer, and "did the resolver return all 34 audio SKUs" is not
    the question the shopper asked. This reads the composed bundle instead: how
    many items, from how many merchants, at what combined price, and how many
    of those items the frozen gold set contains.

    ``in_gold`` is precision over the items actually composed, not over the
    whole returned shelf. It is the number that says whether the set is made of
    things the shopper asked for.
    """

    bundle_id: str
    merchant: str
    items: list[str]
    roles: list[str]
    combined: Decimal
    in_gold: int
    outside_gold: list[str]
    ceiling_ok: bool | None

    @property
    def precision(self) -> float:
        return self.in_gold / len(self.items) if self.items else 0.0


def score_bundle(request: dict, proposals: list[Proposal]) -> BundleScore | None:
    """Compose a set for this request and score it. ``None`` if none composed."""
    constraints = parse(request["utterance"])
    bundles = compose_bundles(constraints, proposals)
    if not bundles:
        return None
    best = bundles[0]
    gold = set(request["gold_skus"])
    got = [p.sku.sku_id for p in best.items]
    ceiling = [r.satisfied for r in best.resolved
               if r.evidence_attribute == "combined_shelf_price"]
    return BundleScore(
        bundle_id=best.bundle_id,
        merchant=str(best.items[0].sku.attributes.get("merchant", "")),
        items=got,
        roles=[role_of(p) or p.sku.category for p in best.items],
        combined=best.combined_shelf_price,
        in_gold=len([s for s in got if s in gold]),
        outside_gold=[s for s in got if s not in gold],
        ceiling_ok=all(ceiling) if ceiling else None,
    )


def bundle_column(request: dict, score: BundleScore | None) -> str:
    """The extra column: a set's answer, or a dash where a set is not asked for."""
    if not request["bundle"]:
        return "—"
    if score is None:
        return "**none composed**"
    return (f"{score.in_gold}/{len(score.items)} in gold, "
            f"${score.combined:,.2f}")


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
    # Captured before anything is written: the hash describes the code that was
    # run, and this run is about to modify its own tracked outputs.
    at_commit = commit_hash()
    skus = load_catalogue()
    verifiers = load_verifiers()
    published = load_published()
    kept, dropped = verified_records(published, verifiers)
    valid_ids = {r.record.record_id for r in kept}
    requests = load_requests()

    rows: list[tuple[dict, Outcome, Outcome]] = []
    bundle_scores: dict[str, BundleScore | None] = {}
    decodes: dict[str, Decode] = {}
    REPORTS.mkdir(parents=True, exist_ok=True)

    for request in requests:
        constraints = parse(request["utterance"])
        bond = score(request, resolve_detailed(constraints, skus, kept).proposals, valid_ids)
        ctrl = score(request, resolve_detailed(constraints, skus, []).proposals, valid_ids)
        rows.append((request, bond, ctrl))

        # Composed from the same proposals that were just scored -- the bundler
        # never re-matches, so this adds no resolution work and cannot change
        # any metric above.
        bundle = score_bundle(request, bond.proposals)
        bundle_scores[request["id"]] = bundle

        # The decode, scored against the human labels. Reads the parse and the
        # gold and nothing else; it cannot move any resolution metric above.
        decodes[request["id"]] = decode_score(request["constraints"], constraints)

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
            "bundle_composed": None if bundle is None else {
                "bundle_id": bundle.bundle_id,
                "merchant": bundle.merchant,
                "items": bundle.items,
                "roles": bundle.roles,
                "combined_shelf_price": str(bundle.combined),
                "in_gold": bundle.in_gold,
                "outside_gold": bundle.outside_gold,
                "gold_precision": round(bundle.precision, 4),
                "combined_ceiling_met": bundle.ceiling_ok,
            },
            "merchants": merchant_rows(request, bond, published, verifiers, with_records=True),
            "control": merchant_rows(request, ctrl, published, verifiers, with_records=False),
            "decode": decodes[request["id"]].as_json(),
        }
        (REPORTS / f"{request['id']}.json").write_text(
            json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8",
        )

    table = render(rows, dropped, bundle_scores)
    print(table)
    print()
    print(render_decode(rows, decodes))

    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(document(rows, dropped, at_commit, bundle_scores,
                                decodes=decodes),
                       encoding="utf-8")
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


def render(rows: list[tuple[dict, Outcome, Outcome]], dropped: list[str],
           bundles: dict[str, BundleScore | None] | None = None) -> str:
    bundles = bundles or {}
    head = (
        "| id | n | hard prec | gold recall | prec@|gold| | citations | "
        "SERVICE+VALUES answered | control | bundle | unsatisfied |"
    )
    rule = "|---|---:|---:|---:|---:|---:|---:|---:|---|---|"
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
            f"| {ctrl.clauses_answered}/{ctrl.clauses_total} "
            f"| {bundle_column(request, bundles.get(request['id']))} | {flag} |"
        )
    t = totals(rows)
    lines.append(
        f"| **all 30** | | **{t['hard_precision']:.3f}** | **{t['gold_recall']:.3f}** "
        f"| **{t['precision_at_gold']:.3f}** "
        f"| **{t['citations'][0]}/{t['citations'][1]}** "
        f"| **{t['answerable'][0]}/{t['answerable'][1]}** "
        f"| **{t['answerable_control'][0]}/{t['answerable_control'][1]}** "
        f"| | {t['unsatisfied_honesty'][0]}/{t['unsatisfied_honesty'][1]} |"
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


def bundle_section(rows: list[tuple[dict, Outcome, Outcome]],
                   bundles: dict[str, BundleScore | None]) -> str:
    """What the three ``(bundle)`` requests got, as sets.

    These three are the requests flat precision reads worst, and for a reason
    that is not a bug: their gold answer is a *set*, and a resolver that does
    not compose returns every eligible item in every eligible category. The
    bundler's output is scored here instead -- precision over the items it
    actually put in the set.
    """
    lines = []
    for request, _bond, _ctrl in rows:
        if not request["bundle"]:
            continue
        score = bundles.get(request["id"])
        if score is None:
            lines.append(f"- **{request['id']}** — no set composed.")
            continue
        listed = ", ".join(f"`{s}` ({r})" for s, r in zip(score.items, score.roles))
        line = (
            f"- **{request['id']}** — {len(score.items)} items from "
            f"**{score.merchant}**, combined **${score.combined:,.2f}**, "
            f"{score.in_gold}/{len(score.items)} in the frozen gold set "
            f"(precision {score.precision:.2f}). {listed}."
        )
        if score.ceiling_ok is not None:
            line += (" Combined-price ceiling met."
                     if score.ceiling_ok else " **Combined-price ceiling missed.**")
        if score.outside_gold:
            line += (f" Outside gold: {', '.join(f'`{s}`' for s in score.outside_gold)}.")
        lines.append(line)
    return "\n".join(lines)


def document(rows: list[tuple[dict, Outcome, Outcome]], dropped: list[str],
             at_commit: str,
             bundles: dict[str, BundleScore | None] | None = None,
             decodes: dict[str, Decode] | None = None) -> str:
    bundles = bundles or {}
    decode_t = decode_totals(decodes) if decodes else None
    decode_rows = (
        f"| decode precision (mean over {len(decodes)}) | {decode_t['precision']:.3f} | — |\n"
        f"| decode recall (mean over {len(decodes)}) | {decode_t['recall']:.3f} | — |\n"
        f"| kind confusions (total) | {decode_t['confusions']} | — |\n"
        f"| perfect decodes (precision = recall = 1.00, no confusion) | "
        f"{decode_t['perfect'][0]}/{decode_t['perfect'][1]} | — |\n"
        if decode_t else ""
    )
    decode_doc = decode_section(rows, decodes) if decodes else ""
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

*Generated by `python scripts/eval_run.py` at commit `{at_commit}`.
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
{decode_rows}| citation precision | {t['citation_precision']:.2f} ({t['citations'][0]}/{t['citations'][1]}) | n/a — nothing to cite |
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

{render(rows, dropped, bundles)}

{decode_doc}## Dynamic bundling

Three of the thirty requests have a **set** for a gold answer, and they are the
three flat precision reads worst — not because the matching is wrong but
because the question is. "Everything I need to start a podcast" is answered by a
microphone, headphones, an interface and a cable, not by all 34 audio SKUs, and
a resolver that does not compose can only return the latter. The `bundle` column
scores what the bundler actually composed: how many of the items it put in the
set are in the frozen gold set, and what the set costs all up.

{bundle_section(rows, bundles)}

The bundler composes from the proposals the resolver already returned and never
re-matches, so nothing in the table above moves because bundling exists — the
flat precision and recall figures for R06, R07 and R24 are exactly what they
were. It is an additional answer, not a correction to the old one.

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
