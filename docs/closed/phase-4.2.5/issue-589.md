# Issue #589

[Story] P4.2.5-3.1: User list endpoint voi search/filter/pagination

**Parent Epic:** #575 (Epic 3: User Management APIs)

GET /api/admin/users?search&tier&status&sort&limit&offset.

- [ ] Search: user_id, display_name, telegram_username (ILIKE)
- [ ] Sort: last_active_desc (default), cost_desc, joined_desc, messages_desc
- [ ] display_name luon masked initials
- [ ] last_active_human localize tieng Viet
- [ ] Filter: tier (4 levels), status (active/at_risk/dormant/new)

Close #575
