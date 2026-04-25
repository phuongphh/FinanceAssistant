# Issues — Index & Navigation

Lưu trữ chi tiết các GitHub issues của Personal CFO Assistant theo phase. Mỗi file `issue-<number>.md` là snapshot nội dung của 1 issue (user story, acceptance criteria, kết quả review).

---

## 🗂️ Folder Structure

```
docs/issues/
├── README.md                    ← You are here
├── active/                      ← Currently open issues (work-in-progress)
└── closed/
    ├── INDEX.md                 ← Table tổng: issue# → phase → title
    └── by-phase/
        ├── pre-phase/           ← V1 features (trước khi có cấu trúc phase)
        ├── phase-1/             ← Phase 1: UX Foundation
        └── phase-2/             ← Phase 2: Personality & Care
```

> **Quy ước:** Khi 1 issue được close trên GitHub, file của nó được move từ `active/` sang `closed/by-phase/<phase>/` và update vào [`closed/INDEX.md`](closed/INDEX.md).

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

- Theo **số issue**: xem [`closed/INDEX.md`](closed/INDEX.md) — table tra cứu issue# → phase → title.
- Theo **phase**: vào folder phase tương ứng trong `closed/by-phase/`.
- **Active** issues: file trong `active/`. Sau khi close, file được move sang `closed/by-phase/<phase>/`.

---

## 🔗 Liên kết

- 📜 [Product Strategy](../current/strategy.md)
- 📋 Master issue lists per phase:
  - [Phase 1 detailed](../current/phase-1-detailed.md)
  - [Phase 2 detailed](../current/phase-2-detailed.md)
  - [Phase 3A issues (active master)](../current/phase-3a-issues.md)
- 📦 [Migration Notes V1 → V2](../archive/MIGRATION_NOTES.md)
