"""``/query`` closes the loop: the winning offer becomes an order (WS-L).

Same mocking pattern as ``test_merchant_decode.py``: no live merchant, no
network, no model key. The fetcher, verifier and proposer are the existing
fakes; the checkout is a fake that answers a WS-K-shaped confirmation. One
real-HTTP test drives ``make_checkout`` against the merchant app in-process.
"""

from __future__ import annotations

import sys
from pathlib import Path

CHAT_APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CHAT_APP))
sys.path.insert(0, str(CHAT_APP.parent.parent / "bondlayer" / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from bondlayer.agent.trace import AgentRun  # noqa: E402
from bondlayer.ucp.capabilities import BENEFIT_VALUE, CHECKOUT  # noqa: E402
from bondlayer.ucp.server import create_app  # noqa: E402

from src.agent import llm, main, ucp_client  # noqa: E402
from tests.test_merchant_decode import PRE_EXISTING_KEYS, FakeProposer  # noqa: E402
from tests.test_query import _mock_fetch  # noqa: E402

#: Every key ``/query`` returned before this workstream, WS-J's included.
KEYS_BEFORE = PRE_EXISTING_KEYS | {"merchant_decodes"}


class FakeCheckout:
    def __init__(self):
        self.calls: list[tuple[str, dict, bool]] = []

    def __call__(self, merchant: str, body: dict, *, extension: bool) -> dict | None:
        self.calls.append((merchant, body, extension))
        [item] = body["items"]
        response = {
            "business": {"id": merchant, "name": merchant.title()},
            "active_capabilities": {CHECKOUT: "2026-04-08"},
            "order": {
                "order_id": "84373a30a113655c",
                "status": "confirmed_awaiting_payment",
                "line_items": [{"sku_id": item["sku_id"], "title": "Test Laptop", "quantity": 1,
                                "unit_price": {"amount": "920.00", "currency": "AUD"},
                                "line_total": {"amount": "920.00", "currency": "AUD"}}],
                "subtotal": {"amount": "920.00", "currency": "AUD"},
                "payment": {"status": "out_of_scope", "note": "no funds move"},
                "agent_ref": body.get("agent_ref"),
            },
        }
        if extension:
            response["honoured_benefits"] = [
                {"record_id": rid, "honoured": True, "sku_id": item["sku_id"],
                 "reason": "verified against the merchant's published signing key"}
                for rid in body["cited_record_ids"]
            ]
            response["extensions"] = {BENEFIT_VALUE: []}
        return response


def _patch(monkeypatch, checkout):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(ucp_client, "make_fetcher", lambda *a, **k: _mock_fetch)
    monkeypatch.setattr(ucp_client, "make_verifier", lambda *a, **k: (lambda entry: True))
    monkeypatch.setattr(ucp_client, "make_proposer", lambda *a, **k: FakeProposer())
    monkeypatch.setattr(ucp_client, "make_checkout", lambda *a, **k: checkout)


def test_toggle_on_returns_the_order_with_every_cited_record_honoured(monkeypatch):
    fake = FakeCheckout()
    _patch(monkeypatch, fake)
    body = TestClient(main.app).post("/query", json={
        "query": "a laptop I can return easily", "bondlayer_enabled": True,
    }).json()

    assert KEYS_BEFORE <= set(body)
    assert body["winner"]["merchant"] == "voltway"

    order = body["order"]
    assert order["kind"] == "close_loop"
    assert order["outcome"] == "ok"
    assert order["merchant"] == "voltway"
    assert order["order"]["order_id"] == "84373a30a113655c"
    assert order["order"]["status"] == "confirmed_awaiting_payment"
    assert order["order"]["agent_ref"] == "chat-app"
    assert order["request"]["items"] == [{"sku_id": "VOL-1", "quantity": 1}]
    # The one record the mock publishes verified, was credited and answered the
    # SERVICE clause -- so it is the one record cited, and it is honoured.
    assert order["request"]["cited_record_ids"] == ["r1"]
    assert order["honoured_benefits"] == [{
        "record_id": "r1", "honoured": True, "sku_id": "VOL-1",
        "reason": "verified against the merchant's published signing key",
    }]
    assert order["extensions_present"] is True
    assert order["summary_counts"] == {"cited": 1, "honoured": 1}
    assert order["summary"].startswith("Checked out VOL-1 at voltway: order 84373a30a113655c confirmed")

    # One call, to the winner, with the toggle state.
    assert fake.calls == [("voltway", order["request"], True)]
    # And it is in the trace as an ordinary step, findable by its detail kind.
    steps = [s for s in body["steps"] if s["detail"].get("kind") == "close_loop"]
    assert len(steps) == 1 and steps[0]["phase"] == "ranking" and steps[0]["outcome"] == "ok"


def test_toggle_off_returns_a_plain_order_with_no_verdicts(monkeypatch):
    fake = FakeCheckout()
    _patch(monkeypatch, fake)
    body = TestClient(main.app).post("/query", json={
        "query": "a laptop I can return easily", "bondlayer_enabled": False,
    }).json()

    assert KEYS_BEFORE <= set(body)
    order = body["order"]
    assert order["kind"] == "close_loop"
    assert order["outcome"] == "ok"
    assert order["order"]["order_id"]
    assert order["honoured_benefits"] is None
    assert order["extensions_present"] is False
    assert order["request"]["cited_record_ids"] == []
    assert order["merchant"] == body["winner"]["merchant"] != "voltway"
    assert order["summary"].endswith("no benefit records were cited, so the order binds none.")
    [(merchant, _, extension)] = fake.calls
    assert merchant == body["winner"]["merchant"] and extension is False


def test_an_unreachable_merchant_at_checkout_is_a_degraded_step_not_a_500(monkeypatch):
    import httpx

    def down(merchant, body, *, extension):
        raise httpx.ConnectError("connection refused")

    _patch(monkeypatch, down)
    response = TestClient(main.app).post("/query", json={
        "query": "a laptop I can return easily", "bondlayer_enabled": True,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["ranked"] and body["winner"]["merchant"] == "voltway", "the ranking survives"
    assert body["order"]["kind"] == "close_loop"
    assert body["order"]["outcome"] == "degraded"
    assert body["order"]["order"] is None
    assert body["order"]["error"].startswith("ConnectError")
    assert "the loop stays open" in body["order"]["summary"]


def test_make_checkout_against_the_real_merchant_app_in_process():
    """Real route, real negotiation: ``checkout`` is declared in both toggle
    states, the verdicts only ride the extension, and the control merchant
    answers a plain order on the same route."""
    client = TestClient(create_app())
    checkout = ucp_client.make_checkout(client)
    body = {"items": [{"sku_id": "VOL-0031", "quantity": 1}],
            "cited_record_ids": ["vw-returns-60", "vw-repairability-parts-5y"],
            "agent_ref": "test"}

    rich = checkout("voltway", body, extension=True)
    assert rich is not None
    assert CHECKOUT in rich["active_capabilities"] and BENEFIT_VALUE in rich["active_capabilities"]
    assert rich["order"]["status"] == "confirmed_awaiting_payment"
    assert [v["honoured"] for v in rich["honoured_benefits"]] == [True, True]
    assert len(rich["extensions"][BENEFIT_VALUE]) == 2

    plain = checkout("voltway", body, extension=False)
    assert plain is not None
    assert CHECKOUT in plain["active_capabilities"] and BENEFIT_VALUE not in plain["active_capabilities"]
    assert "honoured_benefits" not in plain and "extensions" not in plain
    # The order id binds the honoured set either way: same body, same id.
    assert plain["order"]["order_id"] == rich["order"]["order_id"]

    control = checkout("citycircuit", {"items": [{"sku_id": "CIT-0032", "quantity": 1}],
                                       "cited_record_ids": []}, extension=False)
    assert control is not None and "honoured_benefits" not in control
    assert control["order"]["subtotal"]["amount"] == "1066.00"


def test_the_header_still_declares_exactly_what_it_did_and_checkout_rides_the_route():
    # ``agent_header`` is byte for byte what WS-J pinned; checkout is appended
    # only on the one route that needs it.
    assert ucp_client.agent_header(False).split(";") == [ucp_client.CATALOG_SEARCH, ucp_client.CATALOG_LOOKUP]
    assert CHECKOUT not in ucp_client.agent_header(True)


def test_a_provider_error_never_reaches_the_screen(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")

    def boom(prompt: str) -> str:
        raise RuntimeError("secret provider text")

    monkeypatch.setattr(llm, "_complete", boom)
    run = AgentRun(utterance="a laptop", extension_enabled=True, steps=[], ranked=[])
    out = llm.narrate(run)
    assert out["source"] == "template"
    assert "RuntimeError" in out["note"]
    assert "secret provider text" not in out["note"]
    assert out["text"], "the template sentence still comes back"


def test_the_page_renders_the_receipt_and_never_derives_it():
    page = (CHAT_APP / "src" / "agent" / "static" / "index.html").read_text(encoding="utf-8")
    assert "closeLoopHtml(d.order" in page
    assert "Closing the loop" in page
    assert "confirmed — awaiting payment; payment is out of scope for this prototype, no funds move" in page
    assert "Plain UCP order: no benefit records were cited, so the order binds none." in page
    # The tick and cross come from the merchant's verdicts, never decided here.
    assert "v.honoured" in page
