import { CalendarDays, LayoutDashboard, LogOut, MessageSquareText, RefreshCcw, ShieldCheck } from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { DATE_RANGES, useDateRange } from '../context/DateRangeContext';
import { useAuth } from '../context/AuthContext';

const dateFormatter = new Intl.DateTimeFormat('vi-VN', {
  weekday: 'short',
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  timeZone: 'Asia/Ho_Chi_Minh',
});

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/feedback', label: 'Feedback', icon: MessageSquareText, end: false },
];

// The date-range buttons + Refresh read DateRangeContext, so they only render on
// pages wrapped in DateRangeProvider (the dashboard). Isolating them in a nested
// component keeps the hook out of Header's top level so subpages without the
// provider (e.g. /feedback) can reuse the same chrome via showDateControls=false.
function DateRangeControls() {
  const { range, setRange, refresh } = useDateRange();
  return (
    <>
      <div className="grid grid-cols-4 rounded-full border border-hairline bg-porcelain p-1 text-xs font-medium text-ink-500" aria-label="Chọn khoảng thời gian">
        {DATE_RANGES.map((item) => (
          <button
            key={item.value}
            type="button"
            onClick={() => setRange(item.value)}
            className={`rounded-full px-3 py-1.5 transition ${range === item.value ? 'bg-ink-900 text-white' : 'hover:bg-gold-50 hover:text-ink-900'}`}
            aria-pressed={range === item.value}
          >
            {item.value}
          </button>
        ))}
      </div>

      <button
        type="button"
        onClick={refresh}
        className="inline-flex items-center justify-center gap-2 rounded-full border border-hairline bg-porcelain px-4 py-2 text-sm font-medium text-ink-900 transition hover:border-gold hover:text-gold"
        aria-label="Refresh dashboard data"
      >
        <RefreshCcw className="h-4 w-4" aria-hidden="true" />
        Refresh
      </button>
    </>
  );
}

export default function Header({ showDateControls = true }) {
  const { admin, logout } = useAuth();

  return (
    <header className="sticky top-0 z-20 border-b border-hairline bg-paper/95 backdrop-blur">
      <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-4 sm:px-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-full border border-gold bg-gold-50 font-display text-lg font-semibold text-gold">
              B
            </div>
            <div>
              <p className="font-display text-xl font-semibold leading-none text-ink-900">Bé Tiền Ops</p>
              <p className="mt-1 flex items-center gap-1 text-xs text-ink-500">
                <ShieldCheck className="h-3.5 w-3.5 text-sage" aria-hidden="true" />
                Admin Observability · {admin?.full_name || admin?.email}
              </p>
            </div>
          </div>

          <nav className="flex items-center gap-1 rounded-full border border-hairline bg-porcelain p-1 text-sm font-medium text-ink-500" aria-label="Khu vực quản trị">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) => `inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 transition ${isActive ? 'bg-ink-900 text-white' : 'hover:bg-gold-50 hover:text-ink-900'}`}
                >
                  <Icon className="h-4 w-4" aria-hidden="true" />
                  {item.label}
                </NavLink>
              );
            })}
          </nav>
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="flex items-center gap-2 rounded-full border border-hairline bg-porcelain px-3 py-2 text-xs text-ink-700">
            <CalendarDays className="h-4 w-4 text-gold" aria-hidden="true" />
            <span>{dateFormatter.format(new Date())}</span>
          </div>

          {showDateControls ? <DateRangeControls /> : null}

          <button
            type="button"
            onClick={() => logout()}
            className="inline-flex items-center justify-center gap-2 rounded-full bg-ink-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-ink-700"
            aria-label="Đăng xuất khỏi admin console"
          >
            <LogOut className="h-4 w-4" aria-hidden="true" />
            Đăng xuất
          </button>
        </div>
      </div>
    </header>
  );
}
