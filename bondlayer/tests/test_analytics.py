"""``GET /onboard/analytics`` -- the benchmark, summed from the reports on disk.

These tests recount the same JSON files directly and compare. If the route and
the recount ever disagree, the route invented something.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bondlayer.ucp.analytics import benchmark, loss_reason
from bondlayer.ucp.server import create_app

REPORTS = Path(__file__).resolve().parents[1] / "data" / "eval" / "reports"


def _on_disk() -> dict[str, dict]:
    return {
        r["request_id"]: r
        for r in (json.loads(p.read_text(encoding="utf-8")) for p in sorted(REPORTS.glob("*.json")))
    }


@pytest.fixture(scope="module")
def body():
    return TestClient(create_app()).get("/onboard/analytics").json()


def test_labelled_as_the_thirty_request_benchmark(body):
    assert body["source"] == "benchmark"
    assert body["requests"] == 30
    assert body["eval_commit"]


def test_wins_match_a_direct_recount(body):
    wins: dict[str, int] = {}
    seen: dict[str, int] = {}
    for report in _on_disk().values():
        for row in report["merchants"]:
            wins[row["merchant"]] = wins.get(row["merchant"], 0) + bool(row["won"])
            seen[row["merchant"]] = seen.get(row["merchant"], 0) + 1
    assert {m["merchant"]: m["wins"] for m in body["merchants"]} == wins
    # A merchant only appears in the requests it had a candidate for, so the
    # denominator is its own count, not 30.
    assert {m["merchant"]: m["requests"] for m in body["merchants"]} == seen
    assert all(m["requests"] <= body["requests"] for m in body["merchants"])


def test_value_totals_match_a_direct_recount(body):
    by_merchant = {m["merchant"]: m for m in body["merchants"]}
    for merchant, row in by_merchant.items():
        credited = sum(
            (Decimal(r["value_credited_aud"]) for rep in _on_disk().values()
             for r in rep["merchants"] if r["merchant"] == merchant),
            Decimal("0"),
        )
        assert Decimal(row["value_credited_aud"]) == credited


def test_merchants_are_ordered_by_wins(body):
    wins = [m["wins"] for m in body["merchants"]]
    assert wins == sorted(wins, reverse=True)


def test_loss_reasons_count_every_loss(body):
    losses = sum(
        1 for rep in _on_disk().values() for r in rep["merchants"] if r["lost_because"]
    )
    assert sum(r["count"] for r in body["loss_reasons"]) == losses
    # Grouping drops the amount and the winner, so few distinct causes remain.
    assert len(body["loss_reasons"]) < losses


def test_loss_reason_drops_amount_and_winner():
    a = "Published value the wire did not carry: $330 was withheld as unverified, so voltway won."
    b = "Published value the wire did not carry: $1489.79 was withheld, so northgear won."
    assert loss_reason(a) == loss_reason(b) == "Published value the wire did not carry"
    c = "Published no machine-readable benefit records, so nothing was credited; citycircuit won on effective cost."
    assert loss_reason(c) == "Published no machine-readable benefit records, so nothing was credited"


def test_service_values_answered_sums_the_metrics(body):
    reports = _on_disk().values()
    answered = sum(r["metrics"]["clauses_answered"][0] for r in reports)
    control = sum(r["metrics"]["clauses_answered_control"][0] for r in reports)
    assert body["service_values_answered"]["bondlayer"][0] == answered
    assert body["service_values_answered"]["control"][0] == control
    assert answered > control


def test_same_reports_same_response():
    reports = _on_disk()
    assert benchmark(reports) == benchmark(reports)


def test_empty_reports_do_not_divide_by_zero():
    body = benchmark({})
    assert body["requests"] == 0 and body["merchants"] == []
