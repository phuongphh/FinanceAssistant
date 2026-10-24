# Issue #582

[Story] P4.2.5-1.3: Auth dependency + logout endpoint

**Parent Epic:** #573 (Epic 1: Backend Foundation & Auth)

Reusable FastAPI dependency get_current_admin() cho moi admin endpoint.

- [ ] get_current_admin(): reject restricted=True
- [ ] get_current_admin_any(): bypass restricted
- [ ] GET /auth/me tra admin info
- [ ] POST /auth/logout add jti vao Redis blacklist
- [ ] Decode JWT -> 401 if invalid/expired

Close #573
