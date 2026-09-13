"""Offline policy-document onboarding with a human approval gate."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import Enum
from io import BytesIO
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from bondlayer.types import BenefitRecord, BenefitType, SignedRecord, Signer


VALUE_TYPES = {
    BenefitType.SUSTAINABILITY,
    BenefitType.ETHICAL_SOURCING,
    BenefitType.DURABILITY,
    BenefitType.REPAIRABILITY,
}
SUPPORTED_EXTENSIONS = {".md", ".txt", ".pdf"}


class DraftStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True)
class PolicyDocument:
    merchant: str
    filename: str
    raw_path: Path
    text: str
    sha256: str


@dataclass(frozen=True)
class PolicyDraft:
    draft_id: str
    merchant: str
    record: BenefitRecord
    section: str
    confidence: float
    status: DraftStatus = DraftStatus.PENDING
    edited: bool = False
    decision_note: str | None = None
    signed: SignedRecord | None = None


@dataclass(frozen=True)
class PolicyReport:
    merchant: str
    document_sha256: str
    records_drafted: int
    drafted_by_type: dict[str, int]
    confidence_by_type: dict[str, float]
    sections_without_drafts: list[str]
    pending: int
    approved: int
    rejected: int


@dataclass(frozen=True)
class PolicyMetrics:
    extraction_precision: float
    drafts_approved_unedited_share: float


class PolicyError(ValueError):
    pass


class PolicyStore:
    """Raw-file and approval-decision persistence for the seeded demo."""

    def __init__(self, root: Path):
        self.root = root
        self.raw_root = root / "raw"
        self.raw_root.mkdir(parents=True, exist_ok=True)
        self.database = root / "policy_onboarding.sqlite3"
        self._initialise()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.database)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialise(self) -> None:
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS documents (merchant TEXT PRIMARY KEY, filename TEXT NOT NULL, raw_path TEXT NOT NULL, sha256 TEXT NOT NULL, text TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS drafts (draft_id TEXT PRIMARY KEY, merchant TEXT NOT NULL, payload TEXT NOT NULL)"
            )

    def store_document(self, merchant: str, filename: str, raw: bytes, text: str) -> PolicyDocument:
        digest = hashlib.sha256(raw).hexdigest()
        merchant_directory = self.raw_root / merchant
        merchant_directory.mkdir(parents=True, exist_ok=True)
        raw_path = merchant_directory / f"{digest}{Path(filename).suffix.lower()}"
        raw_path.write_bytes(raw)
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO documents VALUES (?, ?, ?, ?, ?)",
                (merchant, filename, str(raw_path), digest, text),
            )
        return PolicyDocument(merchant, filename, raw_path, text, digest)

    def get_document(self, merchant: str) -> PolicyDocument:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT filename, raw_path, sha256, text FROM documents WHERE merchant = ?", (merchant,)
            ).fetchone()
        if row is None:
            raise PolicyError(f"No policy document stored for {merchant!r}")
        return PolicyDocument(merchant, row[0], Path(row[1]), row[3], row[2])

    def save_drafts(self, drafts: list[PolicyDraft]) -> None:
        with self._connect() as connection:
            connection.executemany(
                "INSERT OR REPLACE INTO drafts VALUES (?, ?, ?)",
                [(draft.draft_id, draft.merchant, json.dumps(_draft_payload(draft))) for draft in drafts],
            )

    def replace_drafts(self, merchant: str, drafts: list[PolicyDraft]) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM drafts WHERE merchant = ?", (merchant,))
            connection.executemany(
                "INSERT INTO drafts VALUES (?, ?, ?)",
                [(draft.draft_id, draft.merchant, json.dumps(_draft_payload(draft))) for draft in drafts],
            )

    def get_draft(self, draft_id: str) -> PolicyDraft:
        with self._connect() as connection:
            row = connection.execute("SELECT payload FROM drafts WHERE draft_id = ?", (draft_id,)).fetchone()
        if row is None:
            raise PolicyError(f"Unknown policy draft {draft_id!r}")
        return _draft_from_payload(json.loads(row[0]))

    def drafts_for(self, merchant: str) -> list[PolicyDraft]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM drafts WHERE merchant = ? ORDER BY draft_id", (merchant,)
            ).fetchall()
        return [_draft_from_payload(json.loads(row[0])) for row in rows]

    def save_draft(self, draft: PolicyDraft) -> None:
        self.save_drafts([draft])


class CachedPolicyConverter:
    """Reads committed model-output fixtures so policy conversion is offline."""

    def __init__(self, fixture_path: Path):
        self.fixture_path = fixture_path

    def draft(self, document: str) -> list[BenefitRecord]:
        fixture = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        return [
            record
            for merchant in fixture["merchants"]
            for record in (
                _record_from_payload(candidate["record"])
                for candidate in fixture["merchants"][merchant]
            )
            if record.source_span and record.source_span in document
            and (record.benefit_type not in VALUE_TYPES or record.value_ceiling_aud is None)
        ]

    def drafts_for(self, merchant: str, document: str) -> list[PolicyDraft]:
        fixture = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        candidates = fixture["merchants"].get(merchant, [])
        drafts: list[PolicyDraft] = []
        for candidate in candidates:
            record = _record_from_payload(candidate["record"])
            if not record.source_span or record.source_span not in document:
                continue
            if record.benefit_type in VALUE_TYPES and record.value_ceiling_aud is not None:
                continue
            drafts.append(
                PolicyDraft(
                    draft_id=candidate["draft_id"],
                    merchant=merchant,
                    record=record,
                    section=_section_for_span(document, record.source_span),
                    confidence=float(candidate["confidence"]),
                )
            )
        return drafts


class PolicyIngestor:
    def __init__(self, store: PolicyStore):
        self.store = store

    def ingest(self, merchant: str, filename: str, content: bytes | str) -> PolicyDocument:
        extension = Path(filename).suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            raise PolicyError("Policy files must be .md, .txt, or .pdf")
        raw = content.encode("utf-8") if isinstance(content, str) else content
        if extension == ".pdf":
            text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(raw)).pages)
        else:
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError as error:
                raise PolicyError("Text policy files must be UTF-8") from error
        if not text.strip():
            raise PolicyError("Policy document contains no extractable text")
        return self.store.store_document(merchant, filename, raw, text)


class PolicyOnboardingService:
    def __init__(self, store: PolicyStore, converter: CachedPolicyConverter, signer: Signer):
        self.store = store
        self.ingestor = PolicyIngestor(store)
        self.converter = converter
        self.signer = signer

    def ingest_and_draft(self, merchant: str, filename: str, content: bytes | str) -> PolicyReport:
        document = self.ingestor.ingest(merchant, filename, content)
        self.store.replace_drafts(merchant, self.converter.drafts_for(merchant, document.text))
        return self.report(merchant)

    def report(self, merchant: str) -> PolicyReport:
        document = self.store.get_document(merchant)
        drafts = self.store.drafts_for(merchant)
        types = sorted({draft.record.benefit_type.value for draft in drafts})
        drafted_by_type = {kind: sum(draft.record.benefit_type.value == kind for draft in drafts) for kind in types}
        confidence_by_type = {
            kind: round(sum(draft.confidence for draft in drafts if draft.record.benefit_type.value == kind) / drafted_by_type[kind], 3)
            for kind in types
        }
        produced_sections = {draft.section for draft in drafts}
        return PolicyReport(
            merchant=merchant,
            document_sha256=document.sha256,
            records_drafted=len(drafts),
            drafted_by_type=drafted_by_type,
            confidence_by_type=confidence_by_type,
            sections_without_drafts=[section for section in _sections(document.text) if section not in produced_sections],
            pending=sum(draft.status is DraftStatus.PENDING for draft in drafts),
            approved=sum(draft.status is DraftStatus.APPROVED for draft in drafts),
            rejected=sum(draft.status is DraftStatus.REJECTED for draft in drafts),
        )

    def edit(self, draft_id: str, *, fact: dict[str, str | int | float] | None = None,
             conditions: list[str] | None = None, value_ceiling_aud: Decimal | None = None) -> PolicyDraft:
        draft = self.store.get_draft(draft_id)
        if draft.status is not DraftStatus.PENDING:
            raise PolicyError("Only pending drafts can be edited")
        record = replace(
            draft.record,
            fact=fact if fact is not None else draft.record.fact,
            conditions=conditions if conditions is not None else draft.record.conditions,
            value_ceiling_aud=(
                None if draft.record.benefit_type in VALUE_TYPES
                else value_ceiling_aud if value_ceiling_aud is not None else draft.record.value_ceiling_aud
            ),
        )
        edited = replace(draft, record=record, edited=True)
        self.store.save_draft(edited)
        return edited

    def approve(self, draft_id: str, note: str | None = None) -> PolicyDraft:
        draft = self.store.get_draft(draft_id)
        if draft.status is not DraftStatus.PENDING:
            raise PolicyError("Only pending drafts can be approved")
        document = self.store.get_document(draft.merchant)
        if not draft.record.source_span or draft.record.source_span not in document.text:
            raise PolicyError("Draft has no verbatim source span in its stored document")
        approved = replace(
            draft,
            status=DraftStatus.APPROVED,
            decision_note=note,
            signed=self.signer.sign(draft.record),
        )
        self.store.save_draft(approved)
        return approved

    def reject(self, draft_id: str, note: str | None = None) -> PolicyDraft:
        draft = self.store.get_draft(draft_id)
        if draft.status is not DraftStatus.PENDING:
            raise PolicyError("Only pending drafts can be rejected")
        rejected = replace(draft, status=DraftStatus.REJECTED, decision_note=note)
        self.store.save_draft(rejected)
        return rejected

    def publish(self, merchant: str) -> list[SignedRecord]:
        return [
            draft.signed
            for draft in self.store.drafts_for(merchant)
            if draft.status is DraftStatus.APPROVED and draft.signed is not None
        ]

    def metrics(self, merchant: str, expected: list[dict[str, Any]]) -> PolicyMetrics:
        drafts = self.store.drafts_for(merchant)
        expected_keys = {
            (item["benefit_type"], json.dumps(item["fact"], sort_keys=True)) for item in expected
        }
        correct = sum(
            (draft.record.benefit_type.value, json.dumps(draft.record.fact, sort_keys=True)) in expected_keys
            for draft in drafts
        )
        approved = [draft for draft in drafts if draft.status is DraftStatus.APPROVED]
        return PolicyMetrics(
            round(correct / len(drafts), 3) if drafts else 0.0,
            round(sum(not draft.edited for draft in approved) / len(approved), 3) if approved else 0.0,
        )


def _sections(document: str) -> list[str]:
    return [line[3:].strip() for line in document.splitlines() if line.startswith("## ")]


def _section_for_span(document: str, source_span: str) -> str:
    position = document.index(source_span)
    headings: list[tuple[int, str]] = []
    offset = 0
    for line in document.splitlines(keepends=True):
        if line.startswith("## "):
            headings.append((offset, line[3:].strip()))
        offset += len(line)
    return next((heading for offset, heading in reversed(headings) if offset <= position), "Introduction")


def _record_payload(record: BenefitRecord) -> dict[str, Any]:
    return {
        "record_id": record.record_id,
        "sku_id": record.sku_id,
        "benefit_type": record.benefit_type.value,
        "fact": record.fact,
        "conditions": record.conditions,
        "issuer": record.issuer,
        "issued_at": record.issued_at.isoformat(),
        "expires_at": record.expires_at.isoformat() if record.expires_at else None,
        "value_ceiling_aud": str(record.value_ceiling_aud) if record.value_ceiling_aud is not None else None,
        "source_span": record.source_span,
    }


def _record_from_payload(payload: dict[str, Any]) -> BenefitRecord:
    return BenefitRecord(
        record_id=payload["record_id"],
        sku_id=payload.get("sku_id"),
        benefit_type=BenefitType(payload["benefit_type"]),
        fact=payload["fact"],
        conditions=payload.get("conditions", []),
        issuer=payload["issuer"],
        issued_at=datetime.fromisoformat(payload.get("issued_at", "2026-09-12T00:00:00+00:00")),
        expires_at=datetime.fromisoformat(payload["expires_at"]) if payload.get("expires_at") else None,
        value_ceiling_aud=Decimal(str(payload["value_ceiling_aud"])) if payload.get("value_ceiling_aud") is not None else None,
        source_span=payload.get("source_span"),
    )


def _draft_payload(draft: PolicyDraft) -> dict[str, Any]:
    return {
        "draft_id": draft.draft_id,
        "merchant": draft.merchant,
        "record": _record_payload(draft.record),
        "section": draft.section,
        "confidence": draft.confidence,
        "status": draft.status.value,
        "edited": draft.edited,
        "decision_note": draft.decision_note,
        "signed": (
            {
                "record": _record_payload(draft.signed.record),
                "signature": draft.signed.signature,
                "key_id": draft.signed.key_id,
            }
            if draft.signed else None
        ),
    }


def _draft_from_payload(payload: dict[str, Any]) -> PolicyDraft:
    signed_payload = payload.get("signed")
    signed = (
        SignedRecord(
            record=_record_from_payload(signed_payload["record"]),
            signature=signed_payload["signature"],
            key_id=signed_payload["key_id"],
        )
        if signed_payload else None
    )
    return PolicyDraft(
        draft_id=payload["draft_id"],
        merchant=payload["merchant"],
        record=_record_from_payload(payload["record"]),
        section=payload["section"],
        confidence=float(payload["confidence"]),
        status=DraftStatus(payload["status"]),
        edited=bool(payload["edited"]),
        decision_note=payload.get("decision_note"),
        signed=signed,
    )
