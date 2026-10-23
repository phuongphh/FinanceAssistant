# Issue #580

[Story] P4.2.5-1.1: Admin user data model + migration + seed

**Parent Epic:** #573 (Epic 1: Backend Foundation & Auth)

Migration tao bang admin_users, seed script, bcrypt hash, Pydantic schemas.

- [ ] Migration: bang admin_users (id, email unique, password_hash, full_name, role, is_active, force_password_change, last_login_at, timestamps)
- [ ] Seed script: tao admin phuongphh@nuitruc.ai, password tu env, force_password_change=True
- [ ] Password hash bang bcrypt cost 12
- [ ] AdminUserOut KHONG expose password_hash
- [ ] Idempotent seed

Close #573
