from __future__ import annotations

import asyncio
import os

from sqlalchemy import select

from backend.database import get_session_factory
from backend.models.admin_user import AdminUser
from backend.utils.admin_security import hash_password

DEFAULT_ADMIN_EMAIL = "phuongphh@nuitruc.ai"
DEFAULT_ADMIN_PASSWORD = "admin"


async def seed() -> None:
    email = os.getenv("INITIAL_ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL).strip().lower()
    password = os.getenv("INITIAL_ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD)
    session_factory = get_session_factory()

    async with session_factory() as db:
        result = await db.execute(select(AdminUser).where(AdminUser.email == email))
        existing = result.scalar_one_or_none()
        if existing:
            print(f"✓ Admin {email} already exists, skip seed")
            return

        admin = AdminUser(
            email=email,
            password_hash=hash_password(password),
            full_name="Phuong",
            role="super_admin",
            force_password_change=True,
            is_active=True,
        )
        db.add(admin)
        await db.commit()
        print(f"✓ Seeded admin: {email} (must change password on first login)")


if __name__ == "__main__":
    asyncio.run(seed())
