"""The UCP conformance checks, as pytest.

Same checks the /evidence screen renders, run here so they fail CI rather than
only looking green on a projector. Booting the three real HTTP services is the
point: an in-process check would assume away the claim being made (D9.11).
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bondlayer.demo_data import MERCHANTS, build_services  # noqa: E402
from bondlayer.ucp import conformance  # noqa: E402

PORTS = {mid: 9200 + i for i, mid in enumerate(MERCHANTS)}


@pytest.fixture(scope="module")
def urls() -> dict[str, str]:
    services, _ = build_services()
    for mid, port in PORTS.items():
        cfg = uvicorn.Config(services[mid].build_app(), host="127.0.0.1",
                             port=port, log_level="error")
        threading.Thread(target=uvicorn.Server(cfg).run, daemon=True).start()
    time.sleep(1.5)
    return {mid: f"http://127.0.0.1:{port}" for mid, port in PORTS.items()}


def test_every_conformance_check_passes(urls):
    report = conformance.run(urls)
    failures = [f"{c.name}: {c.detail}" for c in report.checks if not c.passed]
    assert not failures, "\n".join(failures)
    assert report.total >= 12, f"only {report.total} checks ran"


def test_a_broken_namespace_would_be_caught(urls, monkeypatch):
    """The checks must be capable of failing. A suite that cannot go red is
    decoration, and this one is load-bearing evidence."""
    monkeypatch.setattr(conformance.caps, "BENEFIT_VALUE", "dev.ucp.shopping.benefit_value")
    report = conformance.run(urls)
    squat = next(c for c in report.checks if "reserved namespace" in c.name)
    assert not squat.passed, "squatting dev.ucp.* was not detected"
