export const tierOptions = [
  { value: '', label: 'All tiers' },
  { value: 'starter', label: 'Starter' },
  { value: 'young_pro', label: 'Young Pro' },
  { value: 'mass_affluent', label: 'Mass Affluent' },
  { value: 'hnw', label: 'HNW' },
];

export const statusOptions = [
  { value: '', label: 'All status' },
  { value: 'active', label: 'Active' },
  { value: 'at_risk', label: 'At risk' },
  { value: 'dormant', label: 'Dormant' },
  { value: 'new', label: 'New' },
  { value: 'suspended', label: 'Suspended' },
];

export const sortOptions = [
  { value: 'last_active_desc', label: 'Last active' },
  { value: 'cost_desc', label: 'LLM cost' },
  { value: 'joined_desc', label: 'Joined' },
  { value: 'messages_desc', label: 'Messages' },
];

export const statusClasses = {
  active: 'bg-sage/10 text-sage border-sage/20',
  at_risk: 'bg-orange/10 text-orange border-orange/20',
  dormant: 'bg-ink-100 text-ink-500 border-ink-100',
  new: 'bg-gold-50 text-gold border-gold/20',
  suspended: 'bg-burgundy/10 text-burgundy border-burgundy/20',
};

export const pieColors = ['#B8945A', '#5A7A4F', '#C97B4A', '#8B2635', '#0A2540'];

export function buildAdminDashboardPath(endpoint, params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      query.set(key, String(value));
    }
  });
  const suffix = query.toString();
  return suffix ? `${endpoint}?${suffix}` : endpoint;
}

export function buildUsersQueryParams({ search, tier, status, sort, limit = 50, offset = 0 } = {}) {
  return { search, tier, status, sort, limit, offset };
}

export function buildStatusChangeBody(status, reason) {
  return JSON.stringify({ status, reason });
}

export function toDatedChartData(rows = []) {
  return rows.map((item) => ({ ...item, label: String(item.date).slice(5) }));
}

export function latestDauWindow(rows = [], windowSize = 14) {
  return rows.slice(-windowSize);
}

export function getFeatureBarWidthPct(clicks, maxClicks) {
  const safeMax = Math.max(Number(maxClicks) || 0, 1);
  return `${Math.max((Number(clicks || 0) / safeMax) * 100, 4)}%`;
}

export function getRetentionCellPresentation(value) {
  if (value === null || value === undefined) return null;
  const numeric = Number(value);
  return {
    text: `${numeric}%`,
    className: numeric >= 55 ? 'text-white' : 'text-ink-900',
    style: { backgroundColor: `rgba(184, 148, 90, ${Math.max(numeric / 100, 0.12)})` },
  };
}

export function formatValue(value, format) {
  if (value === undefined || value === null) return '—';
  const safe = Number(value || 0);
  if (format === 'percent') return `${safe.toFixed(1)}%`;
  if (format === 'usd') return `$${safe.toFixed(2)}`;
  return formatNumber(safe);
}

export function formatNumber(value) {
  return new Intl.NumberFormat('vi-VN').format(Number(value || 0));
}

export function formatDate(value) {
  if (!value) return '—';
  return new Intl.DateTimeFormat('vi-VN', { day: '2-digit', month: '2-digit', year: '2-digit' }).format(new Date(value));
}

export function formatVnd(value) {
  return `${formatNumber(value)}₫`;
}

export function shortId(value) {
  return value ? `${value.slice(0, 8)}…${value.slice(-4)}` : '—';
}

export function formatTier(value) {
  return tierOptions.find((item) => item.value === value)?.label || value || '—';
}

export function statusLabel(value) {
  if (value === 'at_risk') return 'At risk';
  return value ? value.charAt(0).toUpperCase() + value.slice(1) : '—';
}
