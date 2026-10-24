# Issue #629

[Bug] US5: Briefing "Đổi giờ" button not working

**Parent Epic:** #624 (Enhance UI/UX 4)

Button "Doi gio" trong briefing report khong work. Can fix de no hoat dong giong nhu "Cai thong bao" trong menu Profile.

## Van de
- Click "Doi gio" trong briefing -> khong co phan hoi / khong hien setting
- Trong menu Profile, "Cai thong bao" hoat dong tot (cho chon gio)

## Yeu cau
- [ ] Investigate root cause: callback handler missing / wrong routing / missing state
- [ ] Fix de button "Doi gio" work — reuse briefing time setting tu Profile
- [ ] Neu co the, redirect ve cung flow "Cai thong bao" trong Profile
- [ ] Test: click Doi gio -> chon gio -> briefing update gio moi

Close #624
