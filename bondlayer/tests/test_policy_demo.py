from pathlib import Path

import pytest

from bondlayer.policy import DraftStatus, PolicyError
from bondlayer.policy_demo import DemoPolicyConverter


POLICY = Path(__file__).parents[1] / "data" / "policies" / "jb-hihi-demo-policy.txt"


def test_demo_policy_is_grounded_and_unpublished():
    document = POLICY.read_text(encoding="utf-8")
    drafts = DemoPolicyConverter("demo", "JB Hihi", POLICY).drafts_for("demo", document)
    assert len(drafts) == 6
    assert all(d.status == DraftStatus.PENDING and d.signed is None for d in drafts)
    assert all(d.record.source_span in document for d in drafts)
    assert all(d.record.source_span in d.record.conditions for d in drafts)
    assert all(d.record.value_ceiling_aud is None for d in drafts)
    assert drafts[3].record.fact == {"assessment_years": 3}


def test_modified_or_other_merchant_policy_is_rejected():
    document = POLICY.read_text(encoding="utf-8")
    with pytest.raises(PolicyError):
        DemoPolicyConverter("demo", "JB Hihi", POLICY).drafts_for("demo", document + " altered")
    with pytest.raises(PolicyError):
        DemoPolicyConverter("other", "North Gear", POLICY).drafts_for("other", document)
