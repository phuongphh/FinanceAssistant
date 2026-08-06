import { Activity, Target, Users } from 'lucide-react';
import { useDateRange } from '../context/DateRangeContext';

export default function HeroSection() {
  const { selectedRange } = useDateRange();

  return (
    <section className="grid gap-6 rounded-[2rem] border border-hairline bg-porcelain p-6 md:grid-cols-[1.5fr_1fr] md:p-8">
      <div>
        <p className="mb-3 text-xs font-semibold uppercase tracking-[0.22em] text-gold">Post soft-launch · Growth Ops</p>
        <h1 className="font-display text-4xl font-semibold leading-tight text-ink-900 md:text-5xl">
          Founder growth dashboard
        </h1>
        <p className="mt-4 max-w-2xl text-sm leading-6 text-ink-500 md:text-base">
          Tập trung vào activation, Twin engagement và retention trong {selectedRange.label.toLowerCase()} gần nhất; bỏ các tín hiệu vanity để operator xử lý đúng nút thắt sau soft launch.
        </p>
      </div>
      <div className="grid grid-cols-3 gap-3 md:grid-cols-1">
        <HeroStat icon={Users} label="Focus" value="D7" suffix="activation" />
        <HeroStat icon={Activity} label="Loop" value="Twin" suffix="habit" />
        <HeroStat icon={Target} label="Next" value="D28" suffix="retention" />
      </div>
    </section>
  );
}

function HeroStat({ icon: Icon, label, value, suffix }) {
  return (
    <div className="rounded-2xl border border-hairline bg-paper p-4">
      <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-ink-500">
        <Icon className="h-4 w-4 text-gold" aria-hidden="true" />
        {label}
      </div>
      <div className="font-display text-2xl font-semibold text-ink-900">{value}</div>
      <div className="mt-1 text-xs text-ink-500">{suffix}</div>
    </div>
  );
}
