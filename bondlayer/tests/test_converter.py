from __future__ import annotations

import json
from pathlib import Path

import pytest

from bondlayer.policy import CachedPolicyConverter, DraftStatus, PolicyError, PolicyOnboardingService, PolicyStore
from bondlayer.types import BenefitRecord, SignedRecord


DATA = Path(__file__).parents[1] / "data"
FIXTURES = DATA / "policy_fixtures" / "drafts.json"


class RecordingSigner:
    def __init__(self) -> None:
        self.signed: list[BenefitRecord] = []

    def sign(self, record: BenefitRecord) -> SignedRecord:
        self.signed.append(record)
        return SignedRecord(record=record, signature="fixture-signature", key_id="fixture-key")

    def verify(self, signed: SignedRecord) -> bool:
        return signed.signature == "fixture-signature"


@pytest.fixture
def service(tmp_path: Path) -> tuple[PolicyOnboardingService, RecordingSigner]:
    signer = RecordingSigner()
    return PolicyOnboardingService(PolicyStore(tmp_path), CachedPolicyConverter(FIXTURES), signer), signer


def policy(name: str) -> str:
    return (DATA / "policies" / name).read_text(encoding="utf-8")


def test_voltway_drafts_manifest_records_with_verbatim_evidence(service) -> None:
    onboarding, _ = service
    report = onboarding.ingest_and_draft("voltway", "voltway.md", policy("voltway.md"))
    drafts = onboarding.store.drafts_for("voltway")

    assert report.records_drafted >= 9
    assert len(drafts) == 12
    assert all(draft.record.source_span in policy("voltway.md") for draft in drafts)
    assert all(draft.record.value_ceiling_aud is None for draft in drafts if not draft.record.is_priced)


def test_northgear_environmental_adjectives_produce_no_approvable_draft(service) -> None:
    onboarding, _ = service
    report = onboarding.ingest_and_draft("northgear", "northgear.md", policy("northgear.md"))
    drafts = onboarding.store.drafts_for("northgear")

    assert "Our environmental commitment" in report.sections_without_drafts
    assert not {"sustainability", "ethical_sourcing"} & {draft.record.benefit_type.value for draft in drafts}
    assert report.records_drafted == 5


def test_rejected_draft_is_never_signed_or_published(service) -> None:
    onboarding, signer = service
    onboarding.ingest_and_draft("voltway", "voltway.md", policy("voltway.md"))

    rejected = onboarding.reject("voltway-returns-60", "Customer service exception")

    assert rejected.status is DraftStatus.REJECTED
    assert signer.signed == []
    assert onboarding.publish("voltway") == []


def test_approval_is_persisted_and_handed_to_injected_signer(service) -> None:
    onboarding, signer = service
    onboarding.ingest_and_draft("voltway", "voltway.md", policy("voltway.md"))

    approved = onboarding.approve("voltway-returns-60")
    reloaded = onboarding.store.get_draft("voltway-returns-60")

    assert approved.signed is not None
    assert signer.signed == [approved.record]
    assert reloaded.status is DraftStatus.APPROVED
    assert onboarding.publish("voltway") == [approved.signed]


def test_cached_drafts_match_manifest_and_report_pitch_metrics(service) -> None:
    onboarding, _ = service
    onboarding.ingest_and_draft("voltway", "voltway.md", policy("voltway.md"))
    manifest = json.loads((DATA / "policies" / "manifests.json").read_text(encoding="utf-8"))
    expected = manifest["merchants"]["voltway"]["expect_records"]

    for draft in onboarding.store.drafts_for("voltway"):
        onboarding.approve(draft.draft_id)
    metrics = onboarding.metrics("voltway", expected)

    assert metrics.extraction_precision == 1.0
    assert metrics.drafts_approved_unedited_share == 1.0


def test_ingest_stores_raw_text_and_rejects_unknown_extensions(service) -> None:
    onboarding, _ = service
    report = onboarding.ingest_and_draft("voltway", "terms.txt", policy("voltway.md"))
    document = onboarding.store.get_document("voltway")

    assert report.records_drafted == 12
    assert document.raw_path.read_text(encoding="utf-8") == policy("voltway.md")
    with pytest.raises(PolicyError, match=".md, .txt, or .pdf"):
        onboarding.ingestor.ingest("voltway", "terms.docx", b"not supported")
