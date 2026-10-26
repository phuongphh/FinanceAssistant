# Docs theo phase — Index & Navigation

Toàn bộ tài liệu theo phase của Bé Tiền nằm ở hai thư mục:

- **`docs/active/`** — việc **chưa xong**: issue đang mở + tài liệu định hướng của phase chưa done.
- **`docs/closed/`** — việc **đã xong**: issue đã đóng + tài liệu định hướng của phase đã done.

Cả hai đều chia theo phase (`phase-<id>/`, id viết thường: `phase-4.7`, `phase-4a`…).
Mỗi thư mục phase chứa:

- 3 file định hướng: `phase-<id>-detailed.md`, `phase-<id>-issues.md`, `phase-<id>-test-cases.md`
  (và các doc phụ của phase nếu có, ví dụ deploy-announcements, benchmark…);
- `issue-<N>.md` — snapshot nội dung từng GitHub issue (user story, acceptance criteria, kết quả review).

---

## 🗂️ Folder Structure

```
docs/
├── active/
│   ├── README.md                ← You are here (Quick Stats tự sinh)
│   ├── INDEX.md                 ← Auto-generated: danh sách issue đang mở
│   ├── phase-5.1/
│   │   ├── phase-5.1-detailed.md
│   │   ├── phase-5.1-issues.md
│   │   ├── phase-5.1-test-cases.md   (khi có)
│   │   └── issue-<N>.md         ← issue đang mở của phase
│   ├── …
│   └── unphased/                ← issue đang mở chưa xác định được phase
├── closed/
│   ├── INDEX.md                 ← Auto-generated: issue# → phase → title
│   ├── phase-4.6/
│   │   ├── phase-4.6-detailed.md / -issues.md / -test-cases.md
│   │   └── issue-<N>.md         ← issue đã đóng của phase
│   ├── …
│   └── unphased/
├── current/                     ← doc sống không thuộc phase nào
│   ├── phase-status.yaml        ← nguồn sự thật về trạng thái phase
│   └── strategy.md, tone_guide.md, …
└── archive/                     ← lưu trữ cũ (Phase 1, 2, 3A, 3.6…) — không đổi
```

**Quy tắc xếp chỗ**

| Loại file | Ở `active/` khi… | Ở `closed/` khi… |
|---|---|---|
| `issue-<N>.md` | issue đang **open** | issue đã **closed** |
| Doc định hướng (`phase-<id>-*.md`) | phase chưa `done` trong `phase-status.yaml` | phase đã được ký test (`done`) |

Vì vậy một phase có thể xuất hiện ở **cả hai** nơi — ví dụ Phase 4.7 (pended):
doc định hướng ở `active/phase-4.7/`, còn 6 issue đã đóng ở `closed/phase-4.7/`.

---

## 🤖 Tự động hoá

**1. Issue files + INDEX + Quick Stats** — `.github/workflows/issue-lifecycle.yml`
chạy `.github/scripts/issue-lifecycle.js` khi:
- có issue event (`opened`, `edited`, `closed`, `reopened`, `labeled`, `unlabeled`);
- hằng đêm lúc 02:17 giờ VN (cron, lưới an toàn bắt các event bị lỡ);
- chạy tay qua **Actions → Issue Lifecycle Sync → Run workflow**.

Mỗi lần chạy, script **reconcile toàn bộ**: lấy mọi issue từ GitHub API, ghi
issue đang mở vào `active/<phase>/`, issue đã đóng vào `closed/<phase>/`,
xoá file của issue không còn tồn tại, rồi sinh lại cả hai `INDEX.md` và bảng
Quick Stats bên dưới. Script **chỉ đụng tới file `issue-<N>.md`** — không bao
giờ sửa/xoá doc định hướng; thư mục phase chỉ bị xoá khi đã hoàn toàn rỗng.
Idempotent — chạy nhiều lần không sinh thay đổi thừa.

Chạy local: `GH_TOKEN=... GITHUB_REPOSITORY=phuongphh/FinanceAssistant node .github/scripts/issue-lifecycle.js`
(hoặc `--from-json issues.json` với file JSON xuất từ API).

**2. Đóng phase (doc định hướng active → closed)** — khi tester sửa marker trong
`phase-<id>-test-cases.md` thành `<!-- testing-signoff: signed -->` và push lên
main, workflow **Archive Phase Docs** chạy `scripts/archive_phase.py`: chuyển
mọi doc của `active/phase-<id>/` (trừ `issue-<N>.md`, vốn do script issue quản lý)
sang `closed/phase-<id>/`, sửa link tương đối và cập nhật đường dẫn trong
`docs/current/phase-status.yaml`.

Chạy tay: `python scripts/archive_phase.py --dry-run` (xem trước) hoặc
`python scripts/archive_phase.py --phase 5.1` (ép đóng 1 phase).

**3. Roadmap** — `scripts/sync_phase_status.py` đọc `phase-status.yaml`, sinh
bảng roadmap/README và gieo marker sign-off vào các file test-cases mới.

---

## 📊 Quick Stats

<!-- STATS:START -->
_Bảng này do `.github/scripts/issue-lifecycle.js` tự sinh — đừng sửa tay._

| Phase | Active (đang mở) | Closed (đã xong) |
|-------|------------------|------------------|
| Phase 1 | — | [7](../closed/phase-1/) |
| Phase 2 | — | [9](../closed/phase-2/) |
| Phase 3A | — | [31](../closed/phase-3a/) |
| Phase 3.5 | — | [27](../closed/phase-3.5/) |
| Phase 3.6 | — | [16](../closed/phase-3.6/) |
| Phase 3.7 | — | [16](../closed/phase-3.7/) |
| Phase 3.8 | — | [19](../closed/phase-3.8/) |
| Phase 3.8.5 | — | [11](../closed/phase-3.8.5/) |
| Phase 3.9 | — | [26](../closed/phase-3.9/) |
| Phase 3.9.5 | — | [24](../closed/phase-3.9.5/) |
| Phase 4A | — | [33](../closed/phase-4a/) |
| Phase 4B | — | [28](../closed/phase-4b/) |
| Phase 4.1 | — | [54](../closed/phase-4.1/) |
| Phase 4.2 | — | [16](../closed/phase-4.2/) |
| Phase 4.2.5 | — | [30](../closed/phase-4.2.5/) |
| Phase 4.3 | — | [19](../closed/phase-4.3/) |
| Phase 4.4 | — | [2](../closed/phase-4.4/) |
| Phase 4.5 | — | [22](../closed/phase-4.5/) |
| Phase 4.6 | — | [8](../closed/phase-4.6/) |
| Phase 4.7 | — | [6](../closed/phase-4.7/) |
| Phase 5.0 | — | [2](../closed/phase-5.0/) |
| Chưa gắn phase | [4](unphased/) | [120](../closed/unphased/) |
| **Total** | **[4](INDEX.md)** | **[526](../closed/INDEX.md)** |
<!-- STATS:END -->

---

## 🔍 Tìm 1 issue cụ thể

- **Issue đang mở:** [`INDEX.md`](INDEX.md)
- **Issue đã đóng (theo số):** [`../closed/INDEX.md`](../closed/INDEX.md) — tra cứu issue# → phase → title
- **Theo phase:** vào `active/phase-<id>/` hoặc `closed/phase-<id>/`
- **Trạng thái phase:** [`../current/phase-status.yaml`](../current/phase-status.yaml)

## 🧭 Phase detection rules

Khi sync, phase của issue được xác định theo thứ tự (dừng ở quy tắc đầu tiên khớp):
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
- 🗺️ [Phase status (roadmap)](../current/phase-status.yaml)
- 📦 [Migration Notes V1 → V2](../archive/MIGRATION_NOTES.md)
