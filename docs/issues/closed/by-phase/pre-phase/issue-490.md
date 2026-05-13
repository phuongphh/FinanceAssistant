# Issue #490

[Story] P4.1-C1: Acquisition source + invite tracking

**Parent Epic:** #480 (Epic C: Soft Launch Playbook)

Generate 50 unique invite links voi metadata source, track user acquisition.

- [ ] Table invite_codes (token, source, batch_name, used_by_user_id)
- [ ] Script generate --source <name> --count <n>
- [ ] start_handler parse ?start=invite_<token>
- [ ] Operator /cohort_stats hien breakdown theo source

Close #480
