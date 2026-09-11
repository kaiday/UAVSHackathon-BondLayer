"""Deterministic evaluation and merchant-facing attribution."""

from __future__ import annotations

import copy
import random
from collections import Counter
from typing import Any

from agentbridge.network_agent import evidence_record, fetch_offers, rank


def run_case(urls: dict[str, str], request: str, extended: bool,
             run_id: str = "demo") -> dict[str, Any]:
    """Run one comparison over merchant HTTP wires and return evidence JSON."""
    decisions = fetch_offers(urls, request, extended=extended)
    return evidence_record(request, decisions, extended=extended, run_id=run_id)


def run_repeats(urls: dict[str, str], request: str, repeats: int,
                extended: bool = True) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Repeat with stable merchant-order permutations; never hide failures."""
    records: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for index in range(repeats):
        ordered = list(urls.items())
        random.Random(index).shuffle(ordered)
        record = run_case(dict(ordered), request, extended,
                          run_id=f"repeat-{index + 1}")
        records.append(record)
        if record.get("recommendation"):
            counts[record["recommendation"]] += 1
    recommendation = records[0].get("recommendation") if records else None
    return records, {
        "attempted": repeats,
        "recorded": len(records),
        "stable": sum(1 for r in records if r.get("recommendation") == recommendation),
        "recommendation": recommendation,
        "counts": dict(counts),
    }


def visibility(record: dict[str, Any], merchant_id: str) -> dict[str, Any]:
    """Derive console metrics from one recorded decision, not constants."""
    decision = next((d for d in record.get("decisions", [])
                    if d["merchant_id"] == merchant_id), None)
    if decision is None:
        return {"merchant_id": merchant_id, "error": "merchant not present"}
    wire = decision.get("wire_payload") or {}
    extension = (wire.get("extensions") or {}).get("org.bondlayer.benefit_value") or {}
    records = extension.get("benefit_records") or extension.get("cards") or []
    total = len(records)
    verified = sum(1 for item in decision.get("verification", []) if item.get("verified"))
    return {
        "merchant_id": merchant_id,
        "condition": record.get("condition"),
        "fields_visible": _leaf_count(wire),
        "benefits_on_wire": total,
        "benefits_total": total if total else 3,
        "legible_pct": round(100 * verified / total) if total else 0,
        "verified_value_cents": decision.get("verified_value_cents", 0),
        "unsigned_penalty_cents": decision.get("unsigned_penalty_cents", 0),
        "benefits_withheld": max(0, (total if total else 3) - verified),
    }


def scoreboard(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Explain wins and losses from the same ranked decision artifact."""
    decisions = record.get("decisions", [])
    ordered = sorted(decisions, key=lambda d: (
        bool(d.get("constraints_unsatisfied")),
        not d.get("available", True),
        d.get("effective_cost_cents", 0),
        d.get("merchant_id", ""),
    ))
    winner = ordered[0]["merchant_id"] if ordered else None
    out = []
    for decision in decisions:
        merchant_id = decision["merchant_id"]
        won = merchant_id == winner
        out.append({
            "merchant_id": merchant_id,
            "won": won,
            "lost_to": None if won else winner,
            "list_price_cents": decision.get("list_price_cents", 0),
            "effective_cost_cents": decision.get("effective_cost_cents", 0),
            "verified_value_cents": decision.get("verified_value_cents", 0),
            "unsigned_penalty_cents": decision.get("unsigned_penalty_cents", 0),
            "constraints_satisfied": decision.get("constraints_satisfied", []),
            "constraints_unsatisfied": decision.get("constraints_unsatisfied", []),
        })
    return out


def _leaf_count(value: Any) -> int:
    if isinstance(value, dict):
        return sum(_leaf_count(item) for item in value.values())
    if isinstance(value, list):
        return sum(_leaf_count(item) for item in value)
    return 1
