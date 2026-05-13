#!/usr/bin/env node
/**
 * Issue lifecycle sync
 *
 * Called by .github/workflows/issue-lifecycle.yml on issue events.
 * Keeps docs/issues/ in sync with GitHub issues:
 *   - open   → docs/issues/active/issue-<N>.md
 *   - closed → docs/issues/closed/by-phase/<phase>/issue-<N>.md
 *   - regenerates docs/issues/active/INDEX.md and docs/issues/closed/INDEX.md
 *
 * Phase detection order:
 *   1. Label matching /^phase-(\d+[a-z]?)$/i  → phase-<match>
 *   2. Title prefix /\[Phase\s+(\d+[A-Z]?)\b/ → phase-<match>
 *   3. Fallback → pre-phase
 */

const fs = require('fs');
const path = require('path');

const ROOT = 'docs/issues';
const ACTIVE_DIR = path.join(ROOT, 'active');
const CLOSED_BASE = path.join(ROOT, 'closed', 'by-phase');
const ACTIVE_INDEX = path.join(ACTIVE_DIR, 'INDEX.md');
const CLOSED_INDEX = path.join(ROOT, 'closed', 'INDEX.md');

const PHASE_LABELS = {
  'phase-1': 'Phase 1',
  'phase-2': 'Phase 2',
  'phase-3a': 'Phase 3A',
  'phase-3b': 'Phase 3B',
  'phase-4': 'Phase 4',
  'phase-5': 'Phase 5',
  'phase-6': 'Phase 6',
  'pre-phase': 'Pre-Phase',
};

function detectPhase(title, labels) {
  for (const l of labels) {
    const m = l.toLowerCase().match(/^phase-(\d+[a-z]?)$/);
    if (m) return `phase-${m[1]}`;
  }
  const m = (title || '').match(/\[Phase\s+(\d+[A-Za-z]?)\b/i);
  if (m) return `phase-${m[1].toLowerCase()}`;
  return 'pre-phase';
}

function phaseLabel(phase) {
  return PHASE_LABELS[phase] || phase;
}

function issueBodyContent(number, title, body) {
  return `# Issue #${number}\n\n${title}\n\n${body || ''}\n`;
}

function removeCopiesExcept(number, keepPath) {
  const paths = [path.join(ACTIVE_DIR, `issue-${number}.md`)];
  if (fs.existsSync(CLOSED_BASE)) {
    for (const d of fs.readdirSync(CLOSED_BASE)) {
      paths.push(path.join(CLOSED_BASE, d, `issue-${number}.md`));
    }
  }
  for (const p of paths) {
    if (p !== keepPath && fs.existsSync(p)) fs.unlinkSync(p);
  }
}

function writeIssue(number, title, body, state, labels) {
  const phase = detectPhase(title, labels);
  const dir = state === 'closed' ? path.join(CLOSED_BASE, phase) : ACTIVE_DIR;
  fs.mkdirSync(dir, { recursive: true });
  const target = path.join(dir, `issue-${number}.md`);
  fs.writeFileSync(target, issueBodyContent(number, title, body));
  removeCopiesExcept(number, target);
  return { phase, target };
}

function extractMetaFromFile(filePath) {
  const raw = fs.readFileSync(filePath, 'utf8');
  const lines = raw.split('\n').map(s => s.trim()).filter(Boolean);
  const header = lines[0] || '';
  const m = header.match(/^#\s*Issue\s*#(\d+)/i);
  const number = m ? parseInt(m[1], 10) : null;
  const title = lines[1] || '';
  return { number, title };
}

function listIssueFiles(dir) {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir)
    .filter(f => /^issue-\d+\.md$/.test(f))
    .map(f => path.join(dir, f));
}

function regenActiveIndex() {
  fs.mkdirSync(ACTIVE_DIR, { recursive: true });
  const files = listIssueFiles(ACTIVE_DIR);
  const rows = files
    .map(extractMetaFromFile)
    .filter(r => r.number !== null)
    .sort((a, b) => a.number - b.number);

  const lines = [
    '# Active Issues — Index',
    '',
    'GitHub issues đang mở. File được auto-sync bởi `.github/workflows/issue-lifecycle.yml`.',
    '',
    '| Issue # | Title | File |',
    '|---------|-------|------|',
  ];
  if (rows.length === 0) {
    lines.push('| _(none)_ | — | — |');
  } else {
    for (const r of rows) {
      lines.push(`| #${r.number} | ${r.title} | [issue-${r.number}.md](issue-${r.number}.md) |`);
    }
  }
  lines.push('', `**Total active:** ${rows.length}`, '');
  fs.writeFileSync(ACTIVE_INDEX, lines.join('\n'));
}

function regenClosedIndex() {
  if (!fs.existsSync(CLOSED_BASE)) fs.mkdirSync(CLOSED_BASE, { recursive: true });
  const phases = fs.readdirSync(CLOSED_BASE)
    .filter(d => fs.statSync(path.join(CLOSED_BASE, d)).isDirectory())
    .sort();

  const allRows = [];
  const countsByPhase = {};
  for (const phase of phases) {
    const files = listIssueFiles(path.join(CLOSED_BASE, phase));
    const rows = files
      .map(extractMetaFromFile)
      .filter(r => r.number !== null)
      .map(r => ({ ...r, phase }));
    countsByPhase[phase] = rows.length;
    allRows.push(...rows);
  }
  allRows.sort((a, b) => a.number - b.number);

  const lines = [
    '# Closed Issues — Master Index',
    '',
    'Bảng tra cứu toàn bộ issues đã close. Sort theo issue number ascending. File được auto-sync bởi `.github/workflows/issue-lifecycle.yml`.',
    '',
    '| Issue # | Phase | Title | File |',
    '|---------|-------|-------|------|',
  ];
  if (allRows.length === 0) {
    lines.push('| _(none)_ | — | — | — |');
  } else {
    for (const r of allRows) {
      lines.push(
        `| #${r.number} | ${phaseLabel(r.phase)} | ${r.title} | [${r.phase}/issue-${r.number}.md](by-phase/${r.phase}/issue-${r.number}.md) |`,
      );
    }
  }
  lines.push('');
  lines.push(`**Total:** ${allRows.length} closed issues`);
  const byPhase = phases
    .filter(p => countsByPhase[p] > 0)
    .map(p => `${countsByPhase[p]} ${phaseLabel(p)}`)
    .join(', ');
  if (byPhase) lines.push(`(${byPhase})`);
  lines.push('');
  fs.writeFileSync(CLOSED_INDEX, lines.join('\n'));
}

function main() {
  const eventPath = process.env.GITHUB_EVENT_PATH;
  if (!eventPath) throw new Error('GITHUB_EVENT_PATH not set');
  const event = JSON.parse(fs.readFileSync(eventPath, 'utf8'));
  const issue = event.issue;
  if (!issue) throw new Error('No issue in event payload');

  const number = issue.number;
  const title = issue.title || '';
  const body = issue.body || '';
  const state = issue.state;
  const labels = (issue.labels || []).map(l => (typeof l === 'string' ? l : l.name));

  const { phase, target } = writeIssue(number, title, body, state, labels);
  console.log(`Synced issue #${number} (state=${state}, phase=${phase}) → ${target}`);

  regenActiveIndex();
  regenClosedIndex();
  console.log('Regenerated active/INDEX.md and closed/INDEX.md');
}

main();
