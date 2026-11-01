#!/usr/bin/env node
/**
 * Issue lifecycle sync
 *
 * Called by .github/workflows/issue-lifecycle.yml. Keeps the per-issue files
 * under docs/active/ and docs/closed/ in sync with GitHub issues:
 *   - open   → docs/active/<phase>/issue-<N>.md
 *   - closed → docs/closed/<phase>/issue-<N>.md
 *   - regenerates docs/active/INDEX.md, docs/closed/INDEX.md and the Quick
 *     Stats block in docs/active/README.md
 *
 * The same <phase>/ folders also hold the phase's planning docs
 * (phase-X-detailed.md, -issues.md, -test-cases.md, …). This script only ever
 * writes/deletes `issue-<N>.md` files and removes a phase folder only when it
 * is completely empty, so those docs are never touched. Moving the planning
 * docs from active/ to closed/ is scripts/archive_phase.py's job.
 *
 * Modes:
 *   node issue-lifecycle.js
 *       Full reconcile: fetch every issue from the GitHub API (GH_TOKEN +
 *       GITHUB_REPOSITORY) and rewrite the issue files to match. If the fetch
 *       fails and GITHUB_EVENT_PATH carries an issue, falls back to syncing
 *       just that issue from the event payload.
 *   node issue-lifecycle.js --event-only
 *       Sync only the issue in GITHUB_EVENT_PATH (old behaviour).
 *   node issue-lifecycle.js --from-json <file>
 *       Full reconcile from a JSON array of issues (REST API shape) — for
 *       local runs and tests.
 *
 * Phase detection order (first match wins):
 *   1. Label `phase-<v>`                    e.g. phase-3a, phase-4.5
 *   2. Title contains `Phase <v>`           e.g. [Phase 4.7], [Epic 1 / Phase 3A],
 *                                                [Epic] Phase 3.9.5 — Epic 2
 *   3. Title contains story code `P<v>-`    e.g. P3A-11, P3.5-S22, P4.2.5-7.1
 *   4. Title contains `<v>/E<n>`            e.g. [4.6/E4]
 *   5. Fallback → unphased
 * where <v> is a version like 3, 3a, 4.5, 3.9.5.
 */

const fs = require('fs');
const path = require('path');

const ACTIVE_BASE = path.join('docs', 'active');
const CLOSED_BASE = path.join('docs', 'closed');
const BASES = [ACTIVE_BASE, CLOSED_BASE];
const ACTIVE_INDEX = path.join(ACTIVE_BASE, 'INDEX.md');
const CLOSED_INDEX = path.join(CLOSED_BASE, 'INDEX.md');
const README = path.join(ACTIVE_BASE, 'README.md');
const STATS_START = '<!-- STATS:START -->';
const STATS_END = '<!-- STATS:END -->';

const UNPHASED = 'unphased';
const VERSION = '(\\d+(?:\\.\\d+)*[a-z]?)';
const LABEL_RE = new RegExp(`^phase-${VERSION}$`, 'i');
const TITLE_RES = [
  new RegExp(`\\bphase\\s*${VERSION}(?![\\w.])`, 'i'),
  new RegExp(`\\bP${VERSION}-[A-Z]*\\d`, 'i'),
  new RegExp(`(?<![\\w.])${VERSION}\\s*/\\s*E\\d+`, 'i'),
];
// Folders under docs/active|closed that this script owns issue files in.
const PHASE_DIR_RE = /^(phase-[0-9a-z.]+|unphased)$/;

function detectPhase(title, labels) {
  for (const l of labels) {
    const m = l.match(LABEL_RE);
    if (m) return `phase-${m[1].toLowerCase()}`;
  }
  for (const re of TITLE_RES) {
    const m = (title || '').match(re);
    if (m) return `phase-${m[1].toLowerCase()}`;
  }
  return UNPHASED;
}

function phaseLabel(phase) {
  if (phase === UNPHASED) return 'Chưa gắn phase';
  if (phase === 'pre-phase') return 'Pre-Phase';
  const m = phase.match(/^phase-(.+)$/);
  return m ? `Phase ${m[1].toUpperCase()}` : phase;
}

// Natural order: phase-1 < phase-3a < phase-3.5 < phase-3.9.5 < phase-4 < … < unphased
function phaseSortKey(phase) {
  const m = phase.match(/^phase-(\d+(?:\.\d+)*)([a-z]?)$/);
  if (!m) return [Infinity];
  const key = m[1].split('.').map(Number);
  // A letter suffix fills the next slot with a value in (-1, 0): above a
  // missing component (-1, see comparePhases) but below any decimal (>= 0),
  // so phase-3 < phase-3a < phase-3b < phase-3.5.
  if (m[2]) key.push(-1 + (m[2].charCodeAt(0) - 96) / 27);
  return key;
}

function comparePhases(a, b) {
  const ka = phaseSortKey(a);
  const kb = phaseSortKey(b);
  for (let i = 0; i < Math.max(ka.length, kb.length); i++) {
    const x = ka[i] ?? -1;
    const y = kb[i] ?? -1;
    if (x !== y) return x < y ? -1 : 1;
  }
  return a.localeCompare(b);
}

function issueBodyContent(number, title, body) {
  return `# Issue #${number}\n\n${title}\n\n${body || ''}\n`;
}

function phaseDirs(base) {
  if (!fs.existsSync(base)) return [];
  return fs.readdirSync(base)
    .filter(d => PHASE_DIR_RE.test(d) && fs.statSync(path.join(base, d)).isDirectory());
}

function removeCopiesExcept(number, keepPath) {
  for (const base of BASES) {
    for (const d of phaseDirs(base)) {
      const p = path.join(base, d, `issue-${number}.md`);
      if (p !== keepPath && fs.existsSync(p)) fs.unlinkSync(p);
    }
  }
}

function writeIssue(number, title, body, state, labels) {
  const phase = detectPhase(title, labels);
  const dir = path.join(state === 'closed' ? CLOSED_BASE : ACTIVE_BASE, phase);
  fs.mkdirSync(dir, { recursive: true });
  const target = path.join(dir, `issue-${number}.md`);
  const content = issueBodyContent(number, title, body);
  if (!fs.existsSync(target) || fs.readFileSync(target, 'utf8') !== content) {
    fs.writeFileSync(target, content);
  }
  removeCopiesExcept(number, target);
  return { phase, target };
}

function extractMetaFromFile(filePath) {
  const raw = fs.readFileSync(filePath, 'utf8');
  const lines = raw.split('\n').map(s => s.trim()).filter(Boolean);
  const header = lines[0] || '';
  const m = header.match(/^#\s*Issue\s*#(\d+)/i);
  const number = m ? parseInt(m[1], 10) : null;
  const title = (lines[1] || '').replace(/\|/g, '\\|');
  return { number, title };
}

function listIssueFiles(dir) {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir)
    .filter(f => /^issue-\d+\.md$/.test(f))
    .map(f => path.join(dir, f));
}

function allIssueFiles() {
  const files = [];
  for (const base of BASES) {
    for (const d of phaseDirs(base)) files.push(...listIssueFiles(path.join(base, d)));
  }
  return files;
}

// Only drops folders that are completely empty — a phase folder that still
// holds planning docs (phase-X-detailed.md, …) is kept even with 0 issues.
function removeEmptyPhaseDirs() {
  for (const base of BASES) {
    for (const d of phaseDirs(base)) {
      const dir = path.join(base, d);
      if (fs.readdirSync(dir).length === 0) fs.rmdirSync(dir);
    }
  }
}

function rowsByPhase(base) {
  const byPhase = {};
  for (const phase of phaseDirs(base).sort(comparePhases)) {
    const rows = listIssueFiles(path.join(base, phase))
      .map(extractMetaFromFile)
      .filter(r => r.number !== null)
      .map(r => ({ ...r, phase }));
    if (rows.length > 0) byPhase[phase] = rows;
  }
  return byPhase;
}

function issueLink(r) {
  return `[${r.phase}/issue-${r.number}.md](${r.phase}/issue-${r.number}.md)`;
}

function regenActiveIndex() {
  fs.mkdirSync(ACTIVE_BASE, { recursive: true });
  const byPhase = rowsByPhase(ACTIVE_BASE);
  const rows = Object.values(byPhase).flat().sort((a, b) => a.number - b.number);

  const lines = [
    '# Active Issues — Index',
    '',
    'GitHub issues đang mở, xếp theo phase. File được auto-sync bởi `.github/workflows/issue-lifecycle.yml`.',
    '',
    '| Issue # | Phase | Title | File |',
    '|---------|-------|-------|------|',
  ];
  if (rows.length === 0) {
    lines.push('| _(none)_ | — | — | — |');
  } else {
    for (const r of rows) {
      lines.push(`| #${r.number} | ${phaseLabel(r.phase)} | ${r.title} | ${issueLink(r)} |`);
    }
  }
  lines.push('', `**Total active:** ${rows.length}`, '');
  fs.writeFileSync(ACTIVE_INDEX, lines.join('\n'));
}

function regenClosedIndex() {
  fs.mkdirSync(CLOSED_BASE, { recursive: true });
  const byPhase = rowsByPhase(CLOSED_BASE);
  const phases = Object.keys(byPhase);
  const allRows = phases.flatMap(p => byPhase[p]).sort((a, b) => a.number - b.number);

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
      lines.push(`| #${r.number} | ${phaseLabel(r.phase)} | ${r.title} | ${issueLink(r)} |`);
    }
  }
  lines.push('');
  lines.push(`**Total:** ${allRows.length} closed issues`);
  const summary = phases.map(p => `${byPhase[p].length} ${phaseLabel(p)}`).join(', ');
  if (summary) lines.push(`(${summary})`);
  lines.push('');
  fs.writeFileSync(CLOSED_INDEX, lines.join('\n'));
}

function regenReadmeStats() {
  if (!fs.existsSync(README)) return;
  const readme = fs.readFileSync(README, 'utf8');
  const start = readme.indexOf(STATS_START);
  const end = readme.indexOf(STATS_END);
  if (start === -1 || end === -1 || end < start) return;

  // README lives in docs/active/, so active links are local and closed links
  // go up one level.
  const active = rowsByPhase(ACTIVE_BASE);
  const closed = rowsByPhase(CLOSED_BASE);
  const phases = [...new Set([...Object.keys(active), ...Object.keys(closed)])].sort(comparePhases);
  const count = (m, p) => (m[p] || []).length;
  const totalActive = phases.reduce((n, p) => n + count(active, p), 0);
  const totalClosed = phases.reduce((n, p) => n + count(closed, p), 0);
  const cell = (n, href) => (n ? `[${n}](${href})` : '—');
  const lines = [
    STATS_START,
    '_Bảng này do `.github/scripts/issue-lifecycle.js` tự sinh — đừng sửa tay._',
    '',
    '| Phase | Active (đang mở) | Closed (đã xong) |',
    '|-------|------------------|------------------|',
    ...phases.map(p =>
      `| ${phaseLabel(p)} | ${cell(count(active, p), `${p}/`)} | ${cell(count(closed, p), `../closed/${p}/`)} |`),
    `| **Total** | **[${totalActive}](INDEX.md)** | **[${totalClosed}](../closed/INDEX.md)** |`,
    STATS_END,
  ];
  const next = readme.slice(0, start) + lines.join('\n') + readme.slice(end + STATS_END.length);
  if (next !== readme) fs.writeFileSync(README, next);
}

function regenAll() {
  removeEmptyPhaseDirs();
  regenActiveIndex();
  regenClosedIndex();
  regenReadmeStats();
}

function labelNames(issue) {
  return (issue.labels || []).map(l => (typeof l === 'string' ? l : l.name));
}

function syncOne(issue) {
  return writeIssue(issue.number, issue.title || '', issue.body || '', issue.state, labelNames(issue));
}

/**
 * Make docs/active|closed issue files mirror `issues` exactly: every issue in its right place,
 * files for numbers GitHub no longer has (deleted/transferred) removed.
 */
function reconcile(issues) {
  const real = issues.filter(i => !i.pull_request);
  if (real.length === 0) throw new Error('Refusing to reconcile against an empty issue list');

  const known = new Set();
  const moved = [];
  for (const issue of real) {
    known.add(issue.number);
    const before = allIssueFiles().filter(f => path.basename(f) === `issue-${issue.number}.md`);
    const { target } = syncOne(issue);
    if (before.length !== 1 || before[0] !== target) moved.push(`#${issue.number} → ${target}`);
  }
  const orphans = [];
  for (const f of allIssueFiles()) {
    const n = parseInt(path.basename(f).match(/\d+/)[0], 10);
    if (!known.has(n)) {
      fs.unlinkSync(f);
      orphans.push(f);
    }
  }
  regenAll();
  console.log(`Reconciled ${real.length} issues; ${moved.length} placed/moved, ${orphans.length} orphan files removed`);
  for (const m of moved) console.log(`  ${m}`);
  for (const o of orphans) console.log(`  removed ${o}`);
}

async function fetchAllIssues() {
  const token = process.env.GH_TOKEN || process.env.GITHUB_TOKEN;
  const repo = process.env.GITHUB_REPOSITORY;
  if (!token || !repo) throw new Error('GH_TOKEN/GITHUB_REPOSITORY not set');
  const issues = [];
  for (let page = 1; page <= 100; page++) {
    // Oldest-first: issues created mid-fetch land on the last page instead of
    // shifting earlier offsets, which could skip an issue and make reconcile
    // delete its file as an orphan.
    const url = `https://api.github.com/repos/${repo}/issues?state=all&sort=created&direction=asc&per_page=100&page=${page}`;
    const res = await fetch(url, {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
      },
    });
    if (!res.ok) throw new Error(`GET ${url} → HTTP ${res.status}`);
    const batch = await res.json();
    issues.push(...batch);
    if (batch.length < 100) return issues;
  }
  throw new Error('Too many pages of issues');
}

function eventIssue() {
  const eventPath = process.env.GITHUB_EVENT_PATH;
  if (!eventPath || !fs.existsSync(eventPath)) return null;
  return JSON.parse(fs.readFileSync(eventPath, 'utf8')).issue || null;
}

function syncFromEvent(issue) {
  const { phase, target } = syncOne(issue);
  console.log(`Synced issue #${issue.number} (state=${issue.state}, phase=${phase}) → ${target}`);
  regenAll();
}

async function main() {
  const args = process.argv.slice(2);
  const jsonIdx = args.indexOf('--from-json');
  if (jsonIdx !== -1) {
    reconcile(JSON.parse(fs.readFileSync(args[jsonIdx + 1], 'utf8')));
    return;
  }
  if (args.includes('--event-only')) {
    const issue = eventIssue();
    if (!issue) throw new Error('No issue in event payload');
    syncFromEvent(issue);
    return;
  }

  let issues;
  try {
    issues = await fetchAllIssues();
  } catch (err) {
    const issue = eventIssue();
    if (!issue) throw err;
    console.warn(`Full reconcile unavailable (${err.message}); syncing #${issue.number} from event payload only`);
    syncFromEvent(issue);
    return;
  }
  reconcile(issues);
}

if (require.main === module) {
  main().catch(err => {
    console.error(err);
    process.exit(1);
  });
}

module.exports = { detectPhase, phaseLabel, comparePhases };
