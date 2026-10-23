# Issue #475

[Story] P4.1-C1: Acquisition source + invite tracking

**Parent Epic:** #465 (Epic C: Soft Launch Playbook)

## Description
Generate 50 unique invite links voi metadata source, track user acquisition.

## Acceptance Criteria
- [ ] Table invite_codes (token PK, source, batch_name, used_by_user_id, timestamps)
- [ ] Script generate --source <name> --count <n> -> CSV
- [ ] start_handler parse ?start=invite_<token>, fill users.acquisition_source
- [ ] Operator command /cohort_stats hien breakdown theo source
- [ ] Sources: friends, personal_fb, vn_finance_community, direct_msg

## Estimate: ~1 day
## Dependencies: None

Close #465
