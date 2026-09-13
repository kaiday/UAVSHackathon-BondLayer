"""Who the merchant says the shopper is, and what that is allowed to change.

Ported from ``round2/tests/test_promotions.py`` on the
``feat/bach-personalized-offers`` branch, which was written against the
chat-app's own in-process merchant. That merchant, its data and its valuation
package were deleted by WS-B; these are the same properties, asserted against
the real ``bondlayer`` server and the real ``DeterministicValuation``.

Three properties, and the port exists for them rather than for the code:

1. The merchant is the authority on membership -- an agent cannot assert its
   way into a tier.
2. Consent is structural -- a scoped record is not *selected* without a linked
   shopper, rather than selected and then filtered.
3. Membership is per-merchant -- one shopper, two merchants, two answers.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from bondlayer.ucp.capabilities import (
    BENEFIT_VALUE,
    CATALOG_LOOKUP,
    CATALOG_SEARCH,
    IDENTITY_LINKING,
)
from bondlayer.ucp.membership import NOT_LINKED, load_rosters, resolve_shopper
from bondlayer.ucp.records import for_sku
from bondlayer.ucp.server import create_app
from bondlayer.valuation.reference_policy import (
    ATTESTED_CONDITIONS,
    SHOPPER_INDEPENDENT,
    attested_conditions,
)

#: A member at Voltway (free Circle programme), unknown at NorthGear.
CIRCLE = "shopper-001"
#: A paid NorthGear Plus member, and only a prospect at Voltway.
PLUS = "shopper-002"

IDENTIFIED = json.dumps({"capabilities": {
    CATALOG_SEARCH: ["2026-04-08"],
    CATALOG_LOOKUP: ["2026-04-08"],
    IDENTITY_LINKING: ["2026-04-08"],
    BENEFIT_VALUE: ["draft"],
}})
ANONYMOUS = json.dumps({"capabilities": {
    CATALOG_SEARCH: ["2026-04-08"],
    CATALOG_LOOKUP: ["2026-04-08"],
    BENEFIT_VALUE: ["draft"],
}})


@pytest.fixture(scope="module")
def rosters() -> dict:
    return load_rosters()


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def _search(client: TestClient, merchant: str, header: str,
            shopper_id: str | None = None) -> dict:
    params: dict = {"category": "laptop", "limit": 100}
    if shopper_id:
        params["shopper_id"] = shopper_id
    response = client.get(f"/{merchant}/ucp/catalog/search", params=params,
                          headers={"UCP-Agent": header})
    assert response.status_code == 200, response.text
    return response.json()


def _record_ids(body: dict) -> set[str]:
    blocks = body.get("extensions", {}).get(BENEFIT_VALUE, [])
    return {
        entry["record"]["record_id"]
        for block in blocks
        for entry in block.get("records", [])
    }


class TestTheMerchantIsTheAuthorityOnMembership:
    def test_a_real_id_resolves_to_the_merchants_own_facts(self, rosters):
        identity = resolve_shopper(rosters, "voltway", CIRCLE)
        assert identity["linked"] is True
        assert identity["tier"] == "circle"
        assert identity["status"] == "member"

    def test_an_unknown_id_is_not_linked_and_is_not_an_error(self, rosters):
        identity = resolve_shopper(rosters, "voltway", "shopper-nobody")
        assert identity["linked"] is False
        assert "tier" not in identity

    def test_no_id_at_all_resolves_the_same_way_as_an_unknown_one(self, rosters):
        assert resolve_shopper(rosters, "voltway", None) == NOT_LINKED

    def test_membership_is_per_merchant_not_global(self, rosters):
        """The same shopper, two merchants, two different answers."""
        assert resolve_shopper(rosters, "voltway", CIRCLE)["linked"] is True
        assert resolve_shopper(rosters, "northgear", CIRCLE)["linked"] is False
        assert resolve_shopper(rosters, "northgear", PLUS)["tier"] == "plus"
        assert resolve_shopper(rosters, "voltway", PLUS)["status"] == "prospect"

    def test_an_agent_cannot_assert_its_way_into_a_tier(self, client):
        """The wire carries an id and nothing else that could be believed.

        ``tier`` is not a field the link route reads, so sending one is not a
        way to acquire one.
        """
        response = client.post(
            "/northgear/ucp/identity/link",
            json={"shopper_id": "shopper-nobody", "tier": "plus",
                  "status": "paid_member"},
            headers={"UCP-Agent": IDENTIFIED},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["linked"] is False
        assert body.get("tier") is None

    def test_linking_is_refused_when_the_capability_was_not_negotiated(self, client):
        response = client.post("/voltway/ucp/identity/link",
                               json={"shopper_id": CIRCLE},
                               headers={"UCP-Agent": ANONYMOUS})
        assert response.status_code == 406


class TestConsentIsStructural:
    """A scoped record is never selected, rather than selected and filtered."""

    SCOPED = [{"record": {"record_id": "personal", "sku_id": None,
                          "fact": {"discount_pct": 10, "shopper_id": CIRCLE}}}]
    OPEN = [{"record": {"record_id": "everyone", "sku_id": None, "fact": {}}}]

    def test_a_scoped_record_reaches_the_member_it_names(self):
        got = for_sku(self.SCOPED, "VOL-0031", CIRCLE)
        assert [e["record"]["record_id"] for e in got] == ["personal"]

    def test_a_scoped_record_does_not_reach_anyone_else(self):
        assert for_sku(self.SCOPED, "VOL-0031", PLUS) == []

    def test_a_scoped_record_does_not_reach_an_anonymous_request(self):
        assert for_sku(self.SCOPED, "VOL-0031", None) == []

    def test_an_unscoped_record_is_unaffected_by_identity(self):
        for shopper in (None, CIRCLE, PLUS):
            assert len(for_sku(self.OPEN, "VOL-0031", shopper)) == 1

    def test_the_server_serves_the_personal_offer_only_to_its_member(self, client):
        personal = "vw-member-price-10-shopper-001"
        assert personal in _record_ids(_search(client, "voltway", IDENTIFIED, CIRCLE))
        assert personal not in _record_ids(_search(client, "voltway", IDENTIFIED, PLUS))
        assert personal not in _record_ids(_search(client, "voltway", IDENTIFIED))


class TestIdentityRidesNegotiationLikeEverythingElse:
    def test_an_agent_that_did_not_declare_identity_gets_no_shopper_block(self, client):
        body = _search(client, "voltway", ANONYMOUS, CIRCLE)
        assert "shopper" not in body

    def test_an_anonymous_request_gets_no_shopper_block_either(self, client):
        """No block is a different answer from ``linked: false``.

        "You did not tell me who this is" must leave the agent's own default
        attestation standing; "I do not know who that is" must not.
        """
        assert "shopper" not in _search(client, "voltway", IDENTIFIED)

    def test_an_identified_request_is_answered_by_the_merchant(self, client):
        body = _search(client, "voltway", IDENTIFIED, CIRCLE)
        assert body["shopper"]["linked"] is True
        assert body["shopper"]["tier"] == "circle"

    def test_the_control_merchant_never_serves_an_identity(self, client):
        """CityCircuit publishes no extension, so it reaches no identity path."""
        assert "shopper" not in _search(client, "citycircuit", IDENTIFIED, CIRCLE)


class TestWhatAnAttestationIsWorth:
    def test_an_unidentified_run_keeps_the_static_attestation(self):
        """The whole point of emitting no block: nothing about today changes."""
        assert "member" in ATTESTED_CONDITIONS
        assert "paid_member" not in ATTESTED_CONDITIONS

    def test_a_stranger_earns_no_membership_token(self):
        earned = attested_conditions({"linked": False})
        assert "member" not in earned
        assert "paid_member" not in earned
        assert set(SHOPPER_INDEPENDENT) <= set(earned)

    def test_a_prospect_is_recognised_and_earns_nothing(self):
        """Being known and being a member are different facts.

        Voltway knows shopper-002 -- they have browsed, they are on the list --
        and they have joined nothing. Treating ``linked`` as membership would
        hand the member price to every shopper the merchant can name.
        """
        earned = attested_conditions(
            {"linked": True, "status": "prospect", "tier": None})
        assert "member" not in earned
        assert earned == SHOPPER_INDEPENDENT

    def test_a_free_member_earns_member_and_their_tier(self):
        earned = attested_conditions(
            {"linked": True, "status": "member", "tier": "circle"})
        assert "member" in earned
        assert "circle_tier" in earned
        assert "paid_member" not in earned

    def test_only_a_paid_member_earns_paid_member(self):
        """``reference_policy`` withholds ``paid_member`` from everyone because
        an agent cannot credit a benefit the shopper would have to buy first.
        A shopper who has already bought it is the case that constant cannot
        express, and the merchant is the only party who knows."""
        earned = attested_conditions(
            {"linked": True, "status": "paid_member", "tier": "plus"})
        assert "paid_member" in earned
        assert "plus_tier" in earned

    def test_northgear_plus_points_credit_nothing_without_the_attestation(self):
        """ng-points-2x is gated on ``paid_member`` and has been uncreditable
        for every shopper since it was signed. That is the record identity
        actually unlocks, so pin both halves of it."""
        from bondlayer.records.serialise import signed_from_json
        from bondlayer.ucp.records import load_records
        from bondlayer.valuation import DeterministicValuation
        from bondlayer.valuation.reference_policy import (
            MERCHANT_DOMAINS,
            REFERENCE_SHOPPER_POLICY,
        )
        from bondlayer.types import Sku

        envelopes = [e for e in load_records("northgear")
                     if e["record"]["record_id"] == "ng-points-2x"]
        assert envelopes, "ng-points-2x is no longer published"
        records = [signed_from_json(e) for e in envelopes]
        sku = Sku(sku_id="NG-0001", title="Laptop", category="laptop",
                  shelf_price=Decimal("1000.00"), attributes={"merchant": "northgear"})

        def credited(attested):
            cost = DeterministicValuation(
                _AlwaysValid(), merchant_domains=MERCHANT_DOMAINS,
                satisfied_conditions=attested,
            ).effective_cost(sku, records, REFERENCE_SHOPPER_POLICY)
            return cost.total_credited

        assert credited(attested_conditions({"linked": False})) == Decimal("0")
        assert credited(attested_conditions(
            {"linked": True, "status": "paid_member", "tier": "plus"})) > Decimal("0")


class TestIdentityChangesWhoWins:
    """The end of the port, through the real server and the real valuation.

    shopper-002 is a paid NorthGear Plus member and has never joined Voltway
    Circle. Voltway wins the anonymous comparison; once the merchants answer
    for this particular shopper, NorthGear does -- not because anything was
    re-ranked, but because each merchant's own answer decided which of its
    records it was allowed to be credited for.
    """

    @staticmethod
    def _run(client: TestClient, shopper_id: str | None):
        from bondlayer.agent.composition import run_request
        from bondlayer.valuation.reference_policy import REFERENCE_SHOPPER_POLICY

        sys_path_agent()
        from src.agent import ucp_client  # noqa: PLC0415

        merchants = ["voltway", "citycircuit", "northgear"]
        return run_request(
            "laptop under $1500", merchants,
            ucp_client.make_fetcher(client, shopper_id=shopper_id),
            extension=True,
            verify=ucp_client.make_verifier(client, merchants=merchants),
            policy={bt.value: v
                    for bt, v in REFERENCE_SHOPPER_POLICY.values_aud.items()},
        )

    def test_anonymously_voltway_wins(self, client):
        run = self._run(client, None)
        assert run.ranked[0].merchant == "voltway"

    def test_a_northgear_plus_member_who_never_joined_voltway_flips_it(self, client):
        anonymous = self._run(client, None)
        identified = self._run(client, PLUS)

        assert anonymous.ranked[0].merchant == "voltway"
        assert identified.ranked[0].merchant == "northgear"

        # Nothing about the shelf moved; only what each merchant is owed.
        by_sku = {r.sku_id: r for r in anonymous.ranked}
        for r in identified.ranked:
            assert r.shelf_price == by_sku[r.sku_id].shelf_price

    def test_the_trace_says_why_for_both_merchants(self, client):
        summaries = [s.summary for s in self._run(client, PLUS).steps]
        assert any("northgear confirms this shopper is a plus member" in s
                   for s in summaries)
        assert any("voltway knows this shopper but says they are not a member"
                   in s for s in summaries)

    def test_a_voltway_member_does_not_flip_it(self, client):
        """shopper-001's Circle benefits are already valued to this shopper's
        own caps anonymously, so identifying changes the reasoning and not the
        arithmetic. Worth pinning: the shopper-side budget is what stops a
        merchant buying rank by restating a benefit."""
        anonymous = self._run(client, None)
        identified = self._run(client, CIRCLE)
        assert identified.ranked[0].merchant == "voltway"
        assert identified.ranked[0].effective_cost == anonymous.ranked[0].effective_cost


@pytest.mark.parametrize("identity, expected", [
    (None, Decimal("0")),
    ({"linked": False}, Decimal("0")),
    ({"linked": True, "status": "member", "tier": "circle"}, Decimal("25")),
])
def test_live_eligibility_combines_dynamic_domains_and_merchant_identity(identity, expected):
    from bondlayer.agent.composition import run_request

    body = {
        "business": {"id": "uploaded"},
        "products": [{"id": "ONE", "title": "Laptop", "category": "laptop",
                      "price": {"amount": "1000"}, "attributes": {}}],
        "extensions": {BENEFIT_VALUE: [{
            "sku_id": "ONE", "issuer": "uploaded.example",
            "records": [{"record": {"record_id": "member-offer", "benefit_type": "member_price",
                                     "value_ceiling_aud": "25", "conditions": ["member"]},
                         "signature": "test", "key_id": "test", "signed": True}],
        }]},
    }
    if identity is not None:
        body["shopper"] = identity
    run = run_request(
        "laptop", ["uploaded"], lambda *args, **kwargs: body,
        verify=lambda entry: True, policy={"member_price": Decimal("25")},
        merchant_domains={"uploaded": "uploaded.example"}, satisfied_conditions=(),
    )
    assert run.winner.credited == expected


def sys_path_agent() -> None:
    """Put ``buyer-agent`` on the path; it is a sibling package, not a dep."""
    import sys
    from pathlib import Path

    agent = Path(__file__).resolve().parents[2] / "buyer-agent"
    if str(agent) not in sys.path:
        sys.path.insert(0, str(agent))


class _AlwaysValid:
    """A ``Signer`` stand-in: signature checking is not what these tests pin."""

    def sign(self, record):  # pragma: no cover - never called
        raise NotImplementedError

    def verify(self, signed) -> bool:
        return True
