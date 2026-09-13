"""Merchant-facing metrics must describe evidence, never invented sales or causes."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json

import pytest
from fastapi.testclient import TestClient

from bondlayer import activity
from bondlayer.agent.trace import AgentRun, Ranked
from bondlayer.insights import build_insights, capture_observation
from bondlayer.types import Constraint, ConstraintKind, ResolvedConstraint
from bondlayer.ucp import server

NOW = datetime(2026, 9, 13, 12, tzinfo=timezone.utc)


def report(rid, *, merchant="store", age=1, enabled=True, offer=True, selected=None, unanswered=None):
    row = {"merchant": merchant, "sku_id": "SKU-1" if offer else None,
           "shelf_price": "499.00" if offer else None, "won": selected,
           "unsatisfied": unanswered or []}
    return {"request_id": rid, "source": "live", "created_at": (NOW - timedelta(days=age)).isoformat(),
            "extension_enabled": enabled, "utterance": "A laptop under $1,500 with easy returns",
            "constraints": [{"kind": "hard", "text": "laptop under $1,500"},
                            {"kind": "service", "text": "easy returns"}], "merchants": [row], "order": {}}


def test_counts_are_scoped_to_merchant_period_and_comparison_mode():
    matching = report("one", selected=True, unanswered=["easy returns"])
    matching["order"] = {"merchant": "store", "order": {"status": "confirmed_awaiting_payment", "order_id": "same-content-hash", "payment": {"status": "out_of_scope"}}}
    second = report("two", offer=False)
    sources = {"one": matching, "duplicate": matching, "two": second,
               "baseline": report("baseline", enabled=False), "old": report("old", age=31),
               "other": report("other", merchant="another-business"),
               "fixture": {**report("fixture"), "source": "benchmark"},
               "undated": {**report("undated"), "created_at": None},
               "future": report("future", age=-1)}
    result = build_insights(sources, "store", now=NOW)
    assert result["metrics"] == {"requests": 2, "with_offers": 1, "unanswered": 1,
                                 "checkout_confirmations": 1, "selected": 1,
                                 "selection_known": 1, "detailed_reports": 0}
    assert result["coverage"]["excluded_undated_or_future"] == 2
    assert {r["request_id"] for r in result["recent"]} == {"one", "two"}
    assert "another-business" not in json.dumps(result)
    assert build_insights(sources, "store", now=NOW, mode="control")["metrics"]["requests"] == 1
    assert build_insights(sources, "store", now=NOW, days=0, mode="all")["metrics"]["requests"] == 4


def test_missing_outcome_never_becomes_lost_or_a_paid_sale():
    one = report("one", selected=False)
    result = build_insights({"one": one}, "store", now=NOW)
    assert result["recent"][0]["outcome"] == "Outcome unknown"
    assert result["metrics"]["selection_known"] == 0
    one["merchants"].append({"merchant": "other", "won": True})
    one["order"] = {"merchant": "other", "order": {"status": "confirmed_awaiting_payment", "subtotal": {"amount": "1234.56"}}}
    result = build_insights({"one": one}, "store", now=NOW)
    assert result["recent"][0]["outcome"] == "Another offer selected by agent"
    assert result["metrics"]["checkout_confirmations"] == 0
    assert "1234.56" not in json.dumps(result)
    assert "lost_revenue" not in result["metrics"]


def test_demand_counts_requests_once_and_cites_the_source():
    one = report("one")
    one["constraints"].append({"kind": "service", "text": "painless returns"})
    result = build_insights({"one": one}, "store", now=NOW)
    assert result["demand"]["categories"] == [{"label": "Laptop", "requests": 1, "request_ids": ["one"]}]
    assert result["demand"]["needs"] == [{"label": "Returns", "requests": 1, "request_ids": ["one"]}]
    assert result["demand"]["budgets"][0]["label"] == "Budget ceiling: $1,500.00 AUD"


def make_offer(citations=None, resolved=None, unsatisfied=None):
    return Ranked("store", "SKU-1", "Work laptop", Decimal("499"), Decimal("0"), Decimal("499"),
                  1, 1, 0, citations=citations or [], resolved=resolved or [], unsatisfied=unsatisfied or [])


def test_saved_evidence_distinguishes_missing_data_from_eligibility():
    c = Constraint("easy returns", ConstraintKind.SERVICE)
    offer = make_offer(
        citations=[{"record_id": "returns", "benefit_type": "free_returns", "cited": True, "credited": "0",
                    "why": "Verified and citable, but conditions not attested (member); value withheld; credited $0"}],
        resolved=[ResolvedConstraint(c, True, evidence_record_id="returns", evidence_attribute=None, note="Published returns apply")])
    run = AgentRun("a lightweight laptop", True, [], [offer],
                   constraints=[{"text": "under 1.3kg", "kind": "hard"}, {"text": "easy returns", "kind": "service"}])
    snapshot = {"products": [{"id": "SKU-1", "attributes": {}}]}
    observation = capture_observation(run, "store", snapshot, {})
    assert {g["kind"] for g in observation["gaps"]} == {"missing_data", "eligibility_unknown"}
    assert observation["benefits"][0]["state"] == "eligibility_unknown"
    assert observation["product"]["title"] == "Work laptop"
    assert observation["checkout"]["status"] == "unknown"


def test_no_offer_does_not_invent_missing_inventory_or_membership_failure():
    run = AgentRun("laptop", True, [], [], constraints=[{"text": "laptop", "kind": "hard"}])
    observation = capture_observation(run, "store", {"products": []}, {})
    assert [g["kind"] for g in observation["gaps"]] == ["no_offer"]
    assert observation["selected"] is None
    assert observation["benefits"] == []


def test_baseline_run_does_not_suggest_unpublished_policies_without_evidence():
    c = Constraint("easy returns", ConstraintKind.SERVICE)
    run = AgentRun("laptop with returns", False, [], [make_offer(unsatisfied=[c])],
                   constraints=[{"text": c.text, "kind": c.kind.value}])
    observation = capture_observation(run, "store", {"products": []}, {})
    assert observation["gaps"] == []


def test_repeated_benefits_and_gaps_count_distinct_requests():
    one = report("one")
    gap = {"key": "attribute:weight_kg", "kind": "missing_data", "title": "Add product weight",
           "reason": "Weight was absent", "action": "Review product data", "href": "/catalogue/"}
    benefit = {"label": "Returns", "state": "unpriced", "record_id": "r1", "reason": "No monetary ceiling"}
    one["merchants"][0]["observation"] = {"version": 1, "gaps": [gap, gap], "benefits": [benefit, benefit]}
    result = build_insights({"one": one}, "store", now=NOW)
    assert result["opportunities"][0]["requests"] == 1
    assert result["opportunities"][0]["request_ids"] == ["one"]
    assert result["benefits"][0]["requests"] == 1


def test_empty_state_and_legacy_reports_do_not_invent_causes():
    assert build_insights({}, "store", now=NOW)["opportunities"] == []
    one = report("one", unanswered=["easy returns"])
    result = build_insights({"one": one}, "store", now=NOW)
    assert result["opportunities"][0]["kind"] == "unknown"
    assert result["recent"][0]["benefits"] == []


def test_expired_and_unverified_benefits_remain_distinct():
    citations = [{"record_id": rid, "benefit_type": "warranty", "cited": False,
                  "credited": "0", "why": "Unverified record; credited $0"} for rid in ("expired", "bad-signature")]
    run = AgentRun("laptop", True, [], [make_offer(citations=citations)])
    snapshot = {"extensions": {"org.bondlayer.benefit_value": [{"records": [
        {"record": {"record_id": "expired", "expires_at": "2000-01-01T00:00:00Z"}},
        {"record": {"record_id": "bad-signature", "expires_at": None}},
    ]}]}}
    observed = capture_observation(run, "store", snapshot, {})
    assert [b["state"] for b in observed["benefits"]] == ["expired", "unverified"]


def test_merchant_filter_runs_before_report_retention(tmp_path, monkeypatch):
    monkeypatch.setattr(activity, "UPLOADS", tmp_path)
    directory = tmp_path / "requests"
    directory.mkdir()
    (directory / "live-own.json").write_text(json.dumps(report("own")), encoding="utf-8")
    for i in range(501):
        (directory / f"live-other-{i}.json").write_text(json.dumps(report(f"other-{i}", merchant="other")), encoding="utf-8")
    assert list(activity.reports(merchant="store")) == ["own"]
    assert len(activity.reports()) == 500


@pytest.fixture
def client(tmp_path, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setenv("BONDLAYER_TEST_DATA", "0")
        patch.setenv("BONDLAYER_AI_MODE", "rules")
        patch.setattr(server, "UPLOADS", tmp_path)
        patch.setattr(activity, "UPLOADS", tmp_path)
        with TestClient(server.create_app()) as client:
            assert client.post("/onboard/catalog?merchant=store", files={"file": ("products.csv", "sku,title,category,price\nSKU-1,Work laptop,laptop,499\n")}).status_code == 200
            yield client
    server.create_app()


def test_route_uses_saved_runs_and_validates_filters(client):
    run = AgentRun("laptop", True, [], [make_offer()], constraints=[{"text": "laptop", "kind": "hard"}])
    rid = activity.save_request(run, ["store"], {"store": {"products": []}}, {}, {})
    response = client.get("/onboard/insights/store?days=7&mode=enabled")
    assert response.status_code == 200, response.text
    assert response.json()["metrics"]["requests"] == 1
    assert response.json()["recent"][0]["request_id"] == rid
    assert client.get("/onboard/insights/no-such-store").status_code == 404
    assert client.get("/onboard/insights/store?days=8").status_code == 422
    assert client.get("/onboard/insights/store?mode=fake").status_code == 422
