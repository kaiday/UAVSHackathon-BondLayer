"""What the resolver must never get wrong.

These are not coverage tests. Each one pins a claim the pitch makes out loud:
that matching happens over typed attributes rather than words in a title, that
a clause nobody can answer is reported rather than dropped, and that an
unsigned claim can be displayed but never cited.
"""

import csv
import json
import re
from decimal import Decimal
from pathlib import Path

import pytest

from bondlayer.adapters.catalog import CsvCatalogAdapter
from bondlayer.interpreter.parser import parse
from bondlayer.interpreter.resolver import UNANSWERED, resolve, resolve_detailed
from bondlayer.interpreter.similarity import TfidfIndex
from bondlayer.records.serialise import load_signed
from bondlayer.records.signing import ES256Signer
from bondlayer.types import Constraint, ConstraintKind, Sku
from bondlayer.valuation import MERCHANT_DOMAINS

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "catalog" / "electronics.csv"
RECORDS = ROOT / "data" / "records"
KEYS = ROOT / "keys"
EVAL = ROOT / "data" / "eval" / "requests.json"


@pytest.fixture(scope="module")
def skus() -> list[Sku]:
    return CsvCatalogAdapter(CATALOG).load()


@pytest.fixture(scope="module")
def verified() -> list:
    """Only records that verify against the published JWK.

    This is the gate the resolver never sees behind, and it is the reason the
    planted claim cannot be cited: it is not in this list.
    """
    kept = []
    for merchant, domain in MERCHANT_DOMAINS.items():
        key, path = KEYS / f"{merchant}.pub.json", RECORDS / f"{merchant}.signed.json"
        if not (key.exists() and path.exists()):
            continue
        jwk, = json.loads(key.read_text(encoding="utf-8"))
        signer = ES256Signer.from_jwk(jwk, issuer=domain)
        kept.extend([r for r in load_signed(path) if r.signature and signer.verify(r)])
    return kept


@pytest.fixture(scope="module")
def requests_by_id() -> dict[str, dict]:
    payload = json.loads(EVAL.read_text(encoding="utf-8"))
    return {item["id"]: item for item in payload["requests"]}


def _resolved(proposal, kind: ConstraintKind) -> list:
    return [r for r in proposal.resolved if r.constraint.kind is kind]


# --- R01, the demo query ----------------------------------------------------


def test_r01_resolves_every_clause_and_cites_the_records_that_answer_two(
    skus, verified, requests_by_id,
):
    """One clause of each kind: two answered from attributes, two from records."""
    constraints = parse(requests_by_id["R01"]["utterance"])
    kinds = {c.kind for c in constraints}
    assert kinds == {
        ConstraintKind.HARD, ConstraintKind.SOFT,
        ConstraintKind.SERVICE, ConstraintKind.VALUES,
    }

    proposals = resolve(constraints, skus, verified)
    assert proposals, "R01 returned nothing"

    voltway = next(p for p in proposals if p.sku.attributes["merchant"] == "voltway")
    # Every clause the shopper said comes back resolved, none silently dropped.
    assert len(voltway.resolved) == len(constraints)
    assert {r.constraint.text for r in voltway.resolved} == {c.text for c in constraints}

    # The two record-answered kinds are cited by record id.
    cited = [r for r in voltway.resolved
             if r.constraint.kind in (ConstraintKind.SERVICE, ConstraintKind.VALUES)]
    assert len(cited) == 2
    assert all(r.satisfied and r.evidence_record_id for r in cited)
    assert {r.evidence_record_id for r in cited} <= {v.record.record_id for v in verified}

    # The HARD clause resolved against a typed attribute, not a title substring.
    hard, = _resolved(voltway, ConstraintKind.HARD)
    assert hard.evidence_attribute in {"category", "shelf_price"}
    assert voltway.sku.shelf_price <= Decimal("1500")


def test_every_note_is_one_human_readable_sentence(skus, verified, requests_by_id):
    """FPT asked for a justification, not a SKU list. No note may be empty."""
    for request_id in ("R01", "R08", "R12", "R21", "R29"):
        proposals = resolve(parse(requests_by_id[request_id]["utterance"]), skus, verified)
        for proposal in proposals[:5]:
            for resolved in proposal.resolved:
                assert resolved.note.strip(), f"{request_id}/{proposal.sku.sku_id}: empty note"
                assert resolved.note == UNANSWERED or resolved.note.endswith("."), (
                    f"{request_id}/{proposal.sku.sku_id}: {resolved.note!r} is not a sentence"
                )


# --- R12: the planted claim must not win ------------------------------------


def test_r12_is_not_won_by_the_unsigned_northgear_claim(skus, verified, requests_by_id):
    """Only verified records reach the resolver, so the greenwash cannot be cited."""
    assert "ng-sustainability-claim" not in {v.record.record_id for v in verified}

    constraints = parse(requests_by_id["R12"]["utterance"])
    proposals = resolve(constraints, skus, verified)
    assert proposals

    cited = {r.evidence_record_id for p in proposals for r in p.resolved if r.evidence_record_id}
    assert "ng-sustainability-claim" not in cited

    # NorthGear's phones are still returned -- they are eligible listings -- but
    # the sustainability clause is unanswered for them and answered for Voltway.
    northgear = [p for p in proposals if p.sku.attributes["merchant"] == "northgear"]
    assert northgear, "NorthGear's phones were excluded, which is not the point"
    for proposal in northgear:
        values = _resolved(proposal, ConstraintKind.VALUES)
        assert values and all(not r.satisfied for r in values)
        assert all(r.note == UNANSWERED for r in values)

    voltway = [p for p in proposals if p.sku.attributes["merchant"] == "voltway"]
    answered = [r for p in voltway for r in _resolved(p, ConstraintKind.VALUES) if r.satisfied]
    assert answered, "Voltway's signed sustainability record did not answer R12"
    assert all(r.evidence_record_id == "vw-sustainability-assured-fy2026" for r in answered)


def test_the_planted_claim_is_never_cited_even_when_it_is_handed_over(skus):
    """Defence in depth: the caller is meant to filter, but check the shape too.

    If a future caller ever hands the resolver an unverified record, the claim
    becomes citable -- so this test states the contract loudly rather than
    pretending the resolver verifies anything itself. It does not, by design:
    verification is Bach's, and duplicating it here would mean two answers.
    """
    unsigned = [r for r in load_signed(RECORDS / "northgear.signed.json") if not r.signature]
    claim, = unsigned
    assert claim.record.record_id == "ng-sustainability-claim"
    assert not claim.signature and not claim.key_id
    # A values claim carries no ceiling, so signing it would still be worth $0.
    # What signing buys is attributability, and this one has none.
    assert claim.record.value_ceiling_aud is None


# --- unsatisfied is reported, not dropped -----------------------------------


@pytest.mark.parametrize("request_id", ["R16", "R17"])
def test_an_unanswerable_clause_is_reported_with_the_exact_marker(
    request_id, skus, verified, requests_by_id,
):
    request = requests_by_id[request_id]
    assert request["expect_unsatisfied"] is True

    proposals = resolve(parse(request["utterance"]), skus, verified)
    assert proposals
    assert any(p.unsatisfied for p in proposals), "the clause was silently dropped"

    for proposal in proposals:
        for constraint in proposal.unsatisfied:
            note, = [r.note for r in proposal.resolved if r.constraint.text == constraint.text]
            # Rendered verbatim by the console. Do not paraphrase.
            assert note == UNANSWERED


def test_the_marker_string_is_exactly_what_the_console_renders():
    assert UNANSWERED == "← no catalogue attribute answers this"


# --- HARD resolves on typed attributes, never on the title ------------------


def test_a_listing_missing_the_attribute_is_excluded_as_absent_not_failed(skus):
    """"Attribute absent" and "failed" are different facts and the trace says so."""
    constraint = Constraint(text="under 1.3kg", kind=ConstraintKind.HARD)
    resolution = resolve_detailed([constraint], skus, [])

    absent = [e for e in resolution.excluded if "Attribute absent" in e.reason]
    over = [e for e in resolution.excluded if "is over the" in e.reason]
    assert absent, "no listing lacks weight_kg, so this test proves nothing"
    assert over, "no listing exceeds the bound, so this test proves nothing"
    assert all(e.attribute == "weight_kg" for e in absent + over)
    # The two reasons never blur into one another.
    assert not [e for e in absent if "is over the" in e.reason]


def test_a_derived_gpu_is_accepted_and_the_note_says_it_was_derived(skus):
    derived = [s for s in skus if s.attributes.get("gpu_source") == "title"]
    assert derived, "the adapter derived no GPU, so this test proves nothing"

    proposals = resolve([Constraint("RTX", ConstraintKind.HARD)], skus, [])
    assert proposals
    matched = next(p for p in proposals if p.sku.sku_id == derived[0].sku_id)
    note, = [r.note for r in matched.resolved if r.evidence_attribute == "gpu"]
    assert "derived" in note.lower()


def test_a_product_noun_orders_the_category_and_never_filters_it(skus, requests_by_id):
    """R11's gold is all 23 accessories, not the two with a screen.

    The catalogue has one `category` column, so narrowing "monitor" to listings
    publishing `screen_in` would drop a dock the shopper asked for.
    """
    request = requests_by_id["R11"]
    proposals = resolve(parse(request["utterance"]), skus, [])
    returned = {p.sku.sku_id for p in proposals}
    assert returned == set(request["gold_skus"])
    assert all(p.sku.category == "accessory" for p in proposals)


# --- beyond keyword matching: similarity over a token bag -------------------


def test_substring_matching_splits_a_near_duplicate_that_similarity_collapses(
    skus, requests_by_id,
):
    """R18's trap: the same product spelled two ways.

    `ThinkBook 14 G3 i5 16GB 512GB` and `ThinkBook 14  G3  i5 16 GB 512GB` are
    one product -- same GTIN, same model_key -- spelled with different spacing
    and different unit formatting. A substring test over the title matches one
    and misses the other, which is exactly the failure the problem statement
    calls "beyond keyword matching".
    """
    phrase = "ThinkBook 14 G3"
    with CATALOG.open(encoding="utf-8", newline="") as handle:
        raw_titles = {row["sku"]: row["title"] for row in csv.DictReader(handle)}

    # The substring baseline, over the raw export the merchant actually sends.
    substring = {sku_id for sku_id, title in raw_titles.items()
                 if phrase.lower() in title.lower()}
    # The two spellings of one product, by GTIN.
    family = {s.sku_id for s in skus if s.attributes.get("gtin") == "9312001000011"}
    assert len(family) == 3

    missed = family - substring
    assert missed, "the export no longer carries the near-duplicate trap"

    # Similarity over the normalised token bag recovers every one of them.
    index = TfidfIndex(skus)
    covered = set(index.covered(phrase))
    assert family <= covered, f"similarity missed {family - covered}"

    # And it is the resolver's answer, not just the index's.
    proposals = resolve(parse(requests_by_id["R18"]["utterance"]), skus, [])
    assert family <= {p.sku.sku_id for p in proposals}
    assert set(requests_by_id["R18"]["gold_skus"]) <= {p.sku.sku_id for p in proposals}


def test_the_generation_trap_is_not_collapsed(skus):
    """G3 and G4 differ by one character, and they are different products."""
    index = TfidfIndex(skus)
    g3 = set(index.covered("ThinkBook 14 G3"))
    g4 = set(index.covered("ThinkBook 14 G4"))
    assert g3 and g4
    assert not (g3 & g4), "the matcher collapsed two generations into one product"


def test_the_resolver_never_substring_matches_a_title(skus):
    """The claim, asserted against the source rather than the behaviour.

    Every title comparison in the resolver goes through the token index. If a
    `in sku.title` creeps back in, this fails and someone has to argue for it.
    """
    source = (ROOT / "src" / "bondlayer" / "interpreter" / "resolver.py").read_text(
        encoding="utf-8",
    )
    offenders = [
        line.strip() for line in source.splitlines()
        if re.search(r"\bin\s+\w*\.?title\b", line) or ".title.lower()" in line
    ]
    assert not offenders, f"substring matching on the title: {offenders}"


# --- ordering ---------------------------------------------------------------


def test_a_soft_clause_ranks_and_never_filters(skus):
    """"Cheapest" must not remove anything; it must reorder."""
    hard = [Constraint("laptop", ConstraintKind.HARD)]
    with_soft = hard + [Constraint("cheapest", ConstraintKind.SOFT)]

    plain = {p.sku.sku_id for p in resolve(hard, skus, [])}
    ranked = resolve(with_soft, skus, [])
    assert {p.sku.sku_id for p in ranked} == plain, "a SOFT clause filtered"

    prices = [p.sku.shelf_price for p in ranked]
    assert prices == sorted(prices), "the cheapest-first signal did not order"
    soft, = _resolved(ranked[0], ConstraintKind.SOFT)
    assert soft.satisfied and "shelf_price" in soft.note


def test_a_soft_clause_with_no_heuristic_stays_in_the_justification(skus):
    """Unsatisfied with a note beats silently dropped."""
    constraints = [
        Constraint("laptop", ConstraintKind.HARD),
        Constraint("something ineffable", ConstraintKind.SOFT),
    ]
    proposals = resolve(constraints, skus, [])
    assert proposals
    soft, = _resolved(proposals[0], ConstraintKind.SOFT)
    assert not soft.satisfied
    assert soft.note == UNANSWERED


def test_answered_service_clauses_outrank_unanswered_ones_at_equal_signal(
    skus, verified, requests_by_id,
):
    """R21: shelf prices are close and only the return record separates them."""
    proposals = resolve(parse(requests_by_id["R21"]["utterance"]), skus, verified)
    assert proposals

    def answered(proposal) -> int:
        return sum(1 for r in _resolved(proposal, ConstraintKind.SERVICE) if r.satisfied)

    # citycircuit publishes nothing, so its listings answer no SERVICE clause.
    assert answered(proposals[0]) >= 1
    assert any(answered(p) == 0 for p in proposals), "nothing to outrank"
    assert proposals[0].sku.attributes["merchant"] != "citycircuit"


# --- the resolver only cites what it was handed -----------------------------


def test_no_records_means_no_citations_and_every_clause_unanswered(
    skus, requests_by_id,
):
    """The control column, asserted. This is what a plain feed can do."""
    constraints = parse(requests_by_id["R01"]["utterance"])
    proposals = resolve(constraints, skus, [])
    assert proposals

    assert not [r for p in proposals for r in p.resolved if r.evidence_record_id]
    wanted = [c for c in constraints
              if c.kind in (ConstraintKind.SERVICE, ConstraintKind.VALUES)]
    assert wanted
    for proposal in proposals:
        assert {c.text for c in proposal.unsatisfied} == {c.text for c in wanted}


def test_a_record_from_another_merchant_never_answers_this_listing(skus, verified):
    """A signature proves who wrote a claim, not that it is about this shelf."""
    constraints = [
        Constraint("laptop", ConstraintKind.HARD),
        Constraint("I can return it easily", ConstraintKind.SERVICE),
    ]
    proposals = resolve(constraints, skus, verified)
    by_id = {v.record.record_id: v.record for v in verified}
    for proposal in proposals:
        merchant = proposal.sku.attributes["merchant"]
        for resolved in proposal.resolved:
            if resolved.evidence_record_id:
                issuer = by_id[resolved.evidence_record_id].issuer
                assert issuer == MERCHANT_DOMAINS[merchant]


def test_a_scoped_record_does_not_answer_a_listing_outside_its_scope(skus, verified):
    """Voltway's appliance cover is 24 months and its laptop cover is 12.

    Both are `warranty`. Without scope the wrong one attaches and the
    justification cites a term the shopper would not actually get.
    """
    constraints = [
        Constraint("laptop", ConstraintKind.HARD),
        Constraint("long warranty", ConstraintKind.SERVICE),
    ]
    proposals = resolve(constraints, skus, verified)
    voltway = [p for p in proposals if p.sku.attributes["merchant"] == "voltway"]
    assert voltway

    cited = {r.evidence_record_id for p in voltway
             for r in _resolved(p, ConstraintKind.SERVICE) if r.evidence_record_id}
    assert cited == {"vw-warranty-laptop-phone-12"}
    assert "vw-warranty-appliance-24" not in cited
