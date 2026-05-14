import { apiFetch } from './client';

export function getOverview(period) {
  return apiFetch(`/stats/overview?period=${encodeURIComponent(period)}`);
}

export function getUserGrowth(days) {
  return apiFetch(`/charts/user-growth?days=${encodeURIComponent(days)}`);
}

export function getDau(days) {
  return apiFetch(`/charts/dau?days=${encodeURIComponent(days)}`);
}

export function getFeatureClicks(days, limit = 10) {
  return apiFetch(`/charts/feature-clicks?days=${encodeURIComponent(days)}&limit=${encodeURIComponent(limit)}`);
}

export function getIntentBreakdown(days) {
  return apiFetch(`/charts/intent-breakdown?days=${encodeURIComponent(days)}`);
}

export function getUserTiers() {
  return apiFetch('/charts/user-tiers');
}

export function getCohortRetention(weeks = 8) {
  return apiFetch(`/charts/cohort-retention?weeks=${encodeURIComponent(weeks)}`);
}

export function getUsers(params = {}) {
  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      searchParams.set(key, String(value));
    }
  });
  return apiFetch(`/users?${searchParams.toString()}`);
}

export function getUserDetail(userId) {
  return apiFetch(`/users/${encodeURIComponent(userId)}`);
}

export function changeUserStatus(userId, status, reason) {
  return apiFetch(`/users/${encodeURIComponent(userId)}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ status, reason }),
  });
}
