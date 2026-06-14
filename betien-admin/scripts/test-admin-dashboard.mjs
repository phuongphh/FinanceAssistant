import test from 'node:test';
import assert from 'node:assert/strict';
import {
  buildAdminDashboardPath,
  buildFeedbackQueryParams,
  buildStatusChangeBody,
  buildUsersQueryParams,
  categoryClasses,
  feedbackStatusClasses,
  formatConfidence,
  formatTier,
  formatValue,
  getFeatureBarWidthPct,
  getRetentionCellPresentation,
  isUuid,
  latestDauWindow,
  optionLabel,
  priorityClasses,
  sentimentClasses,
  statusClasses,
  statusLabel,
  toDatedChartData,
} from '../src/utils/adminDashboardUtils.js';

const SAMPLE_UUID = 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d';

test('API client path builder encodes params and drops empty filters', () => {
  assert.equal(
    buildAdminDashboardPath('/charts/feature-clicks', { days: 30, limit: 10 }),
    '/charts/feature-clicks?days=30&limit=10',
  );
  assert.equal(
    buildAdminDashboardPath('/users', buildUsersQueryParams({ search: 'An Bình', tier: '', status: 'active', sort: 'cost_desc', limit: 50, offset: 100 })),
    '/users?search=An+B%C3%ACnh&status=active&sort=cost_desc&limit=50&offset=100',
  );
});

test('chart helpers shape dates and limit DAU to the latest 14 rows', () => {
  const rows = Array.from({ length: 16 }, (_, index) => ({ date: `2026-05-${String(index + 1).padStart(2, '0')}`, dau: index }));
  assert.deepEqual(toDatedChartData(rows.slice(0, 1)), [{ date: '2026-05-01', dau: 0, label: '05-01' }]);
  assert.equal(latestDauWindow(rows).length, 14);
  assert.equal(latestDauWindow(rows)[0].date, '2026-05-03');
});

test('feature chart helper keeps a visible minimum width and scales top feature to 100%', () => {
  assert.equal(getFeatureBarWidthPct(0, 100), '4%');
  assert.equal(getFeatureBarWidthPct(100, 100), '100%');
  assert.equal(getFeatureBarWidthPct(25, 100), '25%');
});

test('cohort heatmap helper handles null, low retention, and high retention cells', () => {
  assert.equal(getRetentionCellPresentation(null), null);
  assert.deepEqual(getRetentionCellPresentation(20), {
    text: '20%',
    className: 'text-ink-900',
    style: { backgroundColor: 'rgba(184, 148, 90, 0.2)' },
  });
  assert.deepEqual(getRetentionCellPresentation(75), {
    text: '75%',
    className: 'text-white',
    style: { backgroundColor: 'rgba(184, 148, 90, 0.75)' },
  });
});

test('user directory helpers preserve filters, status labels, and status color rules', () => {
  assert.deepEqual(buildUsersQueryParams({ search: 'abc', tier: 'hnw', status: 'active', sort: 'messages_desc', limit: 50, offset: 0 }), {
    search: 'abc',
    tier: 'hnw',
    status: 'active',
    sort: 'messages_desc',
    limit: 50,
    offset: 0,
  });
  assert.equal(formatTier('mass_affluent'), 'Mass Affluent');
  assert.equal(statusLabel('at_risk'), 'At risk');
  assert.match(statusClasses.suspended, /burgundy/);
});

test('suspension payload helper matches backend status endpoint contract', () => {
  assert.equal(
    buildStatusChangeBody('suspended', 'Admin suspended user from observability dashboard.'),
    JSON.stringify({ status: 'suspended', reason: 'Admin suspended user from observability dashboard.' }),
  );
});

test('KPI formatter supports empty state, percent, USD, and vi-VN numbers', () => {
  assert.equal(formatValue(null, 'number'), '—');
  assert.equal(formatValue(42.42, 'percent'), '42.4%');
  assert.equal(formatValue(1.234, 'usd'), '$1.23');
  assert.equal(formatValue(1234567, 'number'), '1.234.567');
});

test('feedback query builder maps UI state onto the backend snake_case contract', () => {
  assert.deepEqual(
    buildFeedbackQueryParams({
      period: '30d',
      category: 'bug',
      sentiment: 'negative',
      priority: 'high',
      status: 'new',
      userId: SAMPLE_UUID,
      search: 'app crash',
      sort: 'oldest',
      limit: 50,
      offset: 100,
    }),
    {
      period: '30d',
      start_date: undefined,
      end_date: undefined,
      category: 'bug',
      sentiment: 'negative',
      priority: 'high',
      status: 'new',
      user_id: SAMPLE_UUID,
      search: 'app crash',
      sort: 'oldest',
      limit: 50,
      offset: 100,
    },
  );
});

test('feedback query builder applies defaults for period, sort, limit, and offset', () => {
  const params = buildFeedbackQueryParams();
  assert.equal(params.period, 'all');
  assert.equal(params.sort, 'newest');
  assert.equal(params.limit, 50);
  assert.equal(params.offset, 0);
});

test('feedback query builder only forwards custom dates when the custom period is active', () => {
  const ranged = buildFeedbackQueryParams({ period: '7d', startDate: '2026-01-01', endDate: '2026-01-31' });
  assert.equal(ranged.start_date, undefined);
  assert.equal(ranged.end_date, undefined);

  const custom = buildFeedbackQueryParams({ period: 'custom', startDate: '2026-01-01', endDate: '2026-01-31' });
  assert.equal(custom.start_date, '2026-01-01');
  assert.equal(custom.end_date, '2026-01-31');
});

test('feedback path builder drops empty filters so unused params never hit the wire', () => {
  assert.equal(
    buildAdminDashboardPath('/feedback', buildFeedbackQueryParams({ category: 'praise', userId: SAMPLE_UUID })),
    `/feedback?period=all&category=praise&user_id=${SAMPLE_UUID}&sort=newest&limit=50&offset=0`,
  );
});

test('isUuid accepts full UUIDs (trimmed) and rejects partial or malformed ids', () => {
  assert.equal(isUuid(SAMPLE_UUID), true);
  assert.equal(isUuid(`  ${SAMPLE_UUID}  `), true);
  assert.equal(isUuid('not-a-uuid'), false);
  assert.equal(isUuid('a1b2c3d4'), false);
  assert.equal(isUuid(''), false);
  assert.equal(isUuid(null), false);
});

test('optionLabel resolves labels, falls back to raw value, and renders an em dash when empty', () => {
  const options = [{ value: 'bug', label: 'Bug' }, { value: 'praise', label: 'Praise' }];
  assert.equal(optionLabel(options, 'bug'), 'Bug');
  assert.equal(optionLabel(options, 'unmapped'), 'unmapped');
  assert.equal(optionLabel(options, ''), '—');
  assert.equal(optionLabel(options, null), '—');
});

test('formatConfidence renders an em dash for null and rounds ratios to whole percent', () => {
  assert.equal(formatConfidence(null), '—');
  assert.equal(formatConfidence(undefined), '—');
  assert.equal(formatConfidence(0.873), '87%');
  assert.equal(formatConfidence(1), '100%');
  assert.equal(formatConfidence(0), '0%');
});

test('feedback badge color maps cover every backend enum value', () => {
  assert.match(categoryClasses.bug, /burgundy/);
  assert.match(sentimentClasses.negative, /burgundy/);
  assert.match(sentimentClasses.positive, /sage/);
  assert.match(priorityClasses.high, /burgundy/);
  assert.match(feedbackStatusClasses.new, /gold/);
  assert.match(feedbackStatusClasses.actioned, /sage/);
});
