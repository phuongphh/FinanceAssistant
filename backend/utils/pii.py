from __future__ import annotations


def mask_name(full_name: str | None) -> str:
    """Mask a Vietnamese display name to initials after the first token.

    Example: ``Nguyễn Văn An`` -> ``Nguyễn V. A.``. Empty values render as
    an em dash so admin screens never leak raw fallback identifiers as names.
    """
    if not full_name or not full_name.strip():
        return "—"
    parts = full_name.strip().split()
    if len(parts) == 1:
        return parts[0]
    return (
        parts[0] + " " + " ".join(f"{part[0].upper()}." for part in parts[1:] if part)
    )
