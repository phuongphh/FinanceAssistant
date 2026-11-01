# Issue #542

[Story] P4.2-1.1: Trust & Privacy Moment

**Parent Epic:** #539 (Epic 1: Trust & Data Integrity)

Insert trust card giua Step 1 (goal) va Step 2 (asset input). User phai bam OK hoac hoi cau hoi truoc khi nhap tai san.

- [ ] Trust card hien giua Step 1 va Step 2 khi trust_accepted_at IS NULL
- [ ] 3 bullet privacy + 2 buttons: OK tiep tuc / Toi co cau hoi
- [ ] OK -> trust_accepted_at=NOW(), advance to first_asset
- [ ] Co cau hoi -> feedback record priority=high, chi 1 lan
- [ ] Chi hien 1 lan per user
- [ ] Feature flag TRUST_CARD_ENABLED
- [ ] Strings trong content/onboarding/trust_card.yaml

Close #539
