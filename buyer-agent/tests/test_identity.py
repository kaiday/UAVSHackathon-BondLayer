"""What the agent puts on the wire when the shopper has, and has not, said who they are.

The property under test is narrow and worth stating plainly: **withholding
consent is the absence of a field, not the presence of a filter.** A request
with no ``shopper_id`` must carry no id on the query string and must not
declare ``identity_linking``, so no merchant is ever in a position to log an
identity the shopper did not offer.

No live merchant and no network; the HTTP layer is a recording stub.
"""

from __future__ import annotations

import sys
from pathlib import Path

CHAT_APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CHAT_APP))
sys.path.insert(0, str(CHAT_APP.parent.parent / "bondlayer" / "src"))

from src.agent import ucp_client  # noqa: E402


class _RecordingClient:
    """Answers one empty page and keeps what it was asked."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def get(self, url, params=None, headers=None):
        self.calls.append({"url": url, "params": dict(params or {}),
                           "headers": dict(headers or {})})
        return _Response()


class _Response:
    status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "business": {"id": "voltway", "name": "Voltway"},
            "active_capabilities": {},
            "products": [],
            "next_offset": None,
        }


def _fetch_once(shopper_id: str | None) -> dict:
    http = _RecordingClient()
    fetch = ucp_client.make_fetcher(http, shopper_id=shopper_id)
    fetch("voltway", "laptop", extension=True)
    assert len(http.calls) == 1
    return http.calls[0]


def test_an_anonymous_request_carries_no_shopper_id():
    call = _fetch_once(None)
    assert "shopper_id" not in call["params"]


def test_an_anonymous_request_does_not_declare_identity_linking():
    """Declaring the capability while sending nobody would invite an identity
    conversation the shopper did not consent to."""
    call = _fetch_once(None)
    assert ucp_client.IDENTITY_LINKING not in call["headers"]["UCP-Agent"]


def test_an_identified_request_sends_the_id_and_declares_the_capability():
    call = _fetch_once("shopper-001")
    assert call["params"]["shopper_id"] == "shopper-001"
    assert ucp_client.IDENTITY_LINKING in call["headers"]["UCP-Agent"]


def test_the_benefit_extension_is_still_the_only_thing_the_toggle_moves():
    """Identity is orthogonal to the BondLayer switch: an identified request
    with the extension off still declares no benefit extension."""
    http = _RecordingClient()
    fetch = ucp_client.make_fetcher(http, shopper_id="shopper-001")
    fetch("voltway", "laptop", extension=False)
    header = http.calls[0]["headers"]["UCP-Agent"]
    assert ucp_client.BENEFIT_VALUE not in header
    assert ucp_client.IDENTITY_LINKING in header
