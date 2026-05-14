from __future__ import annotations

import re


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


def mask_email(email: str | None) -> str:
    """Mask email while keeping enough shape for support disambiguation.

    Example: ``phuongphh@nuitruc.ai`` -> ``p********h@nuitruc.ai``.
    Invalid/empty values render as an em dash instead of echoing raw input.
    """
    if not email or "@" not in email:
        return "—"
    local, domain = email.strip().split("@", 1)
    if not local or not domain:
        return "—"
    if len(local) == 1:
        return f"{local[0]}***@{domain}"
    if len(local) == 2:
        return f"{local[0]}***{local[-1]}@{domain}"
    return f"{local[0]}{'*' * (len(local) - 1)}{local[-1]}@{domain}"


def mask_phone(phone: str | None) -> str:
    """Mask a phone number to first 3 and last 3 digits.

    Example: ``0987654321`` -> ``098****321``. Short/empty values are
    intentionally non-identifying.
    """
    if not phone:
        return "—"
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 7:
        return "***"
    return f"{digits[:3]}{'*' * (len(digits) - 6)}{digits[-3:]}"
