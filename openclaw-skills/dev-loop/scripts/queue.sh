#!/usr/bin/env bash
# Hàng đợi: các issue agent:ready (dispatcher sẽ nhặt theo priority/area).
#
# Usage: bash queue.sh

set -euo pipefail
source "$(dirname "$0")/_lib.sh"

require_admin
require_gh

log "Hàng đợi agent:ready — $LOOP_REPO"
gh issue list --repo "$LOOP_REPO" --label "agent:ready" --state open --limit 50 \
    --json number,title,labels \
    --template '{{range .}}  #{{.number}} {{.title}} [{{range $i, $l := .labels}}{{if $i}}, {{end}}{{$l.name}}{{end}}]{{"\n"}}{{else}}  (trống — nhờ PM agent gắn agent:ready cho US){{"\n"}}{{end}}'
