"""Rank one evaluation request by effective cost, and show the working.

    python scripts/effective_cost_report.py          # R21, the tie-break
    python scripts/effective_cost_report.py R01 R12

Every figure the pitch quotes about money should come from here, so that anyone
who disagrees with a number can re-run the command that produced it. Nothing is
generated: it reads the frozen catalogue, the frozen evaluation set and the
published records, verifies each signature against the **public** key only, and
does Decimal arithmetic. No model call, no network, no private key.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bondlayer.records.serialise import load_signed  # noqa: E402
from bondlayer.records.signing import ES256Signer  # noqa: E402
from bondlayer.types import EffectiveCost, Sku  # noqa: E402
from bondlayer.valuation import (  # noqa: E402
    ATTESTED_CONDITIONS,
    MERCHANT_DOMAINS,
    REFERENCE_SHOPPER_POLICY,
    DeterministicValuation,
)

ROOT = Path(__file__).resolve().parents[1]


def catalog() -> dict[str, Sku]:
    with (ROOT / "data" / "catalog" / "electronics.csv").open(
        encoding="utf-8", newline="",
    ) as handle:
        return {
            row["sku"]: Sku(
                row["sku"], row["title"], row["category"],
                Decimal(re.sub(r"[^0-9.]", "", row["price"])),
                {"merchant": row["merchant"]},
            )
            for row in csv.DictReader(handle)
        }


def verifiers() -> dict[str, ES256Signer]:
    """Built from ``keys/<merchant>.pub.json`` -- what any agent can do."""
    built = {}
    for merchant, domain in MERCHANT_DOMAINS.items():
        path = ROOT / "keys" / f"{merchant}.pub.json"
        if path.exists():
            jwk, = json.loads(path.read_text(encoding="utf-8"))
            built[merchant] = ES256Signer.from_jwk(jwk, issuer=domain)
    return built


def main(request_ids: list[str]) -> None:
    skus = catalog()
    checkers = verifiers()
    published = {
        merchant: load_signed(ROOT / "data" / "records" / f"{merchant}.signed.json")
        for merchant in MERCHANT_DOMAINS
    }
    requests = {
        item["id"]: item
        for item in json.loads(
            (ROOT / "data" / "eval" / "requests.json").read_text(encoding="utf-8"),
        )["requests"]
    }

    def cost(sku: Sku) -> EffectiveCost:
        merchant = sku.attributes["merchant"]
        if merchant not in checkers:
            # The control. Nothing published, so nothing to verify or credit --
            # it pays its shelf price, which is the status quo.
            return EffectiveCost(sku.sku_id, sku.shelf_price, [], sku.shelf_price)
        valuation = DeterministicValuation(
            checkers[merchant], merchant_domains=MERCHANT_DOMAINS,
            satisfied_conditions=ATTESTED_CONDITIONS,
        )
        return valuation.effective_cost(sku, published[merchant], REFERENCE_SHOPPER_POLICY)

    for request_id in request_ids:
        request = requests[request_id]
        print(f"\n{request_id}  {request['utterance']}")
        ranked = sorted(
            (cost(skus[sku_id]) for sku_id in request["gold_skus"]),
            key=lambda item: (item.effective_cost, item.sku_id),
        )
        print(f"  {'sku':<11}{'merchant':<13}{'shelf':>10}{'credited':>10}{'effective':>11}")
        for item in ranked:
            merchant = skus[item.sku_id].attributes["merchant"]
            print(
                f"  {item.sku_id:<11}{merchant:<13}{item.shelf_price:>10}"
                f"{item.total_credited:>10}{item.effective_cost:>11}"
            )

        winner = ranked[0]
        cheapest = min(ranked, key=lambda item: (item.shelf_price, item.sku_id))
        if winner.sku_id != cheapest.sku_id:
            gap = winner.shelf_price - cheapest.shelf_price
            print(
                f"  -> {winner.sku_id} wins at ${winner.effective_cost} effective, "
                f"${gap} dearer on the shelf than {cheapest.sku_id} "
                f"(${cheapest.shelf_price}) and ${cheapest.effective_cost - winner.effective_cost} "
                "cheaper to actually own"
            )
        else:
            print(f"  -> {winner.sku_id} wins on shelf price; no flip in this request")

        print("\n  Why, line by line:")
        for line in winner.credited:
            print(f"    {line.record_id:<34}{str(line.credited_aud):>8}  {line.reason}")


if __name__ == "__main__":
    main(sys.argv[1:] or ["R21"])
