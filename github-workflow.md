## GitHub Workflow Convention — ĐỌC TRƯỚC KHI TẠO ISSUE / PR

Hệ thống dùng **GitHub native sub-issues** làm source of truth cho hierarchy
Epic → Sub-issue. Hai workflow `.github/workflows/auto-pr.yml` và
`project-done.yml` tự expand parent → children qua GraphQL.

### Convention cho Epic (≥2 sub-issues)

1. Tạo **issue cha** (Epic) với title format `[Epic N / Phase X] <name>`
2. Link các issue con làm sub-issues qua GitHub UI hoặc `sub_issue_write` API
3. Khi implement: branch `claude/...`, commit cuối có `Closes #<epic-parent>`
4. `auto-pr.yml` tự expand thành `Closes #parent` + `Closes #child1...#childN`
   trong PR body
5. Merge PR → GitHub đóng tất cả → `project-done.yml` move tất cả sang Done

**Đừng** liệt kê tay từng `Closes #N` cho sub-issues — workflow tự làm.

### Convention cho user story đơn lẻ (không thuộc epic)

Vẫn hoạt động như cũ. `auto-pr.yml` extract issue number từ 3 nguồn (priority
cao → thấp):
1. Branch name: `claude/issue-N-...` hoặc `claude/issues-N-N-...`
2. Commit close keyword: `Closes #N`, `Fixes #N`, `Resolves #N`, `Issue #N`
3. Commit bare reference: `#N` (word-boundary protected)

Issue số đơn lẻ không có sub-issues → expand step skip → behavior như trước.

### Khi nào issue được move sang Done

`project-done.yml` trigger trong 2 case:
- **PR merged**: parse body+branch để lấy issue list → expand sub-issues →
  move + close tất cả
- **Issue closed với reason `completed`**: chính issue đó (+ sub-issues) được
  move sang Done. Reason `not_planned` → SKIP (không move).

→ Hệ quả: dù close issue qua PR merge hay manual UI, kết quả như nhau.

### File workflow liên quan

- `.github/workflows/auto-pr.yml` — chạy on push to `claude/**` → tạo/update
  PR với `Closes` lines (đã expand sub-issues)
- `.github/workflows/project-done.yml` — chạy on PR merge HOẶC issue close →
  move issues sang Done trên Project Board #4
- `.github/workflows/issue-lifecycle.yml` — sync issue events → `docs/issues/`
- `.github/workflows/sync-phase-status.yml` — chạy khi
  `docs/current/phase-status.yaml` thay đổi → regenerate marker sections
  trong CLAUDE.md / README.md / docs/README.md / strategy.md

### Push policy — default to PR for substantive changes

**Default:** mọi thay đổi đi qua `claude/**` branch + PR. Auto-pr.yml tự
tạo PR. User merge → workflow chuyển issue sang Done.

**Direct-to-main CHỈ chấp nhận trong các case sau:**

| Case | Ví dụ | Tại sao OK |
|---|---|---|
| One-off ops script ≤100 lines | `scripts/cleanup-branches.sh` | Không có business logic, không cần review |
| Hotfix workflow YAML đang hư | Fix bug `auto-pr.yml` không tạo PR | PR sẽ chính nó là victim của bug |
| Auto-generated content | Output của `sync_phase_status.py` (qua workflow bot) | Đã được review qua source-of-truth file |

**Substantive changes LUÔN đi qua PR** kể cả khi cảm giác urgent:
- Code thay đổi có business logic
- Schema migrations
- Doc thay đổi structure (không phải auto-gen)
- Workflow YAML thêm/sửa logic mới (không phải hotfix)
- File ≥3 hoặc diff ≥100 lines

**Khi không chắc → ASK USER hoặc DEFAULT TO PR.** PR cost thêm 1-2 phút,
direct-to-main cost mất review history + ngược convention. Trade-off rõ.

**Self-check trước khi `git push origin main`:**
1. Có phải one-off script ngắn không? KHÔNG → branch + PR
2. Có phải hotfix workflow đang hư không? KHÔNG → branch + PR
3. Có phải auto-gen output từ trusted source-of-truth không? KHÔNG → branch + PR
4. Tất cả KHÔNG → branch + PR
