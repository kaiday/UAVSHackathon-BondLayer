"""Contract and behavior checks for the merchant-network demo."""

from agentbridge.evaluation import run_case, run_repeats, scoreboard, visibility
from agentbridge.merchant_network import serve_network, stop_network
from agentbridge.network_agent import rank


def test_network_plain_and_extended_flip():
    urls, servers = serve_network(base_port=8051)
    try:
        request = "Find me a good 65W USB-C GaN wall charger under $45"
        plain = run_case(urls, request, extended=False, run_id="test-plain")
        extended = run_case(urls, request, extended=True, run_id="test-extended")
        assert plain["recommendation"] == "volt-depot"
        assert extended["recommendation"] == "harbor-tech"
        assert all("extensions" not in d["wire_payload"] for d in plain["decisions"])
        assert any("extensions" in d["wire_payload"] for d in extended["decisions"])
    finally:
        stop_network(servers)


def test_unsigned_claim_never_credited_and_scoreboard_is_derived():
    urls, servers = serve_network(base_port=8054)
    try:
        record = run_case(urls, "65W USB-C charger under $45", extended=True,
                          run_id="test-adversary")
        spark = next(d for d in record["decisions"] if d["merchant_id"] == "sparkline")
        assert spark["verified_value_cents"] == 0
        assert spark["unsigned_penalty_cents"] > 0
        board = scoreboard(record)
        assert next(row for row in board if row["merchant_id"] == "harbor-tech")["won"]
        assert visibility(record, "harbor-tech")["verified_value_cents"] == 1715
    finally:
        stop_network(servers)


def test_repeat_metric_reports_every_recorded_run():
    urls, servers = serve_network(base_port=8057)
    try:
        records, metrics = run_repeats(urls, "65W USB-C charger under $45", 3)
        assert len(records) == 3
        assert metrics["attempted"] == metrics["recorded"] == 3
        assert metrics["stable"] == 3
    finally:
        stop_network(servers)
