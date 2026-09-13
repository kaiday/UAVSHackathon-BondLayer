"""Merchant insights from observed comparisons, with no model or fabricated outcomes.

Capture evidence when a comparison happens. Aggregate that saved evidence later;
today's catalogue must never be used to invent the reason for an earlier result.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import re

from bondlayer.interpreter.resolver import interpret_hard

ATTRIBUTES = {
    "weight_kg": "weight", "ram_gb": "memory", "storage_gb": "storage",
    "screen_in": "screen size", "gpu": "graphics processor", "cpu": "processor",
}
TOPICS = (
    (r"return|send back", "Returns"), (r"warrant|cover", "Warranty"),
    (r"deliver|shipping", "Delivery"), (r"member|loyalty|points", "Membership and rewards"),
    (r"repair|fix it|spare parts", "Repairability"),
    (r"sustainab|carbon|ethical", "Sustainability and sourcing"),
    (r"light|portab|carry|\bkg\b", "Portability"),
)
BENEFIT_LABELS = {
    "free_returns": "Returns", "warranty": "Warranty", "delivery": "Delivery",
    "member_price": "Member pricing", "points_earn": "Loyalty points",
    "trade_in_credit": "Trade-in", "repairability": "Repairability",
    "durability": "Durability", "sustainability": "Sustainability",
    "ethical_sourcing": "Ethical sourcing",
}
STATE_LABELS = {
    "credited": "Credited", "unpriced": "Verified, no value",
    "eligibility_unknown": "Eligibility unknown", "ineligible": "Not eligible",
    "expired": "Expired", "unverified": "Unverified",
    "not_credited": "Verified, not credited",
}


def instant(value) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (ValueError, TypeError, AttributeError):
        return None


def positive(value) -> bool:
    try:
        amount = Decimal(str(value))
        return amount.is_finite() and amount > 0
    except InvalidOperation:
        return False


def _need(constraint) -> dict:
    return {"text": constraint.text, "kind": constraint.kind.value}


def capture_observation(run, merchant: str, snapshot: dict, order: dict) -> dict:
    """Additive evidence on an actual saved run, scoped to one merchant."""
    offers = [offer for offer in run.ranked if offer.merchant == merchant]
    best = offers[0] if offers else None
    products = snapshot.get("products", [])
    records = {
        entry["record"]["record_id"]: entry["record"]
        for block in snapshot.get("extensions", {}).get("org.bondlayer.benefit_value", [])
        for entry in block.get("records", []) if entry.get("record", {}).get("record_id")
    }
    requirements = [
        {**_need(rc.constraint), "satisfied": rc.satisfied,
         "attribute": rc.evidence_attribute, "record_id": rc.evidence_record_id, "note": rc.note}
        for rc in (best.resolved if best else [])
    ]
    answered = {r["text"] for r in requirements if r["satisfied"]}
    benefits = []
    gaps = []
    now = datetime.now(timezone.utc)
    for citation in best.citations if best else []:
        record = records.get(citation.get("record_id"), {})
        why = str(citation.get("why") or "")
        expires = instant(record.get("expires_at"))
        if expires is not None and expires <= now:
            state = "expired"
        elif not citation.get("cited"):
            state = "unverified"
        elif "conditions not attested" in why.lower() or "tier_not_attested" in why.lower():
            state = "eligibility_unknown"
        elif "tier_not_met" in why.lower():
            state = "ineligible"
        elif positive(citation.get("credited")):
            state = "credited"
        elif "no monetary ceiling" in why.lower():
            state = "unpriced"
        else:
            state = "not_credited"
        kind = citation.get("benefit_type", "unknown")
        label = BENEFIT_LABELS.get(kind, kind.replace("_", " ").capitalize())
        benefits.append({"record_id": citation.get("record_id"), "type": kind,
                         "label": label, "state": state, "reason": why})
        if state in {"expired", "unverified", "eligibility_unknown", "ineligible"}:
            gaps.append({"key": f"benefit:{state}:{kind}", "kind": state,
                         "title": f"{label}: {STATE_LABELS[state].lower()}",
                         "reason": why, "record_id": citation.get("record_id"),
                         "action": ("Check eligibility setup" if state == "eligibility_unknown"
                                    else "Check offer conditions" if state == "ineligible"
                                    else "Check published benefits"), "href": "/benefits/"})

    for constraint in run.constraints:
        text, kind = constraint.get("text", ""), constraint.get("kind", "")
        if text in answered:
            continue
        if kind in {"hard", "soft"}:
            for spec in interpret_hard(text):
                field = spec.attribute
                missing = [p["id"] for p in products if p.get("id") and
                           (p.get("attributes") or {}).get(field) in (None, "")]
                if field in ATTRIBUTES and missing:
                    gaps.append({"key": f"attribute:{field}", "kind": "missing_data",
                                 "title": f"Add product {ATTRIBUTES[field]}",
                                 "reason": f"{len(missing)} {'product' if len(missing) == 1 else 'products'} missing {ATTRIBUTES[field]} for “{text}”.",
                                 "sku_ids": missing, "need": text, "action": "Fix product data", "href": "/catalogue/"})
        elif kind in {"service", "values"} and best and run.extension_enabled:
            # Absence of evidence is not a claim that the business lacks the benefit.
            topic = next((label for pattern, label in TOPICS if re.search(pattern, text, re.I)), "Service benefits")
            gaps.append({"key": f"evidence:{topic}", "kind": "missing_evidence",
                         "title": f"Publish your {topic.lower()} policy",
                         "reason": f"No evidence for “{text}”.",
                         "need": text, "action": "Add policy", "href": "/benefits/"})
    if not offers and snapshot:
        gaps.append({"key": "no_offer", "kind": "no_offer", "title": "No matching offer",
                     "reason": "Your store returned no offer for this request.",
                     "action": "Check catalogue", "href": "/catalogue/"})

    own_checkout = order if order.get("merchant") == merchant else {}
    receipt = own_checkout.get("order") or {}
    confirmed = receipt.get("status") in {"confirmed", "confirmed_awaiting_payment"}
    return {
        "version": 1, "offers_returned": len(offers),
        "selected": None if run.winner is None else run.winner.merchant == merchant,
        "requirements": requirements, "benefits": benefits, "gaps": gaps,
        "product": {"sku_id": best.sku_id, "title": best.title, "price": str(best.shelf_price)} if best else None,
        "checkout": {"status": "confirmed" if confirmed else "not_confirmed" if own_checkout else "unknown",
                     "order_id": receipt.get("order_id") if confirmed else None,
                     "payment_status": (receipt.get("payment") or {}).get("status") if confirmed else None},
    }


def _demand(constraints: list[dict]) -> set[tuple[str, str]]:
    found = set()
    for c in constraints:
        text = str(c.get("text", ""))
        if c.get("kind") == "hard":
            specs = interpret_hard(text)
            for spec in specs:
                if spec.kind == "category":
                    found.add(("categories", str(spec.value).capitalize()))
                elif spec.kind == "price" and spec.value.is_finite():
                    found.add(("budgets", f"Budget ceiling: ${spec.value:,.2f} AUD"))
            if any(s.kind not in {"category", "price"} for s in specs):
                found.add(("needs", text))
        if c.get("kind") in {"service", "values", "soft"}:
            topic = next((label for pattern, label in TOPICS if re.search(pattern, text, re.I)), text)
            if topic:
                found.add(("needs", topic))
    return found


def _legacy_checkout(report: dict, merchant: str) -> dict:
    order = report.get("order") or {}
    receipt = order.get("order") or {}
    if order.get("merchant") == merchant and receipt.get("status") in {"confirmed", "confirmed_awaiting_payment"}:
        return {"status": "confirmed", "order_id": receipt.get("order_id"),
                "payment_status": (receipt.get("payment") or {}).get("status")}
    return {"status": "unknown", "order_id": None, "payment_status": None}


def build_insights(reports: dict[str, dict], merchant: str, *, days: int = 30,
                   mode: str = "enabled", now: datetime | None = None) -> dict:
    """Use live, dated, merchant-specific reports only; fixture scenarios never count."""
    current = now or datetime.now(timezone.utc)
    since = current - timedelta(days=days) if days else None
    eligible = []
    skipped_dates = 0
    for report in reports.values():
        if report.get("source") != "live":
            continue
        row = next((r for r in report.get("merchants", []) if r.get("merchant") == merchant), None)
        if row is None:
            continue
        enabled = report.get("extension_enabled")
        if mode != "all" and enabled is not (mode == "enabled"):
            continue
        at = instant(report.get("created_at"))
        if at is None or at > current:
            skipped_dates += 1
            continue
        if since is not None and at < since:
            continue
        if not isinstance(report.get("request_id"), str):
            continue
        eligible.append((at, report, row))
    eligible.sort(key=lambda item: (item[0], item[1]["request_id"]), reverse=True)

    metrics = {"requests": 0, "with_offers": 0, "unanswered": 0, "checkout_confirmations": 0,
               "selected": 0, "selection_known": 0, "detailed_reports": 0}
    demand = defaultdict(set)
    opportunities = {}
    benefit_counts = defaultdict(set)
    recent = []
    seen = set()
    for at, report, row in eligible:
        rid = report["request_id"]
        if rid in seen:
            continue
        seen.add(rid)
        observation = row.get("observation") or {}
        detailed = observation.get("version") == 1
        has_offer = bool(row.get("sku_id"))
        selected = observation.get("selected") if detailed else (
            row.get("won") if row.get("won") is True or any(r.get("won") is True for r in report.get("merchants", [])) else None
        )
        checkout = observation.get("checkout") if detailed else _legacy_checkout(report, merchant)
        checkout = checkout or {"status": "unknown"}
        unanswered = list(row.get("unsatisfied") or [])
        metrics["requests"] += 1
        metrics["with_offers"] += has_offer
        metrics["unanswered"] += bool(unanswered)
        metrics["detailed_reports"] += detailed
        metrics["selection_known"] += selected is not None
        metrics["selected"] += selected is True
        metrics["checkout_confirmations"] += checkout.get("status") == "confirmed"
        for group, label in _demand(report.get("constraints", [])):
            demand[(group, label)].add(rid)

        gaps = observation.get("gaps", []) if detailed else []
        if not detailed and unanswered:
            gaps = [{"key": "legacy_unanswered", "kind": "unknown",
                     "title": "Unanswered needs",
                     "reason": "Older report; cause not saved.",
                     "action": "Check catalogue", "href": "/catalogue/"}]
        for gap in gaps:
            key = gap.get("key")
            if not key:
                continue
            item = opportunities.setdefault(key, {"id": key, "kind": gap["kind"], "title": gap["title"],
                "action": gap["action"], "href": gap["href"], "request_ids": [], "examples": []})
            if rid not in item["request_ids"]:
                item["request_ids"].append(rid)
                item["examples"].append({"request_id": rid, "reason": gap["reason"]})
        benefits = observation.get("benefits", []) if detailed else []
        for benefit in benefits:
            benefit_counts[(benefit["label"], benefit["state"])].add(rid)
        outcome = ("Checkout confirmed" if checkout.get("status") == "confirmed" else
                   "Offer selected by agent" if selected is True else
                   "Another offer selected by agent" if selected is False else "Outcome unknown")
        recent.append({
            "request_id": rid, "created_at": at.isoformat(), "question": report.get("utterance", ""),
            "has_offer": has_offer, "outcome": outcome, "selected": selected,
            "unanswered": unanswered, "requirements": observation.get("requirements", []) if detailed else [],
            "benefits": benefits, "gaps": gaps, "checkout": checkout,
            "product": observation.get("product") if detailed else (
                {"sku_id": row["sku_id"], "title": None, "price": row.get("shelf_price")} if has_offer else None),
            "technical": {"request_id": rid, "evidence_version": observation.get("version"),
                          "benefits_enabled": report.get("extension_enabled")},
        })
    ranked_opportunities = sorted(opportunities.values(), key=lambda o: (-len(o["request_ids"]), o["id"]))
    for item in ranked_opportunities:
        item["requests"] = len(item["request_ids"])
    return {
        "merchant": merchant, "period": {"days": days, "since": since.isoformat() if since else None,
                                           "until": current.isoformat(), "mode": mode},
        "metrics": metrics,
        "demand": {group: sorted([
            {"label": label, "requests": len(ids), "request_ids": sorted(ids)}
            for (category, label), ids in demand.items() if category == group
        ], key=lambda item: (-item["requests"], item["label"])) for group in ("categories", "budgets", "needs")},
        "opportunities": ranked_opportunities,
        "benefits": [{"label": label, "state": state, "state_label": STATE_LABELS.get(state, state),
                      "requests": len(ids), "request_ids": sorted(ids)}
                     for (label, state), ids in sorted(benefit_counts.items())],
        "recent": recent,
        "coverage": {"source": "Buyer-agent comparisons", "retained_report_limit": 500,
                     "excluded_undated_or_future": skipped_dates,
                     "note": "Counts are agent comparison runs, not shoppers or sales."},
    }
