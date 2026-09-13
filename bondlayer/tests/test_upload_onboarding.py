"""Zero to a persistent, discoverable merchant, using the actual upload routes."""

import json

import pytest
from fastapi.testclient import TestClient

from bondlayer.ucp import onboard, server

CSV = "sku,title,category,price,stock\nLAP-1,Work Laptop,laptop,599.00,3\n"


@pytest.fixture
def empty_app(tmp_path, monkeypatch):
    with monkeypatch.context() as patch:
        patch.delenv("BONDLAYER_TEST_DATA", raising=False)
        patch.setattr(server, "UPLOADS", tmp_path)
        with TestClient(server.create_app()) as client:
            yield client
    server.create_app()


def upload(client, content=CSV, merchant="my-store", **params):
    return client.post("/onboard/catalog", params={"merchant": merchant, **params},
                       files={"file": ("catalogue.csv", content, "text/csv")})


def test_fresh_install_has_no_fixture_merchants_or_history(empty_app):
    assert empty_app.get("/health").json()["merchants"] == 0
    assert empty_app.get("/onboard/merchants").json() == []
    assert empty_app.get("/onboard/requests").json() == []
    for mid in ("voltway", "citycircuit", "northgear"):
        assert empty_app.get(f"/{mid}/.well-known/ucp").status_code == 404
    assert empty_app.get("/onboard/requests/R01").status_code == 404


def test_preview_publish_restart_and_checkout(empty_app, tmp_path):
    preview = upload(empty_app, preview=True, create=True)
    assert preview.status_code == 200
    assert preview.json()["report"]["skus"] == 1
    assert preview.json()["published"] is False
    assert empty_app.get("/onboard/merchants").json() == []
    assert list(tmp_path.iterdir()) == []
    response = empty_app.post("/onboard/catalog?merchant=my-store&create=true",
                             files={"file": ("catalogue.csv", CSV)},
                             data={"display_name": "My Actual Store", "domain": "https://shop.retail.test"})
    assert response.status_code == 200
    assert response.json()["published"] is True
    server.create_app()
    profile = empty_app.get("/my-store/.well-known/ucp").json()
    assert profile["business"]["name"] == "My Actual Store"
    assert profile["business"]["domain"] == "shop.retail.test"
    assert profile["extensions"] == {} and profile["signing_keys"] == []
    product = empty_app.get("/my-store/ucp/catalog/search").json()["products"][0]
    assert product["title"] == "Work Laptop"
    assert product["attributes"]["stock"] == 3
    order = empty_app.post("/my-store/ucp/checkout", headers={"UCP-Agent": "dev.ucp.shopping.checkout"},
                           json={"items": [{"sku_id": "LAP-1", "quantity": 4}]})
    assert order.status_code == 409
    assert empty_app.get("/onboard/merchants").json()[0]["display_name"] == "My Actual Store"


@pytest.mark.parametrize("csv", [
    "sku,merchant,title,category,price\nA\n",
    "sku,title,category,price\nA,Laptop,laptop,-1\n",
    "sku,title,category,price\n",
    "sku,title,category,price\nA,Laptop,laptop,10\nA,Other,laptop,20\n",
    "sku,title,category,price,currency\nA,Laptop,laptop,10,USD\n",
    "sku,title,category,price,weight_kg\nA,Laptop,laptop,10,NaN\n",
])
def test_invalid_upload_is_400_and_does_not_register(empty_app, tmp_path, csv):
    assert upload(empty_app, csv).status_code == 400
    assert empty_app.get("/my-store/ucp/catalog/search").status_code == 404
    assert list(tmp_path.iterdir()) == []


def test_merchant_ids_cannot_escape_storage(empty_app, tmp_path):
    assert upload(empty_app, merchant="../escape").status_code == 400
    assert list(tmp_path.iterdir()) == []


def test_disk_failure_keeps_existing_data(empty_app, monkeypatch, tmp_path):
    assert upload(empty_app).status_code == 200
    before = (tmp_path / "my-store.merchant.json").read_bytes()
    def fail(*args):
        raise OSError("disk unavailable")
    monkeypatch.setattr(onboard, "save_upload", fail)
    assert upload(empty_app, CSV.replace("599.00", "1.00")).status_code == 500
    assert (tmp_path / "my-store.merchant.json").read_bytes() == before
    assert empty_app.get("/my-store/ucp/catalog/search").json()["products"][0]["price"]["amount"] == "599.00"


def test_create_cannot_overwrite_existing_merchant(empty_app, tmp_path):
    assert upload(empty_app, create=True).status_code == 200
    before = (tmp_path / "my-store.merchant.json").read_bytes()
    assert upload(empty_app, CSV.replace("599.00", "1.00"), create=True).status_code == 409
    assert (tmp_path / "my-store.merchant.json").read_bytes() == before


def test_legacy_upload_survives_without_inventing_records(empty_app, tmp_path):
    path = tmp_path / "existing.csv"
    text = "sku,merchant,title,category,price,stock,source_url\nP1,existing,Uploaded laptop,laptop,499,available\n"
    path.write_text(text, encoding="utf-8")
    server.create_app()
    assert path.read_text(encoding="utf-8") == text
    merchants = empty_app.get("/onboard/merchants").json()
    assert [m["merchant"] for m in merchants] == ["existing"]
    assert empty_app.get("/existing/ucp/catalog/search").json()["products"][0]["title"] == "Uploaded laptop"
    assert empty_app.get("/onboard/report/existing").json()["by_rule"]["column_count"] == 1


def test_csv_can_infer_merchant_and_optional_fields_are_independent(empty_app):
    content = "sku,merchant,title,category,price\nA,retailer,First Laptop,laptop,499\nB,retailer,Second Laptop,laptop,699\n"
    response = empty_app.post("/onboard/catalog", files={"file": ("catalogue.csv", content)})
    assert response.status_code == 200
    products = empty_app.get("/retailer/ucp/catalog/search").json()["products"]
    assert [p["title"] for p in products] == ["First Laptop", "Second Laptop"]


def test_template_contains_no_sample_products(empty_app):
    response = empty_app.get("/onboard/catalog/template")
    assert response.status_code == 200
    assert len(response.text.strip().splitlines()) == 1
