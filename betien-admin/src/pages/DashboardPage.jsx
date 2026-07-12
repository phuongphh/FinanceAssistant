import { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  Ban,
  ChevronLeft,
  ChevronRight,
  Coins,
  DollarSign,
  Eye,
  MousePointerClick,
  Search,
  ShieldAlert,
  Sparkles,
  TrendingUp,
  Users,
  WalletCards,
  X,
} from 'lucide-react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import Header from '../components/Header';
import HeroSection from '../components/HeroSection';
import MetricShell from '../components/MetricShell';
import SkeletonCard from '../components/SkeletonCard';
import TwinDashboard from './TwinDashboard/TwinDashboard';
import {
  changeUserStatus,
  getCohortRetention,
  getDecisionAdoption,
  getDau,
  getFeatureClicks,
  getIntentBreakdown,
  getLicenseSummary,
  getOverview,
  getUserDetail,
  getUserGrowth,
  getUsers,
  getUserTiers,
} from '../api/adminDashboard';
import { DateRangeProvider, useDateRange } from '../context/DateRangeContext';
import {
  buildUsersQueryParams,
  formatDate,
  formatNumber,
  formatTier,
  formatValue,
  formatVnd,
  getFeatureBarWidthPct,
  getRetentionCellPresentation,
  latestDauWindow,
  pieColors,
  shortId,
  sortOptions,
  statusClasses,
  statusLabel,
  statusOptions,
  tierOptions,
  toDatedChartData,
} from '../utils/adminDashboardUtils';

const metricCards = [
  { key: 'total_users', label: 'Total users', icon: Users, format: 'number', delta: 'total_users_delta_pct', accent: 'bg-gold' },
  { key: 'new_users_period', label: 'New users', icon: Coins, format: 'number', delta: 'new_users_delta_pct', accent: 'bg-orange' },
  { key: 'dau', label: 'DAU hôm nay', icon: Activity, format: 'number', delta: 'dau_delta_pct', accent: 'bg-ink-900' },
  { key: 'stickiness_pct', label: 'Stickiness', icon: TrendingUp, format: 'percent', accent: 'bg-sage' },
  { key: 'activation_rate_pct', label: 'Activation', icon: MousePointerClick, format: 'percent', accent: 'bg-gold' },
  { key: 'asset_coverage_pct', label: 'Asset coverage', icon: WalletCards, format: 'percent', accent: 'bg-orange' },
  { key: 'total_llm_cost_usd', label: 'LLM cost', icon: DollarSign, format: 'usd', delta: 'cost_delta_pct', inverseDelta: true, accent: 'bg-burgundy' },
  { key: 'avg_cost_per_active_user', label: 'Cost / MAU', icon: DollarSign, format: 'usd', inverseDelta: true, accent: 'bg-burgundy' },
  { key: 'wau', label: 'WAU', icon: Users, format: 'number', accent: 'bg-ink-700' },
  { key: 'mau', label: 'MAU', icon: Users, format: 'number', accent: 'bg-ink-700' },
  { key: 'briefing_open_rate_pct', label: 'Briefing open', icon: Eye, format: 'percent', accent: 'bg-sage' },
  { key: 'error_rate_pct', label: 'Error rate', icon: ShieldAlert, format: 'percent', inverseDelta: true, accent: 'bg-burgundy' },
];

export default function DashboardPage() {
  return (
    <DateRangeProvider>
      <DashboardContent />
    </DateRangeProvider>
  );
}

function DashboardContent() {
  const { range, selectedRange, refreshNonce } = useDateRange();
  const [overview, setOverview] = useState(null);
  const [growth, setGrowth] = useState([]);
  const [dau, setDau] = useState([]);
  const [featureClicks, setFeatureClicks] = useState([]);
  const [intentBreakdown, setIntentBreakdown] = useState([]);
  const [userTiers, setUserTiers] = useState([]);
  const [cohorts, setCohorts] = useState([]);
  const [decisionAdoption, setDecisionAdoption] = useState({ weeks: [], cohorts: [] });
  const [licenseSummary, setLicenseSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let alive = true;
    async function load() {
      setLoading(true);
      setError('');
      try {
        const days = selectedRange.days;
        const [overviewPayload, growthPayload, dauPayload, clicksPayload, intentPayload, tiersPayload, cohortPayload, decisionPayload, licensePayload] = await Promise.all([
          getOverview(range),
          getUserGrowth(days),
          getDau(Math.min(days, 90)),
          getFeatureClicks(days, 10),
          getIntentBreakdown(days),
          getUserTiers(),
          getCohortRetention(8),
          getDecisionAdoption(8),
          getLicenseSummary(),
        ]);
        if (!alive) return;
        setOverview(overviewPayload);
        setGrowth(growthPayload.data || []);
        setDau(dauPayload.data || []);
        setFeatureClicks(clicksPayload.data || []);
        setIntentBreakdown(intentPayload.data || []);
        setUserTiers(tiersPayload.data || []);
        setCohorts(cohortPayload.cohorts || []);
        setDecisionAdoption({ weeks: decisionPayload.weeks || [], cohorts: decisionPayload.cohorts || [] });
        setLicenseSummary(licensePayload);
      } catch (err) {
        if (alive) setError(err.message || 'Không tải được dashboard.');
      } finally {
        if (alive) setLoading(false);
      }
    }
    load();
    return () => {
      alive = false;
    };
  }, [range, selectedRange.days, refreshNonce]);

  return (
    <main className="min-h-screen bg-paper font-body text-ink-900">
      <Header />
      <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6 lg:px-8">
        <HeroSection />
        {error ? <ErrorBanner message={error} /> : null}
        <KPIGrid loading={loading} metrics={overview?.metrics || {}} />
        <TwinDashboard period={range} days={selectedRange.days} refreshNonce={refreshNonce} />
        <section className="grid gap-6 lg:grid-cols-[2fr_1fr]">
          <UserGrowthChart loading={loading} growth={growth} />
          <DAUChart loading={loading} dau={latestDauWindow(dau)} />
        </section>
        <section className="grid gap-6 xl:grid-cols-3">
          <FeatureClicksChart loading={loading} data={featureClicks} />
          <IntentBreakdownChart loading={loading} data={intentBreakdown} />
          <TierDistributionChart loading={loading} data={userTiers} />
        </section>
        <CohortRetentionTable loading={loading} cohorts={cohorts} />
        <DecisionAdoptionChart loading={loading} weeks={decisionAdoption.weeks} cohorts={decisionAdoption.cohorts} />
        <LicenseFoundationCard loading={loading} summary={licenseSummary} />
        <UserDirectory refreshNonce={refreshNonce} />
      </div>
    </main>
  );
}

function ErrorBanner({ message }) {
  return (
    <div className="flex items-center gap-3 rounded-3xl border border-burgundy/30 bg-burgundy/10 p-5 text-burgundy" role="alert">
      <AlertTriangle className="h-5 w-5" aria-hidden="true" />
      <div>
        <p className="font-semibold">Không tải được. Click Refresh để thử lại.</p>
        <p className="text-sm">{message}</p>
      </div>
    </div>
  );
}

function KPIGrid({ loading, metrics }) {
  return (
    <section className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
      {loading && Object.keys(metrics).length === 0
        ? Array.from({ length: 12 }).map((_, index) => <SkeletonCard key={index} />)
        : metricCards.map((card) => <KPICard key={card.key} card={card} metrics={metrics} />)}
    </section>
  );
}

function KPICard({ card, metrics }) {
  const Icon = card.icon;
  const value = metrics[card.key];
  const delta = card.delta ? metrics[card.delta] : null;
  const isDeltaGood = card.inverseDelta ? Number(delta) <= 0 : Number(delta) >= 0;
  return (
    <article className="relative overflow-hidden rounded-2xl border border-hairline bg-porcelain p-4">
      <div className={`absolute left-0 top-0 h-3 w-16 rounded-br-2xl ${card.accent}`} aria-hidden="true" />
      <div className="flex items-center justify-between gap-2 pt-2">
        <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-ink-500">{card.label}</p>
        <Icon className="h-4 w-4 text-gold" aria-hidden="true" />
      </div>
      <p className="mt-4 font-display text-4xl font-semibold leading-none text-ink-900 lg:text-3xl xl:text-4xl">{formatValue(value, card.format)}</p>
      {delta !== null && delta !== undefined ? (
        <p className={`mt-3 inline-flex items-center gap-1 font-mono text-xs ${isDeltaGood ? 'text-sage' : 'text-burgundy'}`}>
          {Number(delta) >= 0 ? <ArrowUpRight className="h-3.5 w-3.5" /> : <ArrowDownRight className="h-3.5 w-3.5" />}
          {Number(delta) >= 0 ? '+' : ''}{Number(delta).toFixed(1)}% vs prev
        </p>
      ) : (
        <p className="mt-3 font-mono text-xs text-ink-500">{value === undefined || value === null ? '—' : 'current period'}</p>
      )}
    </article>
  );
}

function UserGrowthChart({ loading, growth }) {
  const data = useMemo(() => toDatedChartData(growth), [growth]);
  return (
    <MetricShell eyebrow="Growth" title="User growth">
      <p className="-mt-2 mb-4 text-xs text-ink-500">Cumulative users and new signups over the selected period.</p>
      <ChartFrame loading={loading} empty={data.length === 0}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="goldFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#B8945A" stopOpacity={0.28} />
                <stop offset="95%" stopColor="#B8945A" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#E8E0D3" vertical={false} />
            <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fill: '#52677A', fontSize: 11 }} />
            <YAxis tickLine={false} axisLine={false} tick={{ fill: '#52677A', fontSize: 11 }} />
            <Tooltip content={<CustomTooltip />} />
            <Area type="monotone" dataKey="cumulative" name="Total users" stroke="#B8945A" fill="url(#goldFill)" strokeWidth={2} />
            <Area type="monotone" dataKey="new_users" name="New users" stroke="#C97B4A" fill="transparent" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      </ChartFrame>
    </MetricShell>
  );
}

function DAUChart({ loading, dau }) {
  const data = useMemo(() => toDatedChartData(dau), [dau]);
  return (
    <MetricShell eyebrow="Engagement" title="DAU">
      <p className="-mt-2 mb-4 text-xs text-ink-500">Daily active users for the latest 14 days.</p>
      <ChartFrame loading={loading} empty={data.length === 0}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 10, right: 8, left: -24, bottom: 0 }}>
            <CartesianGrid stroke="#E8E0D3" vertical={false} />
            <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fill: '#52677A', fontSize: 11 }} />
            <YAxis tickLine={false} axisLine={false} tick={{ fill: '#52677A', fontSize: 11 }} />
            <Tooltip content={<CustomTooltip />} />
            <Bar dataKey="dau" name="DAU" fill="#0A2540" radius={[8, 8, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </ChartFrame>
    </MetricShell>
  );
}

function FeatureClicksChart({ loading, data }) {
  const maxClicks = Math.max(...data.map((item) => item.clicks), 1);
  const topFeature = data[0];
  return (
    <MetricShell eyebrow="Friction" title="Feature clicks">
      <p className="-mt-2 mb-4 text-xs text-ink-500">Top in-product actions by click volume.</p>
      <div className="space-y-3">
        {loading && data.length === 0 ? <SkeletonRows /> : data.length === 0 ? <EmptyState message="Chưa có feature click." /> : data.map((item) => (
          <div key={item.feature_key}>
            <div className="mb-1 flex items-center justify-between text-xs">
              <span className="truncate pr-3 font-medium text-ink-900">{item.feature_name}</span>
              <span className="font-mono text-ink-500">{formatNumber(item.clicks)}</span>
            </div>
            <div className="h-2.5 overflow-hidden rounded-full bg-gold-50">
              <div className="h-full rounded-full bg-gold" style={{ width: getFeatureBarWidthPct(item.clicks, maxClicks) }} />
            </div>
          </div>
        ))}
      </div>
      <Insight>{topFeature ? `${topFeature.feature_name} đang dẫn đầu; ưu tiên kiểm tra funnel sau click này.` : 'Chưa đủ dữ liệu để xác định feature nổi bật.'}</Insight>
    </MetricShell>
  );
}

function IntentBreakdownChart({ loading, data }) {
  const zeroCost = data.find((item) => item.resolved_by === 'rule');
  return (
    <MetricShell eyebrow="Intent" title="Intent breakdown">
      <p className="-mt-2 mb-4 text-xs text-ink-500">Rule-based vs LLM routing mix.</p>
      <DonutChart loading={loading} data={data} nameKey="label" dataKey="count" />
      <Legend data={data.map((item, index) => ({ label: item.label, value: `${item.pct}%`, color: pieColors[index % pieColors.length] }))} />
      <Insight>{zeroCost ? `${zeroCost.pct}% traffic được xử lý zero-cost; mục tiêu Phase 3.5 là giữ quanh 75%.` : 'Chưa có intent event trong period này.'}</Insight>
    </MetricShell>
  );
}

function TierDistributionChart({ loading, data }) {
  const total = data.reduce((sum, item) => sum + item.count, 0);
  return (
    <MetricShell eyebrow="Segments" title="User tiers">
      <p className="-mt-2 mb-4 text-xs text-ink-500">Wealth segment mix for acquisition quality.</p>
      <DonutChart loading={loading} data={data} nameKey="label" dataKey="count" />
      <Legend data={data.map((item, index) => ({ label: item.label, value: formatNumber(item.count), color: pieColors[index % pieColors.length] }))} />
      <Insight>{total > 0 ? `${formatNumber(total)} users có phân khúc; kiểm tra mass affluent/HNW để định hướng monetization.` : 'Chưa có dữ liệu tier.'}</Insight>
    </MetricShell>
  );
}

function DonutChart({ loading, data, nameKey, dataKey }) {
  if (loading && data.length === 0) return <div className="h-52 animate-pulse rounded-2xl bg-ink-100" />;
  if (data.length === 0) return <EmptyState message="Chưa có dữ liệu." className="h-52" />;
  return (
    <div className="h-52">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={data} dataKey={dataKey} nameKey={nameKey} innerRadius={54} outerRadius={82} paddingAngle={3}>
            {data.map((item, index) => <Cell key={`${item[nameKey]}-${index}`} fill={pieColors[index % pieColors.length]} />)}
          </Pie>
          <Tooltip content={<CustomTooltip />} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

function LicenseFoundationCard({ loading, summary }) {
  const plans = summary?.plans || [];
  const statuses = summary?.statuses || [];
  const freePlan = plans.find((item) => item.key === 'free');
  const activeStatus = statuses.find((item) => item.key === 'active');
  const totalLicenses = Number(summary?.total_licenses || 0);
  const totalUsers = Number(summary?.total_users || 0);
  const coveragePct = totalUsers > 0 ? Math.round((totalLicenses / totalUsers) * 1000) / 10 : 0;
  return (
    <section className="overflow-hidden rounded-3xl border border-gold/30 bg-ink-900 text-white shadow-sm">
      <div className="grid gap-6 p-5 md:grid-cols-[1.3fr_1fr] md:p-6">
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <span className="inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-gold text-ink-900">
              <Sparkles className="h-5 w-5" aria-hidden="true" />
            </span>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-gold">License foundation</p>
              <h2 className="font-display text-2xl font-semibold">Monetization-ready data model</h2>
            </div>
            <span className="rounded-full border border-gold/40 bg-gold/15 px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-gold">Coming Phase 5</span>
          </div>
          <p className="max-w-3xl text-sm leading-6 text-white/70">
            License management UI chưa mở cho operator. Phase 4.2.5 chỉ theo dõi backfill free license, trạng thái nền tảng, và sẵn sàng bật Pro tier ở Phase 5.7.
          </p>
          {loading && !summary ? (
            <div className="h-24 animate-pulse rounded-2xl bg-white/10" />
          ) : (
            <div className="grid gap-3 sm:grid-cols-3">
              <DarkStat label="Coverage" value={`${coveragePct}%`} hint={`${formatNumber(totalLicenses)} / ${formatNumber(totalUsers)} users`} />
              <DarkStat label="Free plan" value={formatNumber(freePlan?.count || 0)} hint="default soft-launch tier" />
              <DarkStat label="Active" value={formatNumber(activeStatus?.count || 0)} hint="licenses usable today" />
            </div>
          )}
        </div>
        <div className="rounded-3xl border border-white/10 bg-white/5 p-4">
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm font-semibold text-white">Operational checks</p>
            <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${summary?.missing_free_backfill ? 'bg-burgundy text-white' : 'bg-sage text-white'}`}>
              {summary?.missing_free_backfill ? 'Needs backfill' : 'Healthy'}
            </span>
          </div>
          <div className="mt-4 space-y-3 text-sm text-white/70">
            <CheckRow label="New users auto-created as free" ok={!summary?.missing_free_backfill} />
            <CheckRow label="Unique license per user" ok />
            <CheckRow label="Tenant-scoped admin summary" ok />
          </div>
          <p className="mt-4 rounded-2xl bg-gold/10 px-3 py-2 text-xs leading-5 text-gold">
            Missing backfill: {formatNumber(summary?.missing_free_backfill || 0)}. Nếu khác 0, chạy migration/backfill trước khi bật paid flows.
          </p>
        </div>
      </div>
    </section>
  );
}

function DarkStat({ label, value, hint }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
      <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-white/50">{label}</p>
      <p className="mt-2 font-display text-3xl font-semibold text-white">{value}</p>
      <p className="mt-1 text-xs text-white/50">{hint}</p>
    </div>
  );
}

function CheckRow({ label, ok }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-2xl bg-ink-900/50 px-3 py-2">
      <span>{label}</span>
      <span className={`h-2.5 w-2.5 rounded-full ${ok ? 'bg-sage' : 'bg-burgundy'}`} aria-hidden="true" />
    </div>
  );
}

function CohortRetentionTable({ loading, cohorts }) {
  const weekKeys = ['w0', 'w1', 'w2', 'w3', 'w4', 'w5', 'w6', 'w7'];
  return (
    <MetricShell eyebrow="Retention" title="Cohort retention">
      <p className="-mt-2 mb-4 text-xs text-ink-500">Weekly cohort heatmap; darker cells indicate stronger return behavior.</p>
      {loading && cohorts.length === 0 ? (
        <div className="h-56 animate-pulse rounded-2xl bg-ink-100" />
      ) : cohorts.length === 0 ? (
        <EmptyState message="Chưa có cohort đủ dữ liệu." className="h-48" />
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full border-separate border-spacing-1 text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-[0.16em] text-ink-500">
                <th className="sticky left-0 bg-porcelain px-3 py-2">Cohort</th>
                <th className="px-3 py-2 text-right">Users</th>
                {weekKeys.map((key) => <th key={key} className="px-3 py-2 text-center">{key.toUpperCase()}</th>)}
              </tr>
            </thead>
            <tbody>
              {cohorts.map((cohort) => (
                <tr key={cohort.cohort_week}>
                  <td className="sticky left-0 rounded-xl bg-paper px-3 py-3 font-mono text-xs text-ink-900">{cohort.cohort_week}</td>
                  <td className="rounded-xl bg-paper px-3 py-3 text-right font-mono text-xs text-ink-500">{cohort.cohort_size}</td>
                  {weekKeys.map((key) => <RetentionCell key={key} value={cohort.retention?.[key]} />)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Insight>W1/W2 giảm mạnh là tín hiệu cần can thiệp onboarding hoặc briefing quality.</Insight>
    </MetricShell>
  );
}

function RetentionCell({ value }) {
  const presentation = getRetentionCellPresentation(value);
  if (!presentation) return <td className="rounded-xl bg-paper px-3 py-3" />;
  return (
    <td className={`rounded-xl px-3 py-3 text-center font-mono text-xs font-semibold ${presentation.className}`} style={presentation.style}>
      {presentation.text}
    </td>
  );
}

const decisionMetrics = [
  { key: 'interactions_per_user', label: 'Tương tác / user', format: 'decimal' },
  { key: 'interactions', label: 'Tổng tương tác', format: 'number' },
  { key: 'active_users', label: 'Active users', format: 'number' },
  { key: 'avg_clarity', label: 'Độ nét TB', format: 'decimal' },
];

function formatWeekLabel(week) {
  return typeof week === 'string' ? week.slice(5).replace('-', '/') : String(week);
}

function buildDecisionAdoptionSeries(weeks, cohorts, metric) {
  return weeks.map((week, index) => {
    const row = { label: formatWeekLabel(week) };
    cohorts.forEach((cohort) => {
      const value = cohort.points?.[index]?.[metric];
      row[cohort.cohort] = value === undefined ? null : value;
    });
    return row;
  });
}

function DecisionAdoptionChart({ loading, weeks, cohorts }) {
  const [metric, setMetric] = useState('interactions_per_user');
  const data = useMemo(() => buildDecisionAdoptionSeries(weeks, cohorts, metric), [weeks, cohorts, metric]);
  const empty = cohorts.length === 0;
  const totals = cohorts.map((cohort) => ({
    cohort,
    total: (cohort.points || []).reduce((sum, point) => sum + (point.interactions || 0), 0),
  }));
  const busiest = totals.slice().sort((a, b) => b.total - a.total)[0];
  return (
    <MetricShell eyebrow="Adoption" title="Decision adoption theo cohort">
      <div className="-mt-2 mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-ink-500">Tương tác quyết định theo tuần, tách segment mới (reset) khỏi cohort cũ (legacy).</p>
        <div className="flex flex-wrap gap-1.5">
          {decisionMetrics.map((option) => (
            <button
              key={option.key}
              type="button"
              onClick={() => setMetric(option.key)}
              className={`rounded-full border px-3 py-1 text-xs font-medium transition ${metric === option.key ? 'border-gold bg-gold-50 text-gold' : 'border-hairline text-ink-500 hover:border-gold'}`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>
      <ChartFrame loading={loading} empty={empty || data.length === 0}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 10, right: 12, left: -20, bottom: 0 }}>
            <CartesianGrid stroke="#E8E0D3" vertical={false} />
            <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fill: '#52677A', fontSize: 11 }} />
            <YAxis tickLine={false} axisLine={false} tick={{ fill: '#52677A', fontSize: 11 }} />
            <Tooltip content={<CustomTooltip />} />
            {cohorts.map((cohort, index) => (
              <Line
                key={cohort.cohort}
                type="monotone"
                dataKey={cohort.cohort}
                name={cohort.label}
                stroke={pieColors[index % pieColors.length]}
                strokeWidth={2}
                dot={false}
                connectNulls
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </ChartFrame>
      <Legend data={cohorts.map((cohort, index) => ({ label: cohort.label, value: `${formatNumber(totals[index].total)} tương tác`, color: pieColors[index % pieColors.length] }))} />
      <Insight>
        {busiest && busiest.total > 0
          ? `${busiest.cohort.label} dẫn đầu về tổng tương tác (${formatNumber(busiest.total)}); theo dõi interactions/user để so sánh mức gắn kết giữa các cohort.`
          : 'Chưa có decision query nào được ghi log để tách cohort.'}
      </Insight>
    </MetricShell>
  );
}

function UserDirectory({ refreshNonce }) {
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [tier, setTier] = useState('');
  const [status, setStatus] = useState('');
  const [sort, setSort] = useState('last_active_desc');
  const [page, setPage] = useState(0);
  const [payload, setPayload] = useState({ total: 0, users: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedUserId, setSelectedUserId] = useState(null);
  const [directoryNonce, setDirectoryNonce] = useState(0);
  const limit = 50;

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearch(searchInput.trim());
      setPage(0);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    let alive = true;
    async function loadUsers() {
      setLoading(true);
      setError('');
      try {
        const nextPayload = await getUsers(buildUsersQueryParams({ search, tier, status, sort, limit, offset: page * limit }));
        if (alive) setPayload(nextPayload);
      } catch (err) {
        if (alive) setError(err.message || 'Không tải được user directory.');
      } finally {
        if (alive) setLoading(false);
      }
    }
    loadUsers();
    return () => {
      alive = false;
    };
  }, [search, tier, status, sort, page, refreshNonce, directoryNonce]);

  const pageCount = Math.max(Math.ceil((payload.total || 0) / limit), 1);
  const canPrev = page > 0;
  const canNext = page + 1 < pageCount;

  function updateFilter(setter) {
    return (event) => {
      setter(event.target.value);
      setPage(0);
    };
  }

  return (
    <MetricShell eyebrow="Users" title="User directory">
      <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="relative min-w-0 flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-500" aria-hidden="true" />
          <input
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder="Search user ID, name, Telegram..."
            className="w-full rounded-full border border-hairline bg-paper py-2 pl-10 pr-4 text-sm text-ink-900 placeholder:text-ink-500"
          />
        </div>
        <div className="flex flex-wrap gap-2">
          <Select label="Tier" value={tier} options={tierOptions} onChange={updateFilter(setTier)} />
          <Select label="Status" value={status} options={statusOptions} onChange={updateFilter(setStatus)} />
          <Select label="Sort" value={sort} options={sortOptions} onChange={updateFilter(setSort)} />
        </div>
      </div>
      {error ? <p className="mb-3 rounded-2xl border border-burgundy/30 bg-burgundy/10 p-3 text-sm text-burgundy">{error}</p> : null}
      <div className="overflow-x-auto rounded-2xl border border-hairline">
        <table className="min-w-full divide-y divide-hairline text-sm">
          <thead className="bg-paper text-left text-[11px] uppercase tracking-[0.16em] text-ink-500">
            <tr>
              <SortableTh label="User ID/Name" sortKey="joined_desc" activeSort={sort} setSort={setSort} />
              <th className="px-4 py-3">Tier</th>
              <SortableTh label="Joined" sortKey="joined_desc" activeSort={sort} setSort={setSort} className="hidden md:table-cell" />
              <SortableTh label="Last Active" sortKey="last_active_desc" activeSort={sort} setSort={setSort} />
              <SortableTh label="Messages" sortKey="messages_desc" activeSort={sort} setSort={setSort} className="hidden lg:table-cell" />
              <th className="hidden px-4 py-3 lg:table-cell">Tokens</th>
              <SortableTh label="LLM Cost" sortKey="cost_desc" activeSort={sort} setSort={setSort} className="hidden md:table-cell" />
              <th className="hidden px-4 py-3 sm:table-cell">Assets</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3 text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-hairline bg-porcelain">
            {loading ? <UserRowsSkeleton /> : payload.users.length === 0 ? (
              <tr><td colSpan="10" className="px-4 py-10 text-center text-ink-500">Không tìm thấy user.</td></tr>
            ) : payload.users.map((user) => (
              <tr key={user.user_id} className="cursor-pointer transition hover:bg-gold-50/50" onClick={() => setSelectedUserId(user.user_id)}>
                <td className="max-w-[220px] px-4 py-3">
                  <p className="truncate font-medium text-ink-900">{user.display_name || '—'}</p>
                  <p className="truncate font-mono text-[11px] text-ink-500">{shortId(user.user_id)}</p>
                </td>
                <td className="px-4 py-3"><span className="whitespace-nowrap rounded-full bg-gold-50 px-2.5 py-1 text-xs text-gold">{formatTier(user.tier)}</span></td>
                <td className="hidden px-4 py-3 font-mono text-xs text-ink-500 md:table-cell">{formatDate(user.joined_at)}</td>
                <td className="px-4 py-3 text-xs text-ink-500">{user.last_active_human}</td>
                <td className="hidden px-4 py-3 text-right font-mono text-xs lg:table-cell">{formatNumber(user.messages_total)}</td>
                <td className="hidden px-4 py-3 text-right font-mono text-xs lg:table-cell">{formatNumber(user.tokens_total)}</td>
                <td className="hidden px-4 py-3 text-right font-mono text-xs md:table-cell">${Number(user.llm_cost_total_usd || 0).toFixed(4)}</td>
                <td className={`hidden px-4 py-3 text-right font-mono text-xs sm:table-cell ${user.assets_count === 0 ? 'text-burgundy' : 'text-ink-900'}`}>{formatNumber(user.assets_count)}</td>
                <td className="px-4 py-3"><StatusBadge status={user.status} /></td>
                <td className="px-4 py-3 text-right">
                  <button type="button" className="rounded-full border border-hairline px-3 py-1 text-xs font-medium text-ink-900 hover:border-gold hover:text-gold" onClick={(event) => { event.stopPropagation(); setSelectedUserId(user.user_id); }}>
                    View
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-4 flex flex-col gap-3 text-sm text-ink-500 sm:flex-row sm:items-center sm:justify-between">
        <p>{formatNumber(payload.total || 0)} users · page {page + 1}/{pageCount}</p>
        <div className="flex gap-2">
          <button type="button" disabled={!canPrev} onClick={() => setPage((value) => Math.max(value - 1, 0))} className="inline-flex items-center gap-1 rounded-full border border-hairline px-3 py-2 disabled:cursor-not-allowed disabled:opacity-40">
            <ChevronLeft className="h-4 w-4" /> Prev
          </button>
          <button type="button" disabled={!canNext} onClick={() => setPage((value) => value + 1)} className="inline-flex items-center gap-1 rounded-full border border-hairline px-3 py-2 disabled:cursor-not-allowed disabled:opacity-40">
            Next <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>
      {selectedUserId ? <UserDetailModal userId={selectedUserId} onClose={() => setSelectedUserId(null)} onStatusChanged={() => setDirectoryNonce((value) => value + 1)} /> : null}
    </MetricShell>
  );
}

function UserDetailModal({ userId, onClose, onStatusChanged }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [suspending, setSuspending] = useState(false);
  const [revealing, setRevealing] = useState(false);

  useEffect(() => {
    let alive = true;
    async function loadDetail() {
      setLoading(true);
      setError('');
      try {
        const payload = await getUserDetail(userId);
        if (alive) setDetail(payload);
      } catch (err) {
        if (alive) setError(err.message || 'Không tải được user detail.');
      } finally {
        if (alive) setLoading(false);
      }
    }
    loadDetail();
    return () => {
      alive = false;
    };
  }, [userId]);

  async function revealPii() {
    setRevealing(true);
    setError('');
    try {
      const payload = await getUserDetail(userId, true);
      setDetail(payload);
    } catch (err) {
      setError(err.message || 'Không reveal được PII.');
    } finally {
      setRevealing(false);
    }
  }

  async function suspendUser() {
    if (!detail || detail.status === 'suspended') return;
    setSuspending(true);
    setError('');
    try {
      await changeUserStatus(userId, 'suspended', 'Admin suspended user from observability dashboard.');
      setDetail({ ...detail, status: 'suspended' });
      onStatusChanged();
    } catch (err) {
      setError(err.message || 'Không suspend được user.');
    } finally {
      setSuspending(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink-900/45 p-4 sm:items-center" role="dialog" aria-modal="true">
      <div className="max-h-[92vh] w-full max-w-4xl overflow-y-auto rounded-[2rem] border border-hairline bg-porcelain p-5 shadow-2xl">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-gold">User detail</p>
            <h3 className="mt-1 font-display text-2xl font-semibold text-ink-900">{detail?.display_name || shortId(userId)}</h3>
            <p className="font-mono text-xs text-ink-500">{userId}</p>
          </div>
          <button type="button" onClick={onClose} className="rounded-full border border-hairline p-2 text-ink-500 hover:text-ink-900" aria-label="Close user detail">
            <X className="h-5 w-5" />
          </button>
        </div>
        {error ? <p className="mb-3 rounded-2xl border border-burgundy/30 bg-burgundy/10 p-3 text-sm text-burgundy">{error}</p> : null}
        {loading ? <div className="h-80 animate-pulse rounded-2xl bg-ink-100" /> : detail ? (
          <div className="space-y-5">
            <div className="grid gap-3 sm:grid-cols-4">
              <InfoTile label="Tier" value={formatTier(detail.tier)} />
              <InfoTile label="Status" value={<StatusBadge status={detail.status} />} />
              <InfoTile label="Joined" value={formatDate(detail.joined_at)} />
              <InfoTile label="License" value={`${detail.license?.plan || 'free'} · ${detail.license?.status || 'active'}`} />
            </div>
            <div className="grid gap-4 lg:grid-cols-3">
              <div className="rounded-2xl border border-hairline bg-paper p-4 lg:col-span-2">
                <h4 className="font-display text-lg font-semibold">Message timeline</h4>
                <div className="mt-3 h-48">
                  {detail.timeline.length === 0 ? <EmptyState message="Chưa có message 30 ngày qua." /> : (
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={detail.timeline} margin={{ top: 8, right: 8, left: -24, bottom: 0 }}>
                        <CartesianGrid stroke="#E8E0D3" vertical={false} />
                        <XAxis dataKey="date" tickLine={false} axisLine={false} tick={{ fill: '#52677A', fontSize: 10 }} />
                        <YAxis tickLine={false} axisLine={false} tick={{ fill: '#52677A', fontSize: 10 }} />
                        <Tooltip content={<CustomTooltip />} />
                        <Bar dataKey="messages" name="Messages" fill="#B8945A" radius={[6, 6, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </div>
              </div>
              <Breakdown title="Assets" empty="No assets" rows={detail.assets.map((item) => ({ label: item.type, value: `${item.count} · ${formatVnd(item.total_value_vnd)}` }))} />
              <Breakdown title="Cost breakdown" empty="No LLM cost" rows={detail.cost_by_intent.map((item) => ({ label: item.resolved_by, value: `$${Number(item.total_cost_usd || 0).toFixed(4)} · ${item.calls}` }))} />
            </div>
            <div className="flex flex-col justify-end gap-2 sm:flex-row">
              <button type="button" onClick={revealPii} disabled={revealing} className="inline-flex items-center justify-center gap-2 rounded-full border border-hairline bg-paper px-4 py-2 text-sm font-semibold text-ink-800 transition hover:bg-ink-50 disabled:cursor-not-allowed disabled:opacity-50">
                {revealing ? 'Revealing...' : 'Reveal PII'}
              </button>
              <button type="button" onClick={suspendUser} disabled={suspending || detail.status === 'suspended'} className="inline-flex items-center justify-center gap-2 rounded-full bg-burgundy px-4 py-2 text-sm font-semibold text-white transition hover:bg-burgundy/90 disabled:cursor-not-allowed disabled:opacity-50">
                <Ban className="h-4 w-4" />
                {detail.status === 'suspended' ? 'Already suspended' : suspending ? 'Suspending...' : 'Suspend user'}
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function Select({ label, value, options, onChange }) {
  return (
    <label>
      <span className="sr-only">{label}</span>
      <select value={value} onChange={onChange} className="rounded-full border border-hairline bg-paper px-3 py-2 text-sm text-ink-900">
        {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
    </label>
  );
}

function SortableTh({ label, sortKey, activeSort, setSort, className = '' }) {
  return (
    <th className={`px-4 py-3 ${className}`}>
      <button type="button" onClick={() => setSort(sortKey)} className={`inline-flex items-center gap-1 ${activeSort === sortKey ? 'text-gold' : ''}`}>
        {label}
        {activeSort === sortKey ? '↓' : ''}
      </button>
    </th>
  );
}

function UserRowsSkeleton() {
  return Array.from({ length: 6 }).map((_, index) => (
    <tr key={index}>
      <td colSpan="10" className="px-4 py-3"><div className="h-9 animate-pulse rounded-xl bg-ink-100" /></td>
    </tr>
  ));
}

function StatusBadge({ status }) {
  return <span className={`whitespace-nowrap rounded-full border px-2.5 py-1 text-xs font-semibold ${statusClasses[status] || statusClasses.dormant}`}>{statusLabel(status)}</span>;
}

function InfoTile({ label, value }) {
  return (
    <div className="rounded-2xl border border-hairline bg-paper p-4">
      <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-500">{label}</p>
      <div className="mt-2 text-sm font-medium text-ink-900">{value}</div>
    </div>
  );
}

function Breakdown({ title, rows, empty }) {
  return (
    <div className="rounded-2xl border border-hairline bg-paper p-4">
      <h4 className="font-display text-lg font-semibold">{title}</h4>
      <div className="mt-3 space-y-2 text-sm">
        {rows.length === 0 ? <p className="text-ink-500">{empty}</p> : rows.map((row) => (
          <div key={row.label} className="flex items-center justify-between gap-3 rounded-xl bg-porcelain px-3 py-2">
            <span className="truncate text-ink-900">{row.label}</span>
            <span className="whitespace-nowrap font-mono text-xs text-ink-500">{row.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ChartFrame({ loading, empty, children }) {
  if (loading && empty) return <div className="h-80 animate-pulse rounded-2xl bg-ink-100" />;
  if (empty) return <EmptyState message="Chưa có dữ liệu cho period này." className="h-80" />;
  return <div className="h-80">{children}</div>;
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-2xl border border-hairline bg-white/95 px-3 py-2 text-xs shadow-lg">
      {label ? <p className="mb-1 font-semibold text-ink-900">{label}</p> : null}
      {payload.map((item) => (
        <p key={item.name || item.dataKey} className="font-mono text-ink-500">
          {item.name}: <span className="text-ink-900">{formatNumber(item.value)}</span>
        </p>
      ))}
    </div>
  );
}

function Legend({ data }) {
  return (
    <div className="mt-3 space-y-2">
      {data.map((item) => (
        <div key={item.label} className="flex items-center justify-between gap-3 text-sm">
          <span className="flex min-w-0 items-center gap-2 text-ink-500"><span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: item.color }} /> <span className="truncate">{item.label}</span></span>
          <span className="font-mono text-xs text-ink-900">{item.value}</span>
        </div>
      ))}
    </div>
  );
}

function Insight({ children }) {
  return <p className="mt-4 rounded-2xl bg-gold-50 px-4 py-3 text-xs leading-5 text-ink-700">{children}</p>;
}

function EmptyState({ message, className = 'h-32' }) {
  return <div className={`flex items-center justify-center rounded-2xl border border-dashed border-hairline text-sm text-ink-500 ${className}`}>{message}</div>;
}

function SkeletonRows() {
  return <div className="space-y-3">{Array.from({ length: 5 }).map((_, index) => <div key={index} className="h-7 animate-pulse rounded-full bg-ink-100" />)}</div>;
}
