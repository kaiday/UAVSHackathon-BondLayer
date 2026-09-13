"""Start the merchant service. One command, no arguments, no network.

    python run_server.py              # serves on :8000, or the next free port
    python run_server.py 8123         # or name one
    PORT=8123 python run_server.py    # or set PORT

If the preferred port is busy it moves to the next free one and prints the URL
it actually bound. A demo machine with something already on :8000 -- another
team's server, an earlier run of this one -- should not stop the demo, and
should never leave you reading a stale build on the port you expected.
"""

from __future__ import annotations

import os
import socket
import sys

import uvicorn

from bondlayer.ucp.profile import load_merchants

HOST = "127.0.0.1"


def free_port(preferred: int, tries: int = 20) -> int:
    """First free port at or after ``preferred``."""
    for port in range(preferred, preferred + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if probe.connect_ex((HOST, port)) != 0:
                return port
    raise SystemExit(
        f"no free port in {preferred}-{preferred + tries - 1}; pass one explicitly"
    )


def main() -> None:
    preferred = int(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("PORT", 8000))
    port = free_port(preferred)

    print("BondLayer merchant service")
    for m in load_merchants().values():
        ext = "benefit extension" if m.publishes_benefit_extension else "plain UCP"
        print(f"  {m.display_name:<12} {m.domain:<22} {m.role:<11} {ext}")
    print()
    if port != preferred:
        print(f"  ! port {preferred} was busy -- using {port} instead")
        print()
    base = f"http://{HOST}:{port}"
    print(f"  console   {base}/console/")
    print(f"  profile   {base}/voltway/.well-known/ucp")
    print(f"  search    {base}/voltway/ucp/catalog/search?category=laptop")
    print(f"  onboard   {base}/onboard/report/voltway")
    print(f"  docs      {base}/docs")
    print()
    uvicorn.run("bondlayer.ucp.server:app", host=HOST, port=port, log_level="warning")


if __name__ == "__main__":
    main()
