# Issue #581

[Story] P4.2.5-1.2: Login endpoint + force password change flow

**Parent Epic:** #573 (Epic 1: Backend Foundation & Auth)

POST /api/admin/auth/login + POST /auth/change-password. JWT HS256, 1h expiry.

- [ ] POST /auth/login: email+password -> JWT token
- [ ] Rate limit: 5 attempts/15ph/IP -> 429
- [ ] force_password_change=True -> restricted JWT, chi cho phep /change-password + /me
- [ ] POST /auth/change-password: validate min 12 chars, co chu+so
- [ ] Update last_login_at

Close #573
