#!/usr/bin/env bash
# Loop đang làm gì: bật/tắt, issue đang code, PR agent đang mở, worker đang chạy.
#
# Usage: bash status.sh

set -euo pipefail
source "$(dirname "$0")/_lib.sh"

require_admin
require_gh

enabled=$(gh variable get AGENT_LOOP_ENABLED --repo "$LOOP_REPO" 2>/dev/null || echo "(chưa set)")
log "Repo: $LOOP_REPO — AGENT_LOOP_ENABLED=$enabled"

echo
echo "🔨 Đang code (agent:wip):"
gh issue list --repo "$LOOP_REPO" --label "agent:wip" --state open \
    --json number,title --template '{{range .}}  #{{.number}} {{.title}}{{"\n"}}{{else}}  (không có){{"\n"}}{{end}}'

echo
echo "👀 PR chờ review (label agent):"
gh pr list --repo "$LOOP_REPO" --label "agent" --state open \
    --json number,title,isDraft,url \
    --template '{{range .}}  #{{.number}} {{if .isDraft}}[draft] {{end}}{{.title}}{{"\n"}}    {{.url}}{{"\n"}}{{else}}  (không có){{"\n"}}{{end}}'

echo
echo "⚠️  Cần người quyết định (agent:blocked / agent:needs-fix):"
for label in "agent:blocked" "agent:needs-fix"; do
    gh issue list --repo "$LOOP_REPO" --label "$label" --state open \
        --json number,title --template "{{range .}}  #{{.number}} {{.title}} ($label){{\"\n\"}}{{end}}"
done

echo
echo "⚙️  Worker đang chạy:"
gh run list --repo "$LOOP_REPO" --workflow agent-worker.yml --limit 20 \
    --json displayTitle,status,url \
    --template '{{range .}}{{if ne .status "completed"}}  {{.displayTitle}} — {{.status}}{{"\n"}}    {{.url}}{{"\n"}}{{end}}{{end}}'
