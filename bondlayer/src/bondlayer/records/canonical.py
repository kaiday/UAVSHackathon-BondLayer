"""Canonical bytes for signed :class:`BenefitRecord` objects."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json
from typing import Any

from bondlayer.types import BenefitRecord, BenefitType


def _decimal_text(value: Decimal) -> str:
    """Return one representation for numerically equal Decimal values."""
    if not value.is_finite():
        raise ValueError("decimal values must be finite")
    if value == 0:
        return "0"
    # Do not normalize(): that rounds under the caller's Decimal context.
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _datetime_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime values must include a timezone")
    utc = value.astimezone(timezone.utc)
    return utc.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        # JSON has no decimal type. A string preserves money exactly.
        return _decimal_text(value)
    if isinstance(value, datetime):
        return _datetime_text(value)
    if isinstance(value, BenefitType):
        return value.value
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def canonical_record(record: BenefitRecord) -> bytes:
    """Serialize record fields in a stable, signature-safe JSON form.

    ``signature`` and ``key_id`` are deliberately absent: signatures are
    detached from the object they authenticate.
    """
    if not isinstance(record, BenefitRecord):
        raise ValueError("expected a BenefitRecord")
    if not all(isinstance(value, str) and value for value in (record.record_id, record.issuer)):
        raise ValueError("record_id and issuer must be nonempty strings")
    if record.sku_id is not None and (not isinstance(record.sku_id, str) or not record.sku_id):
        raise ValueError("sku_id must be a nonempty string or None")
    if not isinstance(record.benefit_type, BenefitType):
        raise ValueError("unknown benefit_type")
    if not isinstance(record.fact, dict) or any(
        not isinstance(key, str) or not isinstance(value, (str, int, float))
        for key, value in record.fact.items()
    ):
        raise ValueError("fact must map strings to scalar facts")
    if not isinstance(record.conditions, list) or any(not isinstance(item, str) for item in record.conditions):
        raise ValueError("conditions must be a list of strings")
    if record.source_span is not None and not isinstance(record.source_span, str):
        raise ValueError("source_span must be a string or None")
    if not isinstance(record.issued_at, datetime) or (
        record.expires_at is not None and not isinstance(record.expires_at, datetime)
    ):
        raise ValueError("record timestamps must be datetimes")
    _datetime_text(record.issued_at)
    if record.expires_at is not None:
        _datetime_text(record.expires_at)
        if record.expires_at <= record.issued_at:
            raise ValueError("expires_at must follow issued_at")
    ceiling = record.value_ceiling_aud
    if ceiling is not None and (
        not isinstance(ceiling, Decimal) or not ceiling.is_finite() or ceiling < 0
    ):
        raise ValueError("value_ceiling_aud must be a finite nonnegative Decimal or None")
    payload = {
        "record_id": record.record_id,
        "sku_id": record.sku_id,
        "benefit_type": record.benefit_type,
        "fact": record.fact,
        "conditions": record.conditions,
        "issuer": record.issuer,
        "issued_at": record.issued_at,
        "expires_at": record.expires_at,
        "value_ceiling_aud": record.value_ceiling_aud,
        "source_span": record.source_span,
    }
    try:
        return json.dumps(
            _json_value(payload),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"record cannot be canonically serialized: {exc}") from exc


# Short alias for callers that treat canonical JSON as the public operation.
canonical_json = canonical_record
