"""The dashboard's "why we lost" console -- WS-E.

`GET /onboard/requests` and `GET /onboard/requests/{id}` only serve what
WS-A's eval runner already wrote to `data/eval/reports/`. These tests check
that the routes are a faithful projection, not a second computation of the
same numbers.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bondlayer.ucp.server import create_app

REPORTS = Path(__file__).resolve().parents[1] / "data" / "eval" / "reports"

FOUR_FIGURES = (
    "fields_exposed",
    "legible_share",
    "value_credited_aud",
    "value_withheld_aud",
)


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app())


def test_requests_list_returns_all_thirty(client):
    body = client.get("/onboard/requests").json()
    assert len(body) == 30
    assert {"request_id", "utterance", "merchants"} <= set(body[0])
    # The summary row is enough to pick a request: id, utterance, and a
    # won/lost line per merchant -- not the four figures themselves.
    assert {"merchant", "control_merchant", "won"} <= set(body[0]["merchants"][0])


def test_known_request_matches_the_json_on_disk(client):
    on_disk = json.loads((REPORTS / "R01.json").read_text(encoding="utf-8"))
    body = client.get("/onboard/requests/R01").json()

    assert body["request_id"] == "R01"
    assert body["utterance"] == on_disk["utterance"]
    assert len(body["merchants"]) == len(on_disk["merchants"]) == 3

    by_merchant = {m["merchant"]: m for m in body["merchants"]}
    for disk_row in on_disk["merchants"]:
        api_row = by_merchant[disk_row["merchant"]]
        for figure in FOUR_FIGURES:
            assert api_row[figure] == disk_row[figure], figure
        assert api_row["won"] == disk_row["won"]
        assert api_row["lost_because"] == disk_row["lost_because"]


def test_voltway_wins_r01_with_a_null_lost_because(client):
    body = client.get("/onboard/requests/R01").json()
    voltway = next(m for m in body["merchants"] if m["merchant"] == "voltway")
    assert voltway["won"] is True
    assert voltway["lost_because"] is None


def test_control_merchant_row_is_present_and_marked(client):
    body = client.get("/onboard/requests/R01").json()
    controls = [m for m in body["merchants"] if m["control_merchant"]]
    assert len(controls) == 1
    assert controls[0]["merchant"] == "citycircuit"
    assert controls[0]["won"] is False
    assert controls[0]["lost_because"]


def test_merchant_query_param_returns_just_that_row(client):
    body = client.get(
        "/onboard/requests/R01", params={"merchant": "northgear"}
    ).json()
    assert body["merchant"] == "northgear"
    assert body["request_id"] == "R01"
    assert "merchants" not in body
    for figure in FOUR_FIGURES:
        assert figure in body


def test_unknown_request_404s(client):
    resp = client.get("/onboard/requests/R999")
    assert resp.status_code == 404


def test_unknown_merchant_on_a_known_request_404s(client):
    resp = client.get("/onboard/requests/R01", params={"merchant": "nope"})
    assert resp.status_code == 404


def test_every_frozen_request_is_listed(client):
    ids = {r["request_id"] for r in client.get("/onboard/requests").json()}
    on_disk_ids = {p.stem for p in REPORTS.glob("*.json")}
    assert ids == on_disk_ids
