import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Download, RefreshCw, Users } from 'lucide-react';
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
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import MetricShell from '../../components/MetricShell';
import { getApiBase, getStoredToken } from '../../api/client';
import {
  getTwinComprehension,
  getTwinDeltaCsvUrl,
  getTwinDeltaDistribution,
  getTwinEngagementFunnel,
  getTwinEngagementUsers,
  getTwinLoopHealth,
  invalidateTwinCache,
} from '../../api/adminDashboard';
import { buildAdminDashboardPath, formatNumber, formatValue, pieColors, toDatedChartData } from '../../utils/adminDashboardUtils';

const segmentOptions = [
  { value: '', label: 'All segments' },
  { value: 'starter', label: 'Starter' },
  { value: 'young_pro', label: 'Young Pro' },
  { value: 'mass_affluent', label: 'Mass Affluent' },
  { value: 'hnw', label: 'HNW' },
];

export default function TwinDashboard({ period, days, refreshNonce }) {
  const [segment, setSegment] = useState('');
  const [cohortWeek, setCohortWeek] = useState('');
  const [twinPeriod, setTwinPeriod] = useState(period);
  const [customStart, setCustomStart] = useState('');
  const [customEnd, setCustomEnd] = useState('');
  const [payload, setPayload] = useState({ funnel: null, loop: null, comprehension: null, delta: null });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [localRefresh, setLocalRefresh] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshNote, setRefreshNote] = useState('');
  const params = useMemo(() => ({
    period: twinPeriod,
    segment,
    cohort_week: cohortWeek,
    start_date: twinPeriod === 'custom' ? customStart : '',
    end_date: twinPeriod === 'custom' ? customEnd : '',
  }), [twinPeriod, segment, cohortWeek, customStart, customEnd]);

  useEffect(() => {
    let alive = true;
    async function loadTwinMetrics() {
      setLoading(true);
      setError('');
      try {
        const [funnel, loop, comprehension, delta] = await Promise.all([
          getTwinEngagementFunnel(params),
          getTwinLoopHealth(params),
          getTwinComprehension(params),
          getTwinDeltaDistribution(params),
        ]);
        if (alive) setPayload({ funnel, loop, comprehension, delta });
      } catch (err) {
        if (alive) setError(err.message || 'Không tải được Twin dashboard.');
      } finally {
        if (alive) setLoading(false);
      }
    }
    loadTwinMetrics();
    return () => {
      alive = false;
    };
  }, [params, refreshNonce, localRefresh]);

  const generatedAt = payload.funnel?.generated_at || payload.loop?.generated_at
    || payload.comprehension?.generated_at || payload.delta?.generated_at || null;
  const freshnessLabel = useMemo(() => formatFreshness(generatedAt), [generatedAt]);

  async function handleForceRefresh() {
    if (refreshing) return;
    setRefreshing(true);
    setRefreshNote('');
    try {
      const result = await invalidateTwinCache();
      setRefreshNote(`Đã xoá ${result?.keys_removed ?? 0} cache key. Đang tải lại…`);
      setLocalRefresh((prev) => prev + 1);
    } catch (err) {
      setRefreshNote(err.message || 'Không refresh được cache.');
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <section className="space-y-6" id="twin-admin-dashboard">
      <div className="rounded-3xl border border-hairline bg-ink-900 p-5 text-white shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-gold">Phase 4.3 · Twin USP health</p>
            <h2 className="mt-2 font-display text-3xl font-semibold">Twin Admin Dashboard</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-white/70">
              Theo dõi funnel, loop close rate, comprehension và delta distribution mỗi 15 phút để operator phát hiện sớm nếu habit loop fail.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <select value={twinPeriod} onChange={(event) => setTwinPeriod(event.target.value)} className="rounded-full border border-white/10 bg-white/10 px-3 py-2 text-sm text-white" aria-label="Twin date range">
              <option value="7d" className="text-ink-900">7 ngày</option>
              <option value="14d" className="text-ink-900">14 ngày</option>
              <option value="30d" className="text-ink-900">30 ngày</option>
              <option value="custom" className="text-ink-900">Custom</option>
            </select>
            {twinPeriod === 'custom' ? (
              <>
                <input type="date" value={customStart} onChange={(event) => setCustomStart(event.target.value)} className="rounded-full border border-white/10 bg-white/10 px-3 py-2 text-sm text-white" aria-label="Custom start date" />
                <input type="date" value={customEnd} onChange={(event) => setCustomEnd(event.target.value)} className="rounded-full border border-white/10 bg-white/10 px-3 py-2 text-sm text-white" aria-label="Custom end date" />
              </>
            ) : null}
            <select value={segment} onChange={(event) => setSegment(event.target.value)} className="rounded-full border border-white/10 bg-white/10 px-3 py-2 text-sm text-white">
              {segmentOptions.map((option) => <option key={option.value} value={option.value} className="text-ink-900">{option.label}</option>)}
            </select>
            <input
              type="date"
              value={cohortWeek}
              onChange={(event) => setCohortWeek(event.target.value)}
              className="rounded-full border border-white/10 bg-white/10 px-3 py-2 text-sm text-white"
              aria-label="Signup cohort week"
            />
            <span
              className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-2 text-xs text-white/70"
              title={generatedAt ? new Date(generatedAt).toLocaleString('vi-VN') : 'Chưa có dữ liệu'}
            >
              <RefreshCw className="h-3.5 w-3.5" /> {freshnessLabel} · {days}d
            </span>
            <button
              type="button"
              onClick={handleForceRefresh}
              disabled={refreshing}
              className="inline-flex items-center gap-2 rounded-full border border-gold/30 bg-gold/20 px-3 py-2 text-xs font-semibold text-white hover:bg-gold/30 disabled:opacity-60"
              aria-label="Force refresh Twin admin cache"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
              {refreshing ? 'Đang refresh…' : 'Refresh ngay'}
            </button>
          </div>
        </div>
        {refreshNote ? <p className="mt-3 text-xs text-white/70">{refreshNote}</p> : null}
      </div>
      {error ? <TwinError message={error} /> : null}
      <div className="grid gap-6 xl:grid-cols-2">
        <EngagementFunnel loading={loading} data={payload.funnel} params={params} />
        <LoopHealth loading={loading} data={payload.loop} />
        <ComprehensionSignals loading={loading} data={payload.comprehension} />
        <DeltaDistribution loading={loading} data={payload.delta} params={params} />
      </div>
    </section>
  );
}

function EngagementFunnel({ loading, data, params }) {
  const [stage, setStage] = useState('first_view');
  const [users, setUsers] = useState([]);
  const stages = data?.stages || [];
  useEffect(() => {
    let alive = true;
    async function loadUsers() {
      try {
        const payload = await getTwinEngagementUsers({ ...params, stage, limit: 25 });
        if (alive) setUsers(payload.users || []);
      } catch {
        if (alive) setUsers([]);
      }
    }
    if (stage) loadUsers();
    return () => { alive = false; };
  }, [stage, params]);
  return (
    <MetricShell eyebrow="Twin Engagement" title="Engagement funnel">
      <ChartBox loading={loading} empty={!stages.length}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={stages} margin={{ left: -20, right: 8, top: 10 }}>
            <CartesianGrid stroke="#E8E0D3" vertical={false} />
            <XAxis dataKey="label" tick={{ fill: '#52677A', fontSize: 11 }} tickLine={false} axisLine={false} />
            <YAxis tick={{ fill: '#52677A', fontSize: 11 }} tickLine={false} axisLine={false} />
            <Tooltip content={<TwinTooltip />} />
            <Bar dataKey="users" name="Users" fill="#B8945A" radius={[8, 8, 0, 0]} onClick={(row) => setStage(row.key)} />
          </BarChart>
        </ResponsiveContainer>
      </ChartBox>
      <div className="mt-4 grid gap-2 sm:grid-cols-4">
        {stages.map((item) => (
          <button key={item.key} type="button" onClick={() => setStage(item.key)} className={`rounded-2xl border p-3 text-left ${stage === item.key ? 'border-gold bg-gold-50' : 'border-hairline bg-paper'}`}>
            <p className="text-xs text-ink-500">{item.label}</p>
            <p className="font-display text-2xl font-semibold text-ink-900">{formatNumber(item.users)}</p>
            <p className="font-mono text-xs text-sage">{formatValue(item.conversion_pct, 'percent')}</p>
          </button>
        ))}
      </div>
      <UserDrilldown users={users} />
    </MetricShell>
  );
}

function LoopHealth({ loading, data }) {
  const trend = toDatedChartData(data?.trend || []);
  const kpis = data?.kpis || {};
  return (
    <MetricShell eyebrow="Twin Loop Health" title="Trigger → view → action → return">
      <div className="grid gap-3 sm:grid-cols-3">
        <MiniKpi label="Full loop" value={formatValue(kpis.full_loop_close_rate_pct, 'percent')} tone={Number(kpis.full_loop_close_rate_pct || 0) >= 15 ? 'good' : 'bad'} />
        <MiniKpi label="Action completion" value={formatValue(kpis.action_completion_pct, 'percent')} tone={Number(kpis.action_completion_pct || 0) >= 20 ? 'good' : 'bad'} />
        <MiniKpi label="Return after action" value={formatValue(kpis.return_after_action_pct, 'percent')} />
      </div>
      <AlertList alerts={data?.alerts || []} />
      <div className="mt-4 grid gap-4 lg:grid-cols-[1fr_1.5fr]">
        <ChartBox loading={loading} empty={!(data?.trigger_sources || []).length} compact>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={data?.trigger_sources || []} dataKey="count" nameKey="source" innerRadius={45} outerRadius={75} paddingAngle={3}>
                {(data?.trigger_sources || []).map((entry, index) => <Cell key={entry.source} fill={pieColors[index % pieColors.length]} />)}
              </Pie>
              <Tooltip content={<TwinTooltip />} />
            </PieChart>
          </ResponsiveContainer>
        </ChartBox>
        <ChartBox loading={loading} empty={!trend.length} compact>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={trend} margin={{ left: -20, right: 8, top: 10 }}>
              <CartesianGrid stroke="#E8E0D3" vertical={false} />
              <XAxis dataKey="label" tick={{ fill: '#52677A', fontSize: 11 }} tickLine={false} axisLine={false} />
              <YAxis tick={{ fill: '#52677A', fontSize: 11 }} tickLine={false} axisLine={false} />
              <Tooltip content={<TwinTooltip />} />
              <Line type="monotone" dataKey="action_completion_pct" name="Action completion %" stroke="#B8945A" strokeWidth={2} />
              <Line type="monotone" dataKey="return_rate_pct" name="Return rate %" stroke="#5A7A4F" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </ChartBox>
      </div>
    </MetricShell>
  );
}

function ComprehensionSignals({ loading, data }) {
  const reactions = data?.reactions || [];
  const timeOnTwin = toDatedChartData(data?.time_on_twin || []);
  const kpis = data?.kpis || {};
  return (
    <MetricShell eyebrow="Twin Comprehension" title="User hiểu Twin không?">
      <div className="grid gap-3 sm:grid-cols-3">
        <MiniKpi label="Why tap rate" value={formatValue(kpis.why_tap_rate_pct, 'percent')} />
        <MiniKpi label="Follow-up rate" value={formatValue(kpis.followup_question_rate_pct, 'percent')} />
        <MiniKpi label="Twin viewers" value={formatNumber(kpis.views)} />
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <ChartBox loading={loading} empty={!reactions.length} compact>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={reactions} margin={{ left: -20, right: 8, top: 10 }}>
              <CartesianGrid stroke="#E8E0D3" vertical={false} />
              <XAxis dataKey="label" tick={{ fill: '#52677A', fontSize: 11 }} tickLine={false} axisLine={false} />
              <YAxis tick={{ fill: '#52677A', fontSize: 11 }} tickLine={false} axisLine={false} />
              <Tooltip content={<TwinTooltip />} />
              <Bar dataKey="count" name="Reactions" fill="#C97B4A" radius={[8, 8, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartBox>
        <ChartBox loading={loading} empty={!timeOnTwin.length} compact>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={timeOnTwin} margin={{ left: -20, right: 8, top: 10 }}>
              <CartesianGrid stroke="#E8E0D3" vertical={false} />
              <XAxis dataKey="label" tick={{ fill: '#52677A', fontSize: 11 }} tickLine={false} axisLine={false} />
              <YAxis tick={{ fill: '#52677A', fontSize: 11 }} tickLine={false} axisLine={false} />
              <Tooltip content={<TwinTooltip />} />
              <Area dataKey="median_seconds" name="Median seconds" stroke="#0A2540" fill="#0A254033" />
            </AreaChart>
          </ResponsiveContainer>
        </ChartBox>
      </div>
    </MetricShell>
  );
}

function DeltaDistribution({ loading, data, params }) {
  const histogram = data?.histogram || [];
  const p50 = toDatedChartData(data?.p50_distribution || []);
  const calibration = data?.calibration || [];
  const calibrationMeta = data?.calibration_meta || null;
  async function exportCsv() {
    const token = getStoredToken();
    const response = await fetch(buildAdminDashboardPath(`${getApiBase()}${getTwinDeltaCsvUrl(params)}`), { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'twin-delta-distribution.csv';
    link.click();
    URL.revokeObjectURL(url);
  }
  return (
    <MetricShell eyebrow="Twin Delta Distribution" title="Weekly delta calibration">
      <div className="mb-3 flex justify-between gap-3">
        <AlertList alerts={data?.alerts || []} />
        <button type="button" onClick={exportCsv} className="inline-flex items-center gap-2 rounded-full border border-hairline bg-paper px-3 py-2 text-xs font-semibold text-ink-700 hover:bg-gold-50">
          <Download className="h-3.5 w-3.5" /> Export CSV
        </button>
      </div>
      {calibrationMeta?.truncated ? (
        <p className="mb-3 flex items-start gap-2 rounded-2xl border border-orange/30 bg-orange/10 p-3 text-xs leading-5 text-orange">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-none" />
          Đang hiển thị {formatNumber(calibrationMeta.rows_returned)} / {formatNumber(calibrationMeta.rows_total)} điểm calibration (giới hạn {formatNumber(calibrationMeta.cap)}). Export CSV để xem trọn bộ.
        </p>
      ) : null}
      <div className="grid gap-4">
        <ChartBox loading={loading} empty={!histogram.length} compact>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={histogram} margin={{ left: -20, right: 8, top: 10 }}>
              <CartesianGrid stroke="#E8E0D3" vertical={false} />
              <XAxis dataKey="bucket" tick={{ fill: '#52677A', fontSize: 11 }} tickLine={false} axisLine={false} />
              <YAxis tick={{ fill: '#52677A', fontSize: 11 }} tickLine={false} axisLine={false} />
              <Tooltip content={<TwinTooltip />} />
              <ReferenceLine x="-1..1%" stroke="#8B2635" strokeDasharray="3 3" label="threshold" />
              <Bar dataKey="count" name="Deltas" fill="#B8945A" radius={[8, 8, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartBox>
        <div className="grid gap-4 lg:grid-cols-2">
          <ChartBox loading={loading} empty={!p50.length} compact>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={p50} margin={{ left: -20, right: 8, top: 10 }}>
                <CartesianGrid stroke="#E8E0D3" vertical={false} />
                <XAxis dataKey="label" tick={{ fill: '#52677A', fontSize: 11 }} tickLine={false} axisLine={false} />
                <YAxis tick={{ fill: '#52677A', fontSize: 11 }} tickLine={false} axisLine={false} />
                <Tooltip content={<TwinTooltip />} />
                <Area dataKey="p50_vnd" name="P50 estimate" stroke="#5A7A4F" fill="#5A7A4F33" />
              </AreaChart>
            </ResponsiveContainer>
          </ChartBox>
          <ChartBox loading={loading} empty={!calibration.length} compact>
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ left: -20, right: 8, top: 10 }}>
                <CartesianGrid stroke="#E8E0D3" />
                <XAxis type="number" dataKey="predicted_vnd" name="Predicted" tick={{ fill: '#52677A', fontSize: 11 }} />
                <YAxis type="number" dataKey="actual_vnd" name="Actual" tick={{ fill: '#52677A', fontSize: 11 }} />
                <Tooltip content={<TwinTooltip />} />
                <Scatter name="Prediction vs actual" data={calibration} fill="#0A2540" />
              </ScatterChart>
            </ResponsiveContainer>
          </ChartBox>
        </div>
      </div>
    </MetricShell>
  );
}

function UserDrilldown({ users }) {
  return (
    <div className="mt-4 rounded-2xl bg-paper p-3">
      <p className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-ink-500"><Users className="h-3.5 w-3.5" /> Anonymized drill-down</p>
      {users.length === 0 ? <p className="text-sm text-ink-500">Chưa có user trong stage này.</p> : users.slice(0, 5).map((user) => (
        <div key={user.anon_user_id} className="flex justify-between border-t border-hairline py-2 text-xs">
          <span className="font-mono text-ink-900">{user.anon_user_id}</span>
          <span className="text-ink-500">{formatNumber(user.views)} views</span>
        </div>
      ))}
    </div>
  );
}

function MiniKpi({ label, value, tone = 'neutral' }) {
  const color = tone === 'good' ? 'text-sage' : tone === 'bad' ? 'text-burgundy' : 'text-ink-900';
  return (
    <div className="rounded-2xl border border-hairline bg-paper p-3">
      <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-500">{label}</p>
      <p className={`mt-2 font-display text-2xl font-semibold ${color}`}>{value}</p>
    </div>
  );
}

function AlertList({ alerts }) {
  if (!alerts?.length) return null;
  return (
    <div className="mt-3 space-y-2">
      {alerts.map((alert) => (
        <p key={alert.message} className="flex items-start gap-2 rounded-2xl border border-burgundy/20 bg-burgundy/10 p-3 text-xs leading-5 text-burgundy">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-none" /> {alert.message}
        </p>
      ))}
    </div>
  );
}

function formatFreshness(generatedAt) {
  if (!generatedAt) return 'Chưa có dữ liệu';
  const ts = new Date(generatedAt).getTime();
  if (Number.isNaN(ts)) return 'Chưa có dữ liệu';
  const diffSec = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  if (diffSec < 60) return 'Cập nhật vừa xong';
  const mins = Math.floor(diffSec / 60);
  if (mins < 60) return `Cập nhật ${mins} phút trước`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `Cập nhật ${hours} giờ trước`;
  const days = Math.floor(hours / 24);
  return `Cập nhật ${days} ngày trước`;
}

function TwinError({ message }) {
  return <p className="rounded-3xl border border-burgundy/30 bg-burgundy/10 p-4 text-sm text-burgundy">{message}</p>;
}

function ChartBox({ loading, empty, compact = false, children }) {
  const height = compact ? 'h-60' : 'h-72';
  if (loading && empty) return <div className={`${height} animate-pulse rounded-2xl bg-ink-100`} />;
  if (empty) return <div className={`${height} flex items-center justify-center rounded-2xl border border-dashed border-hairline text-sm text-ink-500`}>Chưa có dữ liệu Twin.</div>;
  return <div className={height}>{children}</div>;
}

function TwinTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-2xl border border-hairline bg-white/95 px-3 py-2 text-xs shadow-lg">
      {label ? <p className="mb-1 font-semibold text-ink-900">{label}</p> : null}
      {payload.map((item) => <p key={item.name || item.dataKey} className="font-mono text-ink-500">{item.name}: <span className="text-ink-900">{formatNumber(item.value)}</span></p>)}
    </div>
  );
}
