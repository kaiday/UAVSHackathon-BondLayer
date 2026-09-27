"""Explicit offline drafts for the bundled fictional JB Hihi policy only."""

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from bondlayer.policy import PolicyDraft, PolicyError
from bondlayer.types import BenefitRecord, BenefitType


class DemoPolicyConverter:
    def __init__(self, issuer: str, merchant_name: str, policy_path: Path):
        self.issuer = issuer
        self.merchant_name = merchant_name
        self.policy_path = policy_path
        self.last_call = {"mode": "rules", "source": "bundled_demo_policy", "model": None}

    def drafts_for(self, merchant: str, document: str) -> list[PolicyDraft]:
        reference = self.policy_path.read_text(encoding="utf-8")
        if self.merchant_name.casefold() != "jb hihi" or document.strip() != reference.strip():
            raise PolicyError(
                "Offline policy upload supports only the unchanged bundled JB Hihi demo policy "
                "for JB Hihi. Other documents require OpenAI extraction."
            )
        definitions = [
            ("1. CHANGE-OF-MIND RETURNS", BenefitType.FREE_RETURNS, {"days": 30}, []),
            ("2. ADDITIONAL STORE WARRANTY", BenefitType.WARRANTY, {"months": 12}, []),
            ("3. DELIVERY", BenefitType.DELIVERY, {"minimum_order_aud": 99, "standard_fee_aud": 9.95}, ["order_over_99"]),
            ("4. REPAIR SUPPORT", BenefitType.REPAIRABILITY, {"assessment_years": 3}, []),
            ("5. LOYALTY POINTS", BenefitType.POINTS_EARN, {"points_per_dollar": 2, "cents_per_point": 1}, ["member"]),
            ("6. TRADE-IN", BenefitType.TRADE_IN_CREDIT, {"maximum_credit_aud": 200}, ["trade_in_device"]),
        ]
        drafts = []
        now = datetime.now(timezone.utc)
        for index, (heading, kind, facts, tokens) in enumerate(definitions):
            start = document.index(heading)
            next_heading = definitions[index + 1][0] if index + 1 < len(definitions) else "7. CONTACT"
            span = document[start:document.index(next_heading, start)].strip()
            identity = hashlib.sha256(f"{merchant}:{document}:{index}".encode()).hexdigest()[:20]
            record = BenefitRecord(
                record_id=f"{merchant}-{identity}", sku_id=None, benefit_type=kind,
                fact=facts, conditions=[*tokens, span], issuer=self.issuer,
                issued_at=now, expires_at=None, value_ceiling_aud=None, source_span=span,
            )
            drafts.append(PolicyDraft(record.record_id, merchant, record, heading, 1.0))
        return drafts
