import { useEffect, useMemo, useState } from 'preact/hooks';

type ConePoint = { year: number; p10: string; p50: string; p90: string };
type TwinPayload = {
  has_projection: boolean;
  scenario: 'current' | 'optimal';
  actual_net_worth: string;
  delta_vs_p50: string | null;
  allocation: Record<string, number>;
  cone: ConePoint[];
  computed_at: string | null;
  empty_state?: string;
};

type Props = { telegramInitData: string };

export function TwinDashboard({ telegramInitData }: Props) {
  const [scenario, setScenario] = useState<'current' | 'optimal'>('current');
  const [payload, setPayload] = useState<TwinPayload | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    fetch(`/api/twin?scenario=${scenario}`, {
      signal: controller.signal,
      headers: { 'X-Telegram-Init-Data': telegramInitData, Accept: 'application/json' },
    })
      .then((res) => {
        if (!res.ok) throw new Error(res.status === 401 ? 'Phiên Telegram hết hạn.' : 'Không tải được dashboard.');
        return res.json();
      })
      .then((body) => {
        setPayload(body.data);
        setError('');
      })
      .catch((err) => {
        if (err.name !== 'AbortError') setError(err.message);
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [scenario, telegramInitData]);

  const target = useMemo(() => payload?.cone[payload.cone.length - 1], [payload]);

  if (loading) return <main class="shell skeleton">Đang tải Bé Tiền tương lai…</main>;
  if (error) return <main class="shell error">{error}</main>;
  if (!payload?.has_projection) return <main class="shell empty">🔮 {payload?.empty_state}</main>;

  return (
    <main class="shell">
      <header class="hero">
        <span>🔮 Bé Tiền tương lai</span>
        <h1>{money(payload.actual_net_worth)}</h1>
        <p>{payload.delta_vs_p50 ? `${money(payload.delta_vs_p50)} so với đường bình thường` : 'Đang theo dõi đường bình thường'}</p>
      </header>
      <nav class="toggle" aria-label="Scenario">
        <button class={scenario === 'current' ? 'active' : ''} onClick={() => setScenario('current')}>Hiện tại</button>
        <button class={scenario === 'optimal' ? 'active' : ''} onClick={() => setScenario('optimal')}>Tối ưu</button>
      </nav>
      <section class="card">
        <h2>Mốc 10 năm</h2>
        <div class="kpis">
          <Kpi label="Khiêm tốn" value={target?.p10} />
          <Kpi label="Bình thường" value={target?.p50} />
          <Kpi label="Lạc quan" value={target?.p90} />
        </div>
      </section>
      <section class="card">
        <h2>Phân bổ</h2>
        {Object.entries(payload.allocation).map(([key, value]) => <p key={key}>{labelAsset(key)}: {(value * 100).toFixed(1)}%</p>)}
      </section>
    </main>
  );
}

function Kpi({ label, value }: { label: string; value?: string }) {
  return <article><small>{label}</small><strong>{money(value ?? '0')}</strong></article>;
}

function money(raw: string) {
  return `${Number(raw).toLocaleString('vi-VN')}đ`;
}

function labelAsset(name: string) {
  const labels: Record<string, string> = {
    cash: 'Tiền mặt',
    cash_savings: 'Tiền mặt',
    crypto: 'Tiền mã hóa',
    gold: 'Vàng',
    life_insurance: 'Bảo hiểm nhân thọ',
    real_estate: 'Bất động sản',
    real_estate_vn: 'Bất động sản',
    stock: 'Cổ phiếu VN',
    stocks_vn: 'Cổ phiếu VN',
    stocks_global: 'Cổ phiếu quốc tế',
    bonds_vn: 'Trái phiếu',
  };
  return labels[name.trim().toLowerCase()] ?? name;
}
