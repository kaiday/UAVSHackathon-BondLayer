"""Exercise actual OpenAI with isolated merchant storage, never real merchant files."""

import os
import secrets
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")
sys.path[:0] = [str(ROOT / "bondlayer" / "src"), str(ROOT / "buyer-agent")]
os.environ["BONDLAYER_AI_MODE"] = "openai"
os.environ["BONDLAYER_SERVICE_TOKEN"] = secrets.token_urlsafe(32)
os.environ.pop("BONDLAYER_TEST_DATA", None)

with tempfile.TemporaryDirectory(prefix="bondlayer-live-") as temp:
    os.environ["BONDLAYER_UPLOADS_DIR"] = temp
    from fastapi.testclient import TestClient
    from bondlayer.ucp import server
    from src.agent.main import ShoppingQuery, _handle_query

    client = TestClient(server.create_app())
    csv = "sku,title,category,price,ram,weight_kg,stock\nLIVE-1,Example notebook,laptop,999.00,16GB,1.4,5\n"
    response = client.post("/onboard/catalog?merchant=livecheck&create=true", data={"display_name": "Live integration check", "domain": "livecheck.example"}, files={"file": ("catalogue.csv", csv, "text/csv")})
    assert response.status_code == 200, response.text
    asked = client.post("/onboard/ask/livecheck", json={"question": "What should I improve in this catalogue?"})
    assert asked.status_code == 200, asked.text
    print("Merchant assistance:", asked.json()["ai"]["response_id"])

    document = "# Customer policy\n\n## Returns\nWe accept returns on all laptops within 60 days of delivery. Return shipping is free for every customer, with no membership requirement.\n"
    uploaded = client.post("/onboard/policies/livecheck", files={"file": ("policy.md", document, "text/markdown")})
    assert uploaded.status_code == 200, uploaded.text
    body = uploaded.json()
    print("Policy extraction:", body["ai"]["response_id"], "drafts:", len(body["drafts"]))
    print("Extracted facts and conditions:", [(d["record"]["fact"], d["record"]["conditions"]) for d in body["drafts"]])
    assert body["drafts"]
    for draft in body["drafts"]:
        assert draft["record"]["source_span"] in document
        if draft["record"]["benefit_type"] == "free_returns":
            edited = client.patch(f"/onboard/policies/livecheck/drafts/{draft['draft_id']}", json={"value_ceiling_aud": "40"})
            assert edited.status_code == 200, edited.text
        approved = client.post(f"/onboard/policies/livecheck/drafts/{draft['draft_id']}/approve")
        assert approved.status_code == 200, approved.text
    published = client.post("/onboard/policies/livecheck/publish")
    assert published.status_code == 200, published.text
    print("Published signed records:", published.json()["published"])

    query = _handle_query(ShoppingQuery(query="a laptop under $1,500 that I can return easily", values_aud={"free_returns": "40"}), client)
    assert query["winner"], query
    assert query["winner"]["records_verified"] > 0, query["winner"]
    print("Intent decoding:", query["ai"]["intent"]["response_id"])
    print("Model ranking:", query["ai"]["ranking"]["response_id"])
    print("Winner:", query["winner"]["sku_id"], "verified:", query["winner"]["records_verified"], "credit:", query["winner"]["credited_aud"])
    print("Resolved clauses:", query["winner"]["resolved"])
    assert any(c["kind"] == "service" and c["satisfied"] for c in query["winner"]["resolved"])
    print("Citation reasons:", query["winner"]["citations"])
    assert query["request_id"]
    assert client.get(f"/onboard/requests/{query['request_id']}").json()["source"] == "live"
    print("Checkout:", query["order"])
    assert query["order"]["summary_counts"]["honoured"] > 0
    with TestClient(server.create_app()) as restarted:
        from bondlayer.ucp.intent import verified_records
        assert verified_records(server._merchants["livecheck"])
        assert restarted.get("/onboard/policies/livecheck").json()["published_records"]
    print("Restart: saved policies, published benefits and signing keys restored and verified")
