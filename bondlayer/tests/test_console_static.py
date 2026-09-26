"""The Next.js console is served as static files at /console, with no invented figures.

The build output (bondlayer/app/out) is committed, so these run with no Node.
Every number on those pages is fetched from /onboard at runtime; the HTML must
carry none of the mock figures the design preview shipped with.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bondlayer.ucp.server import CONSOLE, app

pytestmark = pytest.mark.skipif(not CONSOLE.is_dir(), reason="bondlayer/app/out not built")

PAGES = ["/console/", "/console/requests/", "/console/catalogue/", "/console/quality/",
         "/console/benefits/", "/console/settings/", "/console/onboarding/"]
MOCK_FIGURES = ["unsplash", "REQ-0017", "257.03", "46.66", "74.50", "Surface Laptop Go 3"]

client = TestClient(app)


@pytest.mark.parametrize("path", PAGES)
def test_console_page_is_served(path):
    response = client.get(path)
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "BondLayer" in response.text


@pytest.mark.parametrize("path", PAGES)
def test_served_html_carries_no_mock_figures(path):
    html = client.get(path).text
    for figure in MOCK_FIGURES:
        assert figure not in html, f"{figure!r} in {path}"


def test_no_built_file_carries_mock_figures():
    for file in Path(CONSOLE).rglob("*"):
        if file.suffix in {".html", ".js", ".txt", ".json"}:
            text = file.read_text(encoding="utf-8", errors="ignore")
            for figure in MOCK_FIGURES:
                assert figure not in text, f"{figure!r} in {file.relative_to(CONSOLE)}"


def test_the_export_connects_ask_and_policy_upload_to_live_endpoints():
    """Catch a stale static export even when the Python integration is current."""
    bundle = "".join(
        file.read_text(encoding="utf-8", errors="ignore")
        for file in Path(CONSOLE).rglob("*.js")
    )
    assert "/onboard/ask/" in bundle
    assert "/onboard/policies/" in bundle
    assert "response_id" in bundle
    assert "Test OpenAI connection" in bundle
    assert "Use voice input" not in bundle


def test_the_old_dashboard_is_still_served():
    assert client.get("/dashboard/").status_code == 200
