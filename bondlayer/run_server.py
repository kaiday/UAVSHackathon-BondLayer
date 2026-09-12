"""Start the merchant service. One command, no arguments, no network.

    python run_server.py

Serves all three merchants from the frozen catalogue on http://127.0.0.1:8000.
Nothing is fetched, no key is generated, no model is called.
"""

from __future__ import annotations

import uvicorn

from bondlayer.ucp.profile import load_merchants


def main() -> None:
    merchants = load_merchants()
    print("BondLayer merchant service")
    for mid, m in merchants.items():
        ext = "benefit extension" if m.publishes_benefit_extension else "plain UCP"
        print(f"  {m.display_name:<12} {m.domain:<22} {m.role:<11} {ext}")
    print()
    print("  profile   http://127.0.0.1:8000/voltway/.well-known/ucp")
    print("  search    http://127.0.0.1:8000/voltway/ucp/catalog/search?category=laptop")
    print("  onboard   http://127.0.0.1:8000/onboard/report/voltway")
    print("  docs      http://127.0.0.1:8000/docs")
    print()
    uvicorn.run("bondlayer.ucp.server:app", host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    main()
