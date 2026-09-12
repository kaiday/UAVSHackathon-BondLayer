"""Canonical JSON serialization for deterministic signing.

Per ES256 signature requirements, JSON must be:
- Sorted keys
- No insignificant whitespace
- Integers for minor units (cents)
- UTF-8 encoding
- No trailing newline
"""

import json
from dataclasses import asdict
from typing import Any


def to_canonical_json(obj: Any) -> str:
    """Convert a Python object to canonical JSON string suitable for signing.

    Args:
        obj: Object to serialize (dict, dataclass, etc.)

    Returns:
        Canonical JSON string (sorted keys, compact, UTF-8, no trailing newline)
    """
    if hasattr(obj, "__dataclass_fields__"):
        data = asdict(obj)
    else:
        data = obj

    # Recursively convert all keys to strings and sort
    def normalize(o: Any) -> Any:
        if isinstance(o, dict):
            return {str(k): normalize(v) for k, v in sorted(o.items())}
        elif isinstance(o, (list, tuple)):
            return [normalize(v) for v in o]
        elif isinstance(o, float) and o == int(o):
            return int(o)
        else:
            return o

    normalized = normalize(data)

    # Use separators to remove all insignificant whitespace
    # sort_keys=True ensures deterministic output
    json_str = json.dumps(
        normalized,
        separators=(",", ":"),
        sort_keys=True,
        ensure_ascii=True,
        default=str,
    )

    return json_str


def from_canonical_json(json_str: str) -> dict:
    """Parse canonical JSON back to a dict.

    Args:
        json_str: Canonical JSON string

    Returns:
        Parsed dictionary
    """
    return json.loads(json_str)


def round_trip_test(obj: Any) -> tuple[str, Any]:
    """Test that an object round-trips through canonical JSON.

    Args:
        obj: Object to test

    Returns:
        Tuple of (canonical_json, parsed_object)
    """
    canonical = to_canonical_json(obj)
    parsed = from_canonical_json(canonical)
    return canonical, parsed
