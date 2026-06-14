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

// ---------------------------------------------------------------------------
// Feedback explorer (admin → /feedback subpage)
// ---------------------------------------------------------------------------
// Option values MUST mirror the backend contracts:
//   period       → backend/api/admin/feedback.py::_RANGE_RE
//   category     → backend/feedback/services/classifier.py::VALID_CATEGORIES
//   sentiment    → ::VALID_SENTIMENTS
//   priority     → ::VALID_PRIORITIES
//   status       → backend/feedback/models/feedback.py::FEEDBACK_STATUS_*
//   sort         → backend/api/admin/feedback.py::SORT_KEYS

export const feedbackPeriodOptions = [
  { value: 'all', label: 'Tất cả' },
  { value: '7d', label: '7 ngày' },
  { value: '14d', label: '14 ngày' },
  { value: '30d', label: '30 ngày' },
  { value: '90d', label: '90 ngày' },
  { value: 'custom', label: 'Tùy chọn' },
];

export const feedbackCategoryOptions = [
  { value: '', label: 'All categories' },
  { value: 'bug', label: 'Bug' },
  { value: 'complaint', label: 'Complaint' },
  { value: 'suggestion', label: 'Suggestion' },
  { value: 'question', label: 'Question' },
  { value: 'praise', label: 'Praise' },
  { value: 'other', label: 'Other' },
];

export const feedbackSentimentOptions = [
  { value: '', label: 'All sentiment' },
  { value: 'positive', label: 'Positive' },
  { value: 'neutral', label: 'Neutral' },
  { value: 'negative', label: 'Negative' },
];

export const feedbackPriorityOptions = [
  { value: '', label: 'All priority' },
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'low', label: 'Low' },
];

export const feedbackStatusOptions = [
  { value: '', label: 'All status' },
  { value: 'new', label: 'New' },
  { value: 'reviewing', label: 'Reviewing' },
  { value: 'actioned', label: 'Actioned' },
  { value: 'dismissed', label: 'Dismissed' },
];

export const feedbackSortOptions = [
  { value: 'newest', label: 'Newest first' },
  { value: 'oldest', label: 'Oldest first' },
];

export const feedbackStatusClasses = {
  new: 'bg-gold-50 text-gold border-gold/20',
  reviewing: 'bg-orange/10 text-orange border-orange/20',
  actioned: 'bg-sage/10 text-sage border-sage/20',
  dismissed: 'bg-ink-100 text-ink-500 border-ink-100',
};

export const sentimentClasses = {
  positive: 'bg-sage/10 text-sage border-sage/20',
  neutral: 'bg-ink-100 text-ink-500 border-ink-100',
  negative: 'bg-burgundy/10 text-burgundy border-burgundy/20',
};

export const priorityClasses = {
  high: 'bg-burgundy/10 text-burgundy border-burgundy/20',
  medium: 'bg-orange/10 text-orange border-orange/20',
  low: 'bg-ink-100 text-ink-500 border-ink-100',
};

export const categoryClasses = {
  bug: 'bg-burgundy/10 text-burgundy border-burgundy/20',
  complaint: 'bg-orange/10 text-orange border-orange/20',
  suggestion: 'bg-gold-50 text-gold border-gold/20',
  question: 'bg-ink-100 text-ink-700 border-ink-100',
  praise: 'bg-sage/10 text-sage border-sage/20',
  other: 'bg-ink-100 text-ink-500 border-ink-100',
};

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isUuid(value) {
  return typeof value === 'string' && UUID_RE.test(value.trim());
}

export function optionLabel(options, value) {
  if (value === undefined || value === null || value === '') return '—';
  return options.find((item) => item.value === value)?.label || value;
}

export function formatDateTime(value) {
  if (!value) return '—';
  return new Intl.DateTimeFormat('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Ho_Chi_Minh',
  }).format(new Date(value));
}

export function formatConfidence(value) {
  if (value === undefined || value === null) return '—';
  return `${Math.round(Number(value) * 100)}%`;
}

// Maps the explorer's UI state onto the backend query contract. Custom dates
// are only forwarded when the custom period is active; buildAdminDashboardPath
// drops every undefined/empty value so unused filters never hit the wire.
export function buildFeedbackQueryParams({
  period = 'all',
  startDate,
  endDate,
  category,
  sentiment,
  priority,
  status,
  userId,
  search,
  sort = 'newest',
  limit = 50,
  offset = 0,
} = {}) {
  const isCustom = period === 'custom';
  return {
    period,
    start_date: isCustom ? startDate : undefined,
    end_date: isCustom ? endDate : undefined,
    category,
    sentiment,
    priority,
    status,
    user_id: userId,
    search,
    sort,
    limit,
    offset,
  };
}
