# Issues — Index & Navigation

Lưu trữ chi tiết các GitHub issues của Bé Tiền theo phase. Mỗi file `issue-<number>.md` là snapshot nội dung của 1 issue (user story, acceptance criteria, kết quả review).

---

## 🗂️ Folder Structure

```
docs/issues/
├── README.md                    ← You are here (Quick Stats tự sinh)
├── active/
│   ├── INDEX.md                 ← Auto-generated list of open issues
│   └── issue-<N>.md             ← One file per open issue
└── closed/
    ├── INDEX.md                 ← Auto-generated: issue# → phase → title
    └── by-phase/
        ├── phase-1/             ← Phase 1: UX Foundation
        ├── phase-3a/            ← Phase 3A: Wealth Foundation
        ├── phase-4.5/           ← Phase 4.5: Decision Engine Foundation
        ├── …                    ← Mỗi phase 1 folder, tạo khi có issue đầu tiên
        └── unphased/            ← Bug/story lẻ không xác định được phase
```

> **Tự động hoá:** `.github/workflows/issue-lifecycle.yml` chạy script
> `.github/scripts/issue-lifecycle.js` khi:
> - có issue event (`opened`, `edited`, `closed`, `reopened`, `labeled`, `unlabeled`);
> - hằng đêm lúc 02:17 giờ VN (cron, lưới an toàn bắt các event bị lỡ);
> - chạy tay qua **Actions → Issue Lifecycle Sync → Run workflow**.
>
> Mỗi lần chạy, script **reconcile toàn bộ**: lấy mọi issue từ GitHub API,
> đặt issue đang mở vào `active/`, issue đã đóng vào `closed/by-phase/<phase>/`,
> xoá file của issue không còn tồn tại, rồi sinh lại cả hai `INDEX.md` và bảng
> Quick Stats bên dưới. Script idempotent — chạy nhiều lần không sinh thay đổi thừa.
>
> Chạy local: `GH_TOKEN=... GITHUB_REPOSITORY=phuongphh/FinanceAssistant node .github/scripts/issue-lifecycle.js`
> (hoặc `--from-json issues.json` với file JSON xuất từ API).

---

## 📊 Quick Stats

<!-- STATS:START -->
_Bảng này do `.github/scripts/issue-lifecycle.js` tự sinh — đừng sửa tay._

| Phase | Closed Issues | Folder |
|-------|---------------|--------|
| Phase 1 | 7 | [`closed/by-phase/phase-1/`](closed/by-phase/phase-1/) |
| Phase 2 | 9 | [`closed/by-phase/phase-2/`](closed/by-phase/phase-2/) |
| Phase 3A | 31 | [`closed/by-phase/phase-3a/`](closed/by-phase/phase-3a/) |
| Phase 3.5 | 27 | [`closed/by-phase/phase-3.5/`](closed/by-phase/phase-3.5/) |
| Phase 3.6 | 16 | [`closed/by-phase/phase-3.6/`](closed/by-phase/phase-3.6/) |
| Phase 3.7 | 16 | [`closed/by-phase/phase-3.7/`](closed/by-phase/phase-3.7/) |
| Phase 3.8 | 19 | [`closed/by-phase/phase-3.8/`](closed/by-phase/phase-3.8/) |
| Phase 3.8.5 | 11 | [`closed/by-phase/phase-3.8.5/`](closed/by-phase/phase-3.8.5/) |
| Phase 3.9 | 26 | [`closed/by-phase/phase-3.9/`](closed/by-phase/phase-3.9/) |
| Phase 3.9.5 | 24 | [`closed/by-phase/phase-3.9.5/`](closed/by-phase/phase-3.9.5/) |
| Phase 4A | 33 | [`closed/by-phase/phase-4a/`](closed/by-phase/phase-4a/) |
| Phase 4B | 28 | [`closed/by-phase/phase-4b/`](closed/by-phase/phase-4b/) |
| Phase 4.1 | 54 | [`closed/by-phase/phase-4.1/`](closed/by-phase/phase-4.1/) |
| Phase 4.2 | 16 | [`closed/by-phase/phase-4.2/`](closed/by-phase/phase-4.2/) |
| Phase 4.2.5 | 30 | [`closed/by-phase/phase-4.2.5/`](closed/by-phase/phase-4.2.5/) |
| Phase 4.3 | 19 | [`closed/by-phase/phase-4.3/`](closed/by-phase/phase-4.3/) |
| Phase 4.4 | 2 | [`closed/by-phase/phase-4.4/`](closed/by-phase/phase-4.4/) |
| Phase 4.5 | 22 | [`closed/by-phase/phase-4.5/`](closed/by-phase/phase-4.5/) |
| Phase 4.6 | 8 | [`closed/by-phase/phase-4.6/`](closed/by-phase/phase-4.6/) |
| Phase 4.7 | 6 | [`closed/by-phase/phase-4.7/`](closed/by-phase/phase-4.7/) |
| Phase 5.0 | 2 | [`closed/by-phase/phase-5.0/`](closed/by-phase/phase-5.0/) |
| Chưa gắn phase | 118 | [`closed/by-phase/unphased/`](closed/by-phase/unphased/) |
| **Total closed** | **524** | [`closed/INDEX.md`](closed/INDEX.md) |
| Active (đang mở) | 2 | [`active/INDEX.md`](active/INDEX.md) |
<!-- STATS:END -->

---

## 🔍 Tìm 1 issue cụ thể

- **Open issues:** [`active/INDEX.md`](active/INDEX.md)
- **Closed issues (theo số):** [`closed/INDEX.md`](closed/INDEX.md) — tra cứu issue# → phase → title
- **Theo phase:** vào folder phase tương ứng trong `closed/by-phase/`

## 🤖 Phase detection rules

Khi sync, phase được xác định theo thứ tự (dừng ở quy tắc đầu tiên khớp):
1. Label `phase-<V>` trên issue — ví dụ `phase-3a`, `phase-4.5`, `phase-4.2.5`
2. Title chứa `Phase <V>` — ví dụ `[Phase 4.5] ...`, `Phase 3A - ...`
3. Title chứa mã story dạng `P<V>-...` — ví dụ `P4.5-E2-S3`, `P3A-12`
4. Title chứa mã Epic dạng `<V>/E<n>` — ví dụ `4.7/E1`
5. Fallback → `unphased`

`<V>` là số phase có thể có nhiều phần thập phân và hậu tố chữ (`3a`, `4.2.5`).

Nếu bạn muốn override, add label `phase-<N>` vào issue.

---

## 🔗 Liên kết

- 📜 [Product Strategy](../current/strategy.md)
- 📋 Master issue lists per phase:
  - [Phase 1 detailed](../current/phase-1-detailed.md)
  - [Phase 2 detailed](../current/phase-2-detailed.md)
  - [Phase 3A issues (active master)](../current/phase-3a-issues.md)
- 📦 [Migration Notes V1 → V2](../archive/MIGRATION_NOTES.md)
