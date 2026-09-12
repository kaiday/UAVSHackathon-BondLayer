"""Resolution regressions: typed filtering, semantic ranking and honest gaps."""

from decimal import Decimal

from bondlayer.interpreter import parse, resolve
from bondlayer.types import BenefitRecord, BenefitType, Constraint, ConstraintKind, SignedRecord, Sku


def _sku(sku_id: str, *, merchant: str = "voltway", gtin: str | None = None, **attributes) -> Sku:
    data = {"merchant": merchant, **attributes}
    if gtin:
        data["gtin"] = gtin
    return Sku(sku_id, attributes.pop("title", "Legion 5"), attributes.pop("category", "laptop"),
               Decimal(str(attributes.pop("price", 2500))), data)


def test_r25_applies_every_typed_hard_filter_and_keeps_three_merchants():
    constraints = parse("Gaming laptop, 32GB, RTX, under $3,000")
    eligible = [
        _sku("CIT-0035", merchant="citycircuit", gtin="same", ram_gb=32, gpu="RTX4060", gpu_source="title"),
        _sku("NOR-0036", merchant="northgear", gtin="same", ram_gb=32, gpu="RTX4060", gpu_source="title"),
        _sku("VOL-0034", merchant="voltway", gtin="same", ram_gb=32, gpu="RTX4060", gpu_source="title"),
    ]
    rejected = [
        _sku("too-little-ram", ram_gb=16, gpu="RTX4060", gpu_source="title"),
        _sku("no-gpu", ram_gb=32),
        _sku("too-expensive", ram_gb=32, gpu="RTX4060", gpu_source="title", price=3001),
    ]

    proposals = resolve(constraints, eligible + rejected, [])

    assert {proposal.sku.sku_id for proposal in proposals} == {"CIT-0035", "NOR-0036", "VOL-0034"}
    assert all(all(item.satisfied for item in proposal.resolved if item.constraint.kind is ConstraintKind.HARD)
               for proposal in proposals)


def test_r01_combined_laptop_budget_constraint_filters_both_predicates():
    constraints = parse(
        "A laptop under $1,500 I can return easily if it turns out not to suit my work, "
        "from a brand that actually repairs things"
    )
    proposals = resolve(constraints, [
        _sku("within", price=1499),
        _sku("over-budget", price=1501),
        _sku("not-laptop", category="phone", price=100),
    ], [])

    assert [proposal.sku.sku_id for proposal in proposals] == ["within"]
    hard = next(item for item in proposals[0].resolved if item.constraint.kind is ConstraintKind.HARD)
    assert hard.evidence_attribute == "category,shelf_price"


def test_same_merchant_gtin_duplicates_collapse_but_cross_merchant_offers_do_not():
    constraints = [Constraint("laptop", ConstraintKind.HARD)]
    proposals = resolve(constraints, [
        _sku("VOL-one", merchant="voltway", gtin="9312"),
        _sku("VOL-two", merchant="voltway", gtin="9312", price=2450),
        _sku("CIT-one", merchant="citycircuit", gtin="9312", price=2400),
    ], [])

    assert {proposal.sku.sku_id for proposal in proposals} == {"VOL-two", "CIT-one"}


def test_unverified_nonempty_signature_is_not_cited_and_unsatisfied_is_explicit():
    sku = _sku("VOL-1", merchant="voltway")
    record = BenefitRecord(
        "repair-1", None, BenefitType.REPAIRABILITY, {"parts_years": 5}, [],
        "voltway.example", __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        None, None,
    )
    signed = SignedRecord(record, signature="looks-signed-but-is-not-verified", key_id="k1")
    constraints = [Constraint("hate throwing things away", ConstraintKind.VALUES)]

    proposal = resolve(constraints, [sku], [signed])[0]

    assert proposal.records == []
    assert proposal.unsatisfied == constraints
    assert proposal.resolved[0].evidence_record_id is None
    assert proposal.resolved[0].note == "← no catalogue attribute answers this"


def test_unsatisfiable_values_clause_is_returned_with_the_partial_catalogue_answer():
    constraints = [
        Constraint("phone", ConstraintKind.HARD),
        Constraint("carbon neutral", ConstraintKind.VALUES),
    ]
    proposal = resolve(constraints, [_sku("phone", category="phone")], [])[0]

    assert proposal.sku.sku_id == "phone"
    assert proposal.unsatisfied == [constraints[1]]
    assert proposal.resolved[0].evidence_attribute == "category"


def test_zero_overlap_design_phrase_uses_feature_ontology_not_title_tokens():
    constraints = [Constraint("for design work", ConstraintKind.SOFT)]
    suitable = _sku("design", title="Unrelated model", ram_gb=16, cpu="i7-1360P", screen_in=14.0)
    weak = _sku("weak", title="Unrelated model", ram_gb=8, cpu="i5", screen_in=13.0, price=1)

    proposals = resolve(constraints, [weak, suitable], [])

    assert proposals[0].sku.sku_id == "design"
    assert proposals[0].resolved[0].satisfied
    assert proposals[0].resolved[0].evidence_attribute == "ram_gb,cpu,screen_in"


def test_vague_gift_is_a_ranked_assumption_not_a_failure():
    proposal = resolve(parse("Anything under $100 that would make a good gift"), [
        _sku("gift", category="accessory", price=99),
    ], [])[0]

    gift = next(item for item in proposal.resolved if item.constraint.kind is ConstraintKind.SOFT)
    assert gift.satisfied
    assert "Assumption:" in gift.note
