import { useEffect, useMemo, useState } from 'react';
import { Activity, AlertTriangle, Coins, DollarSign, MousePointerClick, TrendingUp, Users, WalletCards } from 'lucide-react';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import Header from '../components/Header';
import HeroSection from '../components/HeroSection';
import MetricShell from '../components/MetricShell';
import SkeletonCard from '../components/SkeletonCard';
import { getDau, getOverview, getUserGrowth } from '../api/adminDashboard';
import { DateRangeProvider, useDateRange } from '../context/DateRangeContext';

const metricCards = [
  { key: 'total_users', label: 'Total users', icon: Users, format: 'number', delta: 'total_users_delta_pct' },
  { key: 'dau', label: 'DAU hôm nay', icon: Activity, format: 'number', delta: 'dau_delta_pct' },
  { key: 'stickiness_pct', label: 'Stickiness', icon: TrendingUp, format: 'percent' },
  { key: 'activation_rate_pct', label: 'Activation', icon: MousePointerClick, format: 'percent' },
  { key: 'total_llm_cost_usd', label: 'LLM cost', icon: DollarSign, format: 'usd', delta: 'cost_delta_pct' },
  { key: 'asset_coverage_pct', label: 'Asset coverage', icon: WalletCards, format: 'percent' },
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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let alive = true;
    async function load() {
      setLoading(true);
      setError('');
      try {
        const [overviewPayload, growthPayload, dauPayload] = await Promise.all([
          getOverview(range),
          getUserGrowth(selectedRange.days),
          getDau(Math.min(selectedRange.days, 90)),
        ]);
        if (!alive) return;
        setOverview(overviewPayload);
        setGrowth(growthPayload.data || []);
        setDau(dauPayload.data || []);
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

  const mergedSeries = useMemo(() => {
    const dauByDate = new Map(dau.map((item) => [item.date, item.dau]));
    return growth.map((item) => ({
      ...item,
      dau: dauByDate.get(item.date) || 0,
      label: item.date.slice(5),
    }));
  }, [growth, dau]);

  return (
    <main className="min-h-screen bg-paper font-body text-ink-900">
      <Header />
      <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6 lg:px-8">
        <HeroSection />

        {error ? (
          <div className="flex items-center gap-3 rounded-3xl border border-burgundy/30 bg-burgundy/10 p-5 text-burgundy" role="alert">
            <AlertTriangle className="h-5 w-5" aria-hidden="true" />
            <div>
              <p className="font-semibold">Không tải được. Click Refresh để thử lại.</p>
              <p className="text-sm">{error}</p>
            </div>
          </div>
        ) : null}

        <section className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
          {loading && !overview
            ? Array.from({ length: 6 }).map((_, index) => <SkeletonCard key={index} />)
            : metricCards.map((card) => <MetricCard key={card.key} card={card} metrics={overview?.metrics || {}} />)}
        </section>

        <section className="grid gap-6 lg:grid-cols-[1.35fr_0.65fr]">
          <MetricShell eyebrow="Growth" title="User growth + DAU">
            <div className="h-80">
              {loading && mergedSeries.length === 0 ? (
                <div className="h-full animate-pulse rounded-2xl bg-ink-100" />
              ) : mergedSeries.length === 0 ? (
                <EmptyState message="Chưa có dữ liệu cho period này." />
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={mergedSeries} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                    <defs>
                      <linearGradient id="goldFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#B8945A" stopOpacity={0.22} />
                        <stop offset="95%" stopColor="#B8945A" stopOpacity={0.02} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="#E8E0D3" vertical={false} />
                    <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fill: '#52677A', fontSize: 11 }} />
                    <YAxis tickLine={false} axisLine={false} tick={{ fill: '#52677A', fontSize: 11 }} />
                    <Tooltip contentStyle={{ border: '1px solid #E8E0D3', borderRadius: 16, fontFamily: 'Geist' }} />
                    <Area type="monotone" dataKey="cumulative" name="Total users" stroke="#B8945A" fill="url(#goldFill)" strokeWidth={2} />
                    <Area type="monotone" dataKey="dau" name="DAU" stroke="#5A7A4F" fill="transparent" strokeWidth={2} />
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </div>
          </MetricShell>

          <MetricShell eyebrow="Framework" title="Epic 5 ready slots">
            <div className="space-y-3 text-sm text-ink-500">
              <Placeholder label="Feature clicks" />
              <Placeholder label="Intent breakdown" />
              <Placeholder label="User tiers" />
              <Placeholder label="Cohort retention" />
              <Placeholder label="User directory" />
            </div>
          </MetricShell>
        </section>
      </div>
    </main>
  );
}

function MetricCard({ card, metrics }) {
  const Icon = card.icon;
  const value = metrics[card.key];
  const delta = card.delta ? metrics[card.delta] : null;
  return (
    <article className="rounded-2xl border border-hairline bg-porcelain p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-ink-500">{card.label}</p>
        <Icon className="h-4 w-4 text-gold" aria-hidden="true" />
      </div>
      <p className="mt-4 font-display text-3xl font-semibold text-ink-900">{formatValue(value, card.format)}</p>
      {delta !== null && delta !== undefined ? (
        <p className={`mt-3 font-mono text-xs ${delta >= 0 ? 'text-sage' : 'text-burgundy'}`}>
          {delta >= 0 ? '+' : ''}{delta}% vs prev
        </p>
      ) : (
        <p className="mt-3 font-mono text-xs text-ink-500">{metrics.wau || 0} WAU · {metrics.mau || 0} MAU</p>
      )}
    </article>
  );
}

function EmptyState({ message }) {
  return (
    <div className="flex h-full items-center justify-center rounded-2xl border border-dashed border-hairline text-sm text-ink-500">
      {message}
    </div>
  );
}

function Placeholder({ label }) {
  return (
    <div className="flex items-center justify-between rounded-2xl border border-hairline bg-paper px-4 py-3">
      <span>{label}</span>
      <span className="font-mono text-xs text-gold">next epic</span>
    </div>
  );
}

function formatValue(value, format) {
  const safe = Number(value || 0);
  if (format === 'percent') return `${safe.toFixed(1)}%`;
  if (format === 'usd') return `$${safe.toFixed(2)}`;
  return new Intl.NumberFormat('vi-VN').format(safe);
}
