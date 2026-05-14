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
