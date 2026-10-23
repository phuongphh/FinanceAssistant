#!/usr/bin/env node
/**
 * Issue lifecycle sync
 *
 * Called by .github/workflows/issue-lifecycle.yml. Keeps docs/issues/ in
 * sync with GitHub issues:
 *   - open   → docs/issues/active/issue-<N>.md
 *   - closed → docs/issues/closed/by-phase/<phase>/issue-<N>.md
 *   - regenerates active/INDEX.md, closed/INDEX.md and the Quick Stats block
 *     in docs/issues/README.md
 *
 * Modes:
 *   node issue-lifecycle.js
 *       Full reconcile: fetch every issue from the GitHub API (GH_TOKEN +
 *       GITHUB_REPOSITORY) and rewrite docs/issues/ to match. If the fetch
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

const ROOT = 'docs/issues';
const ACTIVE_DIR = path.join(ROOT, 'active');
const CLOSED_BASE = path.join(ROOT, 'closed', 'by-phase');
const ACTIVE_INDEX = path.join(ACTIVE_DIR, 'INDEX.md');
const CLOSED_INDEX = path.join(ROOT, 'closed', 'INDEX.md');
const README = path.join(ROOT, 'README.md');
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
  return [...m[1].split('.').map(Number), m[2] ? m[2].charCodeAt(0) : 0];
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

function closedPhaseDirs() {
  if (!fs.existsSync(CLOSED_BASE)) return [];
  return fs.readdirSync(CLOSED_BASE)
    .filter(d => fs.statSync(path.join(CLOSED_BASE, d)).isDirectory());
}

function removeCopiesExcept(number, keepPath) {
  const paths = [path.join(ACTIVE_DIR, `issue-${number}.md`)];
  for (const d of closedPhaseDirs()) {
    paths.push(path.join(CLOSED_BASE, d, `issue-${number}.md`));
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
  const files = listIssueFiles(ACTIVE_DIR);
  for (const d of closedPhaseDirs()) files.push(...listIssueFiles(path.join(CLOSED_BASE, d)));
  return files;
}

function removeEmptyPhaseDirs() {
  for (const d of closedPhaseDirs()) {
    const dir = path.join(CLOSED_BASE, d);
    if (fs.readdirSync(dir).length === 0) fs.rmdirSync(dir);
  }
}

function activeRows() {
  return listIssueFiles(ACTIVE_DIR)
    .map(extractMetaFromFile)
    .filter(r => r.number !== null)
    .sort((a, b) => a.number - b.number);
}

function closedRowsByPhase() {
  const byPhase = {};
  for (const phase of closedPhaseDirs().sort(comparePhases)) {
    byPhase[phase] = listIssueFiles(path.join(CLOSED_BASE, phase))
      .map(extractMetaFromFile)
      .filter(r => r.number !== null)
      .map(r => ({ ...r, phase }));
  }
  return byPhase;
}

function regenActiveIndex() {
  fs.mkdirSync(ACTIVE_DIR, { recursive: true });
  const rows = activeRows();

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
  fs.mkdirSync(CLOSED_BASE, { recursive: true });
  const byPhase = closedRowsByPhase();
  const phases = Object.keys(byPhase).filter(p => byPhase[p].length > 0);
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
      lines.push(
        `| #${r.number} | ${phaseLabel(r.phase)} | ${r.title} | [${r.phase}/issue-${r.number}.md](by-phase/${r.phase}/issue-${r.number}.md) |`,
      );
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

  const byPhase = closedRowsByPhase();
  const phases = Object.keys(byPhase).filter(p => byPhase[p].length > 0);
  const total = phases.reduce((n, p) => n + byPhase[p].length, 0);
  const lines = [
    STATS_START,
    '_Bảng này do `.github/scripts/issue-lifecycle.js` tự sinh — đừng sửa tay._',
    '',
    '| Phase | Closed Issues | Folder |',
    '|-------|---------------|--------|',
    ...phases.map(p =>
      `| ${phaseLabel(p)} | ${byPhase[p].length} | [\`closed/by-phase/${p}/\`](closed/by-phase/${p}/) |`),
    `| **Total closed** | **${total}** | [\`closed/INDEX.md\`](closed/INDEX.md) |`,
    `| Active (đang mở) | ${activeRows().length} | [\`active/INDEX.md\`](active/INDEX.md) |`,
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
 * Make docs/issues/ mirror `issues` exactly: every issue in its right place,
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
    const url = `https://api.github.com/repos/${repo}/issues?state=all&per_page=100&page=${page}`;
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
