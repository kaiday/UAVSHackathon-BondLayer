"""Capture the actual HTTP exchanges, so the protocol can be watched happening.

The comparison screen shows what the agent concluded. This shows what went over
the socket to get there: the `UCP-Agent` header the agent sent, the capability
set the merchant activated in response, and the raw JSON body — for all three
merchants, under both capability declarations.

It also emits the equivalent `curl`, because the strongest possible answer to
"is your UCP real?" is a judge running the command on their own laptop and
getting the same bytes back.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

import httpx

from . import capabilities as caps

PLAIN = [caps.CATALOG_SEARCH, caps.CATALOG_LOOKUP]
BONDLAYER = PLAIN + [caps.IDENTITY_LINKING, caps.BENEFIT_VALUE]

#: Bodies are shown verbatim on a projector; a full catalogue would be unreadable.
BODY_LIMIT = 4000


@dataclass
class Exchange:
    merchant_id: str
    method: str
    url: str
    request_headers: dict[str, str]
    status: int
    elapsed_ms: int
    body: str
    truncated: bool = False
    curl: str = ""
    active_capabilities: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _curl(url: str, headers: dict[str, str]) -> str:
    parts = ["curl -s"]
    for k, v in headers.items():
        parts.append(f"\\\n  -H '{k}: {v}'")
    parts.append(f"\\\n  '{url}'")
    return " ".join(parts)


def _capture(
    client: httpx.Client, merchant_id: str, url: str, headers: dict[str, str]
) -> Exchange:
    resp = client.get(url, headers=headers)
    try:
        parsed = resp.json()
        body = json.dumps(parsed, indent=2)
        active = parsed.get("active_capabilities", []) if isinstance(parsed, dict) else []
    except Exception:
        body, active = resp.text, []
    truncated = len(body) > BODY_LIMIT
    return Exchange(
        merchant_id=merchant_id,
        method="GET",
        url=url,
        request_headers=dict(headers),
        status=resp.status_code,
        elapsed_ms=int(resp.elapsed.total_seconds() * 1000),
        body=body[:BODY_LIMIT] + ("\n… truncated" if truncated else ""),
        truncated=truncated,
        curl=_curl(url, headers),
        active_capabilities=active,
    )


def capture(
    merchant_urls: dict[str, str],
    *,
    use_extension: bool,
    query: str = "waterproof jacket",
    member_id: str | None = None,
    client: httpx.Client | None = None,
) -> list[Exchange]:
    """The two exchanges the agent actually makes, for every merchant.

    Exactly what `shopping_agent.fetch_offers` does — the declaration fetch that
    drives negotiation and pins the key, then the catalogue search under the
    negotiated set.
    """
    owns = client is None
    client = client or httpx.Client(timeout=10.0)
    declared = BONDLAYER if use_extension else PLAIN
    headers = {"UCP-Agent": f"demo-shopper/0.1; capabilities={','.join(declared)}"}

    out: list[Exchange] = []
    try:
        for mid, base in merchant_urls.items():
            out.append(_capture(client, mid, f"{base}/.well-known/ucp", headers))
            search = f"{base}/ucp/catalog/search?q={query.replace(' ', '+')}"
            if member_id and use_extension:
                search += f"&member_id={member_id}"
            out.append(_capture(client, mid, search, headers))
    finally:
        if owns:
            client.close()
    return out
