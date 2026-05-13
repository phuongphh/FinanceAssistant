# Issues — Index & Navigation

Lưu trữ chi tiết các GitHub issues của Personal CFO Assistant theo phase. Mỗi file `issue-<number>.md` là snapshot nội dung của 1 issue (user story, acceptance criteria, kết quả review).

---

## 🗂️ Folder Structure

```
docs/issues/
├── README.md                    ← You are here
├── active/
│   ├── INDEX.md                 ← Auto-generated list of open issues
│   └── issue-<N>.md             ← One file per open issue
└── closed/
    ├── INDEX.md                 ← Auto-generated: issue# → phase → title
    └── by-phase/
        ├── pre-phase/           ← V1 features (trước khi có cấu trúc phase)
        ├── phase-1/             ← Phase 1: UX Foundation
        ├── phase-2/             ← Phase 2: Personality & Care
        └── phase-3a/            ← Phase 3A: Wealth Foundation (created on first close)
```

> **Tự động hoá:** `.github/workflows/issue-lifecycle.yml` sync mọi GitHub issue event:
> - `opened` / `edited` → ghi `active/issue-<N>.md`
> - `closed` → move sang `closed/by-phase/<phase>/`
> - `reopened` → move ngược về `active/`
> - `labeled` / `unlabeled` → re-check phase, di chuyển file nếu phase thay đổi
>
> Cả hai `INDEX.md` được regenerate tự động sau mỗi event.

---

## 📊 Quick Stats

| Phase | Closed Issues | Folder |
|-------|---------------|--------|
| Pre-Phase (V1) | 5 | [`closed/by-phase/pre-phase/`](closed/by-phase/pre-phase/) |
| Phase 1 — UX Foundation | 7 | [`closed/by-phase/phase-1/`](closed/by-phase/phase-1/) |
| Phase 2 — Personality & Care | 9 | [`closed/by-phase/phase-2/`](closed/by-phase/phase-2/) |
| **Total closed** | **21** | — |
| Active | 0 | [`active/`](active/) |

---

## 🔍 Tìm 1 issue cụ thể

- **Open issues:** [`active/INDEX.md`](active/INDEX.md)
- **Closed issues (theo số):** [`closed/INDEX.md`](closed/INDEX.md) — tra cứu issue# → phase → title
- **Theo phase:** vào folder phase tương ứng trong `closed/by-phase/`

## 🤖 Phase detection rules

Khi sync, phase được xác định theo thứ tự:
1. Label `phase-<N>` trên issue (ví dụ `phase-3a`)
2. Title prefix dạng `[Phase 3A - ...]`
3. Fallback → `pre-phase`

Nếu bạn muốn override, add label `phase-<N>` vào issue.

---

## 🔗 Liên kết

- 📜 [Product Strategy](../current/strategy.md)
- 📋 Master issue lists per phase:
  - [Phase 1 detailed](../current/phase-1-detailed.md)
  - [Phase 2 detailed](../current/phase-2-detailed.md)
  - [Phase 3A issues (active master)](../current/phase-3a-issues.md)
- 📦 [Migration Notes V1 → V2](../archive/MIGRATION_NOTES.md)
