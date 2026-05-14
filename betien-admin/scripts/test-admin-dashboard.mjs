import test from 'node:test';
import assert from 'node:assert/strict';
import {
  buildAdminDashboardPath,
  buildStatusChangeBody,
  buildUsersQueryParams,
  formatTier,
  formatValue,
  getFeatureBarWidthPct,
  getRetentionCellPresentation,
  latestDauWindow,
  statusClasses,
  statusLabel,
  toDatedChartData,
} from '../src/utils/adminDashboardUtils.js';

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
