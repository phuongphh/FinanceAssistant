import { apiFetch } from './client';
import { buildAdminDashboardPath, buildStatusChangeBody, buildUsersQueryParams } from '../utils/adminDashboardUtils';

export function getOverview(period) {
  return apiFetch(buildAdminDashboardPath('/stats/overview', { period }));
}

export function getUserGrowth(days) {
  return apiFetch(buildAdminDashboardPath('/charts/user-growth', { days }));
}

export function getDau(days) {
  return apiFetch(buildAdminDashboardPath('/charts/dau', { days }));
}

export function getFeatureClicks(days, limit = 10) {
  return apiFetch(buildAdminDashboardPath('/charts/feature-clicks', { days, limit }));
}

export function getIntentBreakdown(days) {
  return apiFetch(buildAdminDashboardPath('/charts/intent-breakdown', { days }));
}

export function getUserTiers() {
  return apiFetch('/charts/user-tiers');
}

export function getCohortRetention(weeks = 8) {
  return apiFetch(buildAdminDashboardPath('/charts/cohort-retention', { weeks }));
}

export function getLicenseSummary() {
  return apiFetch('/licenses/summary');
}

export function getUsers(params = {}) {
  return apiFetch(buildAdminDashboardPath('/users', buildUsersQueryParams(params)));
}

export function getUserDetail(userId, reveal = false) {
  const suffix = reveal ? '?reveal=true' : '';
  return apiFetch(`/users/${encodeURIComponent(userId)}${suffix}`);
}

export function changeUserStatus(userId, status, reason) {
  return apiFetch(`/users/${encodeURIComponent(userId)}/status`, {
    method: 'PATCH',
    body: buildStatusChangeBody(status, reason),
  });
}
