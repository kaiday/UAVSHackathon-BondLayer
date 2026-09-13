"""``GET /onboard/analytics`` -- the benchmark, summed.

The console's Analytics page shows two things and labels them so they cannot be
confused: this module's **benchmark** (the 30 frozen requests) and
``traffic.py``'s **live** log. This module is the first.

It adds nothing to the numbers. Every figure is a sum or a count over the
``RequestReport`` JSON that ``onboard`` already loaded from
``data/eval/reports/`` -- the same files ``/onboard/requests*`` serves verbatim,
written by ``scripts/eval_run.py`` at the commit named in
``docs/eval-results.md``. No clock, no network, no model: the same reports give
the same response, which is the only reason these figures may sit next to the
eval table.

Only the non-control rows (``merchants``) are counted. The ``control`` rows
rank the same shelf with no records at all; they answer a different question
and are summarised separately, as the SERVICE + VALUES comparison.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter

from bondlayer.ucp import onboard

router = APIRouter(prefix="/onboard", tags=["analytics"])

EVAL_RESULTS = Path(__file__).resolve().parents[3] / "docs" / "eval-results.md"
_COMMIT = re.compile(r"at commit `([0-9a-f]{7,40})`")


def loss_reason(lost_because: str) -> str:
    """The reason a merchant lost, without the parts that vary per request.

    Grouping rule: keep the text before the first ``:`` or ``;``. That drops the
    dollar amount ("$330 was withheld ...") and the winner ("; voltway won on
    effective cost"), so the same cause groups together whoever won and by how
    much.
    """
    return re.split(r"[:;]", lost_because, maxsplit=1)[0].strip()


def _eval_commit() -> str | None:
    if not EVAL_RESULTS.is_file():
        return None
    match = _COMMIT.search(EVAL_RESULTS.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def benchmark(reports: dict[str, dict]) -> dict:
    """Per-merchant wins, loss reasons and value, plus the one number that matters."""
    merchants: dict[str, dict] = {}
    reasons: dict[str, dict] = {}
    answered = total = answered_control = total_control = 0

    for _, report in sorted(reports.items()):
        metrics = report.get("metrics", {})
        a, t = metrics.get("clauses_answered", [0, 0])
        ac, tc = metrics.get("clauses_answered_control", [0, 0])
        answered, total = answered + a, total + t
        answered_control, total_control = answered_control + ac, total_control + tc

        for row in report["merchants"]:
            m = merchants.setdefault(row["merchant"], {
                "merchant": row["merchant"],
                "control_merchant": row["control_merchant"],
                "requests": 0,
                "wins": 0,
                "value_credited_aud": Decimal("0"),
                "value_withheld_aud": Decimal("0"),
                "_legible": 0.0,
            })
            m["requests"] += 1
            m["wins"] += bool(row["won"])
            m["value_credited_aud"] += Decimal(row["value_credited_aud"])
            m["value_withheld_aud"] += Decimal(row["value_withheld_aud"])
            m["_legible"] += row["legible_share"]
            if row["lost_because"]:
                reason = loss_reason(row["lost_because"])
                entry = reasons.setdefault(reason, {"reason": reason, "count": 0, "merchants": {}})
                entry["count"] += 1
                entry["merchants"][row["merchant"]] = entry["merchants"].get(row["merchant"], 0) + 1

    rows = []
    for m in sorted(merchants.values(), key=lambda m: (-m["wins"], m["merchant"])):
        n = m.pop("requests")
        legible = m.pop("_legible")
        rows.append({
            **m,
            "requests": n,
            "win_rate": round(m["wins"] / n, 3) if n else 0.0,
            "value_credited_aud": str(m["value_credited_aud"]),
            "value_withheld_aud": str(m["value_withheld_aud"]),
            "mean_legible_share": round(legible / n, 3) if n else 0.0,
        })

    return {
        "source": "benchmark",
        "requests": len(reports),
        "eval_commit": _eval_commit(),
        "merchants": rows,
        "loss_reasons": sorted(reasons.values(), key=lambda r: (-r["count"], r["reason"])),
        "service_values_answered": {
            "bondlayer": [answered, total],
            "control": [answered_control, total_control],
        },
    }


@router.get("/analytics")
def analytics() -> dict:
    """The 30 frozen requests, summed. Recomputed from the loaded reports on
    every call; there is nothing to cache and nothing to go stale."""
    return benchmark(onboard._requests)
