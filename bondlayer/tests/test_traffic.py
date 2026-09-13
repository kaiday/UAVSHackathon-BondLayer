"""The live traffic log: counts what the merchant already receives, and nothing else."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bondlayer.ucp import traffic
from bondlayer.ucp.server import create_app
from bondlayer.ucp.traffic import TrafficLog, classify, declared_capabilities

PLAIN = "dev.ucp.shopping.catalog.search;dev.ucp.shopping.catalog.lookup"
FULL = (
    "dev.ucp.shopping.catalog.search;dev.ucp.shopping.catalog.lookup;"
    "dev.ucp.shopping.checkout;org.bondlayer.benefit_value;org.bondlayer.intent_match"
)
SECRET_UTTERANCE = "a laptop under $1,500 for my zebra-sanctuary accounting"
SECRET_QUERY = "quokkasecret"


class Clock:
    def __init__(self, t: float = 1_800_000_000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app())


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def log(tmp_path, clock, monkeypatch):
    fresh = TrafficLog(tmp_path / "traffic" / "events.jsonl", clock=clock)
    monkeypatch.setattr(traffic, "LOG", fresh)
    return fresh


def test_classify_names_only_the_ucp_surface():
    assert classify("/voltway/.well-known/ucp") == ("voltway", "profile")
    assert classify("/voltway/ucp/catalog/search") == ("voltway", "search")
    assert classify("/northgear/ucp/catalog/lookup") == ("northgear", "lookup")
    assert classify("/voltway/ucp/intent/propose") == ("voltway", "intent")
    assert classify("/citycircuit/ucp/checkout") == ("citycircuit", "checkout")
    for path in ("/onboard/merchants", "/onboard/traffic", "/console/", "/dashboard/", "/docs"):
        assert classify(path) is None


def test_declared_capabilities_read_like_negotiation():
    assert declared_capabilities(None) == ()
    assert declared_capabilities(PLAIN) == ()
    assert declared_capabilities(FULL) == ("benefit_value", "checkout", "intent_match")


def test_search_is_counted_with_what_the_agent_declared(client, log):
    client.get("/voltway/ucp/catalog/search?category=laptop", headers={"UCP-Agent": PLAIN})
    client.get("/voltway/ucp/catalog/search?category=laptop", headers={"UCP-Agent": FULL})
    calls = [e for e in log.events() if e.kind == "call"]
    assert [(e.merchant, e.route, e.status) for e in calls] == [("voltway", "search", 200)] * 2
    assert calls[0].declared == ()
    assert "benefit_value" in calls[1].declared

    totals = client.get("/onboard/traffic").json()["totals"]
    assert totals["calls"] == 2
    assert totals["declared_benefit_value"] == 1
    assert totals["benefit_value_share"] == 0.5


def test_a_refused_call_is_counted_as_406(client, log):
    # The control never negotiates intent_match.
    r = client.post("/citycircuit/ucp/intent/propose", headers={"UCP-Agent": FULL},
                    json={"utterance": "a laptop", "limit": 1})
    assert r.status_code == 406
    body = client.get("/onboard/traffic?merchant=citycircuit").json()
    assert body["totals"]["refused_406"] == 1
    assert body["totals"]["by_route"]["intent"] == 1


def test_checkout_records_an_order_with_honoured_counts(client, log):
    r = client.post("/voltway/ucp/checkout", headers={"UCP-Agent": FULL}, json={
        "items": [{"sku_id": "VOL-0031", "quantity": 1}],
        "cited_record_ids": ["vw-returns-60", "vw-repairability-parts-5y", "made-up-id"],
    })
    assert r.status_code == 200
    orders = [e for e in log.events() if e.kind == "order"]
    assert len(orders) == 1
    assert orders[0].order_id == r.json()["order"]["order_id"]
    assert (orders[0].honoured, orders[0].cited) == (2, 3)
    assert client.get("/onboard/traffic").json()["orders"] == {"count": 1, "honoured": 2, "cited": 3}


def test_the_log_never_holds_the_utterance_or_the_query(client, log):
    client.post("/voltway/ucp/intent/propose", headers={"UCP-Agent": FULL},
                json={"utterance": SECRET_UTTERANCE, "limit": 1})
    client.get(f"/voltway/ucp/catalog/search?q={SECRET_QUERY}", headers={"UCP-Agent": FULL})
    on_disk = log.path.read_text(encoding="utf-8")
    served = client.get("/onboard/traffic").text
    for secret in ("zebra-sanctuary", SECRET_QUERY, "1,500"):
        assert secret not in on_disk
        assert secret not in served
    assert len(log.events()) == 2


def test_the_merchant_s_own_screens_are_not_traffic(client, log):
    client.get("/onboard/merchants")
    client.get("/onboard/analytics")
    client.get("/onboard/traffic")
    client.get("/dashboard/")
    assert log.events() == []


def test_series_buckets_by_minute_and_filters_by_merchant(log, clock):
    log.call("voltway", "search", 200, FULL)
    clock.t += 61
    log.call("voltway", "lookup", 200, FULL)
    log.call("northgear", "search", 200, PLAIN)

    body = log.summary(bucket="minute", window=5)
    assert len(body["series"]) == 5
    assert [p["total"] for p in body["series"]][-2:] == [1, 2]
    assert body["series"][-1]["lookup"] == 1

    voltway = log.summary(merchant="voltway", window=5)
    assert voltway["totals"]["calls"] == 2
    assert {r["merchant"]: r["calls"] for r in voltway["by_merchant"]} == {"voltway": 2, "northgear": 1}


def test_calls_outside_the_window_leave_the_series_but_stay_in_totals(log, clock):
    log.call("voltway", "search", 200, FULL)
    clock.t += 3600
    body = log.summary(bucket="minute", window=10)
    assert sum(p["total"] for p in body["series"]) == 0
    assert body["totals"]["calls"] == 1


def test_persisted_events_survive_a_restart(log, clock):
    log.call("voltway", "search", 200, FULL)
    log.order("voltway", "abc123", honoured=6, cited=6)
    reloaded = TrafficLog(log.path, clock=clock)
    assert reloaded.events() == log.events()


def test_a_torn_line_does_not_lose_the_rest(log, clock):
    log.call("voltway", "search", 200, FULL)
    with log.path.open("a", encoding="utf-8") as out:
        out.write('{"ts": 1, "kind": "ca')
    assert len(TrafficLog(log.path, clock=clock).events()) == 1


def test_reset_clears_memory_and_file(client, log):
    log.call("voltway", "search", 200, FULL)
    assert client.delete("/onboard/traffic").json() == {"reset": True}
    assert log.events() == []
    assert not log.path.exists()


def test_empty_log_summarises_without_dividing_by_zero(log):
    body = log.summary()
    assert body["totals"]["calls"] == 0
    assert body["totals"]["benefit_value_share"] is None
    assert body["first_event"] is None


def test_bad_bucket_is_rejected(client, log):
    assert client.get("/onboard/traffic?bucket=week").status_code == 422


def test_the_server_log_does_not_persist_unless_run_server_asks():
    # Importing the app (as every test does) must never write into the demo's traffic.
    assert traffic.TrafficLog().path is None
