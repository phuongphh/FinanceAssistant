"""PII-safe property sanitization shared by analytics streams."""
from __future__ import annotations

import re
from typing import Any

_PII_KEY_PATTERN = re.compile(
    r"(?i)(phone|email|address|token|password|secret|message|content|"
    r"merchant_name|note|raw_text|body|text)"
)
_MAX_STR_VALUE_LEN = 200


def _is_json_friendly(value: Any) -> bool:
    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, (list, tuple)):
        return all(_is_json_friendly(v) for v in value)
    if isinstance(value, dict):
        return all(
            isinstance(k, str) and _is_json_friendly(v)
            for k, v in value.items()
        )
    return False


def sanitize_properties(props: dict[str, Any] | None) -> dict[str, Any]:
    """Strip PII keys and truncate long stringy values.

    Primitive, conservative — when in doubt, drop.
    """
    if not props:
        return {}
    out: dict[str, Any] = {}
    for key, value in props.items():
        if not isinstance(key, str):
            continue
        if _PII_KEY_PATTERN.search(key):
            continue
        if isinstance(value, str) and len(value) > _MAX_STR_VALUE_LEN:
            value = value[:_MAX_STR_VALUE_LEN]
        if not _is_json_friendly(value):
            continue
        out[key] = value
    return out
