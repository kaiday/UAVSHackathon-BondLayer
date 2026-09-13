"""Live agent traffic -- the UCP calls this server actually received.

The console's Analytics page shows two things and labels them so they cannot be
confused: ``analytics.py``'s **benchmark** (30 frozen requests) and this
module's **live** log. Minh's first console drew "agent requests over time"
from a hard-coded series; this is where a real one comes from.

**What is recorded -- only what the merchant already receives, as counts.**
One ``call`` event per request to a merchant's UCP surface (profile, catalogue
search and lookup, intent, checkout): when, which merchant, which route, the
HTTP status, and which BondLayer-relevant capabilities the agent *declared* in
``UCP-Agent``. One ``order`` event per confirmed checkout: the order id and how
many cited records were honoured.

**What is never recorded.** The shopper's utterance, the search text, the
request body, the caller's address, or anything shopper-side. And never "won a
comparison": a merchant does not learn that it was compared (root README), so
the log cannot know it -- an order placed is the only win a merchant sees.

``/onboard/*``, ``/console`` and ``/dashboard`` are the merchant's own screens,
not agent traffic, and are never logged.

**Where it lives.** In memory, capped at ``MAXLEN`` events. ``run_server.py``
calls ``LOG.persist_to(DEFAULT_PATH)`` so a restart during the demo keeps the
chart; everything else -- the test suite, ``trace_run.py`` -- stays in memory, so
running the tests never writes into the demo's traffic. ``data/traffic/`` is
gitignored. ``DELETE /onboard/traffic`` resets both for a clean demo.
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, FastAPI, Query, Request

from bondlayer.ucp.capabilities import BENEFIT_VALUE, CHECKOUT, INTENT_MATCH, parse_agent_header

router = APIRouter(prefix="/onboard", tags=["traffic"])

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "data" / "traffic" / "events.jsonl"
MAXLEN = 10_000

ROUTES = ("profile", "search", "lookup", "intent", "checkout")
BUCKETS = {"minute": 60, "hour": 3600}

_PATH = re.compile(
    r"^/(?P<merchant>[A-Za-z0-9_-]+)/"
    r"(?:(?P<profile>\.well-known/ucp)|ucp/(?P<route>catalog/search|catalog/lookup|intent/propose|checkout))/?$"
)
_ROUTE = {
    "catalog/search": "search",
    "catalog/lookup": "lookup",
    "intent/propose": "intent",
    "checkout": "checkout",
}

#: The declared capabilities worth counting, by the short name the console shows.
DECLARED = {BENEFIT_VALUE: "benefit_value", INTENT_MATCH: "intent_match", CHECKOUT: "checkout"}


@dataclass(frozen=True)
class TrafficEvent:
    ts: float
    kind: str  # "call" | "order"
    merchant: str
    route: str | None = None
    status: int | None = None
    declared: tuple[str, ...] = ()
    order_id: str | None = None
    honoured: int | None = None
    cited: int | None = None


def classify(path: str) -> tuple[str, str] | None:
    """``(merchant, route)`` for a merchant's UCP surface; ``None`` for anything else."""
    match = _PATH.match(path)
    if not match:
        return None
    route = "profile" if match["profile"] else _ROUTE[match["route"]]
    return match["merchant"], route


def declared_capabilities(ucp_agent: str | None) -> tuple[str, ...]:
    """What the agent declared, read the same way negotiation reads it."""
    declared = parse_agent_header(ucp_agent)
    return tuple(sorted(short for name, short in DECLARED.items() if name in declared))


class TrafficLog:
    def __init__(self, path: Path | None = None, clock: Callable[[], float] = time.time,
                 maxlen: int = MAXLEN) -> None:
        self.clock = clock
        self.path: Path | None = None
        self._events: deque[TrafficEvent] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        if path is not None:
            self.persist_to(path)

    # --- writing -----------------------------------------------------------

    def persist_to(self, path: Path) -> None:
        """Append every event to ``path`` from now on, after loading what is there."""
        self.path = path
        if not path.is_file():
            return
        with self._lock:
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    raw = json.loads(line)
                    raw["declared"] = tuple(raw.get("declared", ()))
                    self._events.append(TrafficEvent(**raw))
                except (ValueError, TypeError):
                    continue  # a torn last line after a crash is not a reason to lose the rest

    def _append(self, event: TrafficEvent) -> None:
        with self._lock:
            self._events.append(event)
            if self.path is not None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as out:
                    out.write(json.dumps(asdict(event)) + "\n")

    def call(self, merchant: str, route: str, status: int, ucp_agent: str | None) -> None:
        self._append(TrafficEvent(
            ts=self.clock(), kind="call", merchant=merchant, route=route, status=status,
            declared=declared_capabilities(ucp_agent),
        ))

    def order(self, merchant: str, order_id: str, honoured: int, cited: int) -> None:
        self._append(TrafficEvent(
            ts=self.clock(), kind="order", merchant=merchant, order_id=order_id,
            honoured=honoured, cited=cited,
        ))

    def reset(self) -> None:
        with self._lock:
            self._events.clear()
            if self.path is not None and self.path.is_file():
                self.path.unlink()

    # --- reading -----------------------------------------------------------

    def events(self) -> list[TrafficEvent]:
        with self._lock:
            return list(self._events)

    def summary(self, merchant: str | None = None, bucket: str = "minute",
                window: int = 60) -> dict:
        size = BUCKETS[bucket]
        now = self.clock()
        end = (int(now // size) + 1) * size
        start = end - window * size

        everything = self.events()
        events = [e for e in everything if merchant is None or e.merchant == merchant]
        calls = [e for e in events if e.kind == "call"]
        orders = [e for e in events if e.kind == "order"]

        series = [{"t": start + i * size, **{r: 0 for r in ROUTES}, "total": 0}
                  for i in range(window)]
        for e in calls:
            if start <= e.ts < end:
                point = series[int((e.ts - start) // size)]
                point[e.route] += 1
                point["total"] += 1

        by_merchant: dict[str, dict] = {}
        for e in everything:
            row = by_merchant.setdefault(e.merchant, {"merchant": e.merchant, "calls": 0, "orders": 0})
            row["calls" if e.kind == "call" else "orders"] += 1

        declaring = sum(1 for e in calls if "benefit_value" in e.declared)
        return {
            "source": "live",
            "merchant": merchant,
            "now": now,
            "first_event": min((e.ts for e in events), default=None),
            "bucket": bucket,
            "bucket_seconds": size,
            "window": window,
            "totals": {
                "calls": len(calls),
                "by_route": {r: sum(1 for e in calls if e.route == r) for r in ROUTES},
                "refused_406": sum(1 for e in calls if e.status == 406),
                "declared_benefit_value": declaring,
                "declared_intent_match": sum(1 for e in calls if "intent_match" in e.declared),
                "benefit_value_share": round(declaring / len(calls), 3) if calls else None,
            },
            "orders": {
                "count": len(orders),
                "honoured": sum(e.honoured or 0 for e in orders),
                "cited": sum(e.cited or 0 for e in orders),
            },
            "by_merchant": sorted(by_merchant.values(), key=lambda r: (-r["calls"], r["merchant"])),
            "series": series,
            "recent": [asdict(e) for e in reversed(events[-20:])],
        }


#: The server's one log. Looked up at call time, so tests can swap it.
LOG = TrafficLog()


@router.get("/traffic")
def traffic(
    merchant: str | None = None,
    bucket: str = Query(default="minute", pattern="^(minute|hour)$"),
    window: int = Query(default=60, ge=1, le=240),
) -> dict:
    return LOG.summary(merchant, bucket, window)


@router.delete("/traffic")
def reset_traffic() -> dict:
    LOG.reset()
    return {"reset": True}


def install(app: FastAPI) -> None:
    """Mount the routes and the one middleware that records calls."""
    app.include_router(router)

    @app.middleware("http")
    async def record_traffic(request: Request, call_next):
        response = await call_next(request)
        hit = classify(request.url.path)
        if hit is not None:
            LOG.call(hit[0], hit[1], response.status_code, request.headers.get("UCP-Agent"))
        return response
