import { useEffect, useMemo, useState } from 'react';
import {
  ChevronLeft,
  ChevronRight,
  Download,
  Filter,
  MessageSquareText,
  RotateCcw,
  Search,
  X,
} from 'lucide-react';
import Header from '../components/Header';
import MetricShell from '../components/MetricShell';
import { getApiBase, getStoredToken } from '../api/client';
import { getFeedbackCsvUrl, getFeedbackList } from '../api/adminDashboard';
import {
  categoryClasses,
  feedbackCategoryOptions,
  feedbackPeriodOptions,
  feedbackPriorityOptions,
  feedbackSentimentOptions,
  feedbackSortOptions,
  feedbackStatusClasses,
  feedbackStatusOptions,
  formatConfidence,
  formatDateTime,
  formatNumber,
  isUuid,
  optionLabel,
  priorityClasses,
  sentimentClasses,
  shortId,
} from '../utils/adminDashboardUtils';

const PAGE_SIZE = 50;

export default function FeedbackPage() {
  return (
    <main className="min-h-screen bg-paper font-body text-ink-900">
      <Header showDateControls={false} />
      <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6 lg:px-8">
        <FeedbackExplorer />
      </div>
    </main>
  );
}

function FeedbackExplorer() {
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [userIdInput, setUserIdInput] = useState('');
  const [userId, setUserId] = useState('');
  const [period, setPeriod] = useState('all');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [category, setCategory] = useState('');
  const [sentiment, setSentiment] = useState('');
  const [priority, setPriority] = useState('');
  const [status, setStatus] = useState('');
  const [sort, setSort] = useState('newest');
  const [page, setPage] = useState(0);
  const [payload, setPayload] = useState({ total: 0, items: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(null);
  const [exporting, setExporting] = useState(false);
  const [exportNote, setExportNote] = useState('');

  const trimmedUserId = userIdInput.trim();
  const userIdInvalid = trimmedUserId !== '' && !isUuid(trimmedUserId);
  const customIncomplete = period === 'custom' && (!startDate || !endDate);

  // Debounce free-text search so each keystroke doesn't hit the API.
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearch(searchInput.trim());
      setPage(0);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  // The user_id box only forwards a value once it is a complete UUID — the
  // backend 422s on malformed ids. Partial matches still work via the search
  // box (which scans user_id substrings server-side).
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setUserId(isUuid(trimmedUserId) ? trimmedUserId : '');
      setPage(0);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [trimmedUserId]);

  const filterParams = useMemo(
    () => ({ period, startDate, endDate, category, sentiment, priority, status, userId, search, sort }),
    [period, startDate, endDate, category, sentiment, priority, status, userId, search, sort],
  );

  useEffect(() => {
    // A custom range with a missing endpoint would silently fall back to "all"
    // server-side; skip the call until the operator picks both dates.
    if (customIncomplete) {
      setLoading(false);
      return undefined;
    }
    let alive = true;
    async function loadFeedback() {
      setLoading(true);
      setError('');
      try {
        const next = await getFeedbackList({ ...filterParams, limit: PAGE_SIZE, offset: page * PAGE_SIZE });
        if (alive) setPayload(next);
      } catch (err) {
        if (alive) setError(err.message || 'Không tải được feedback.');
      } finally {
        if (alive) setLoading(false);
      }
    }
    loadFeedback();
    return () => {
      alive = false;
    };
  }, [filterParams, page, customIncomplete]);

  const items = payload.items || [];
  const total = payload.total || 0;
  const pageCount = Math.max(Math.ceil(total / PAGE_SIZE), 1);
  const canPrev = page > 0;
  const canNext = page + 1 < pageCount;
  const activeFilterCount =
    (category ? 1 : 0) +
    (sentiment ? 1 : 0) +
    (priority ? 1 : 0) +
    (status ? 1 : 0) +
    (period !== 'all' ? 1 : 0) +
    (userId ? 1 : 0) +
    (search ? 1 : 0);

  function updateFilter(setter) {
    return (event) => {
      setter(event.target.value);
      setPage(0);
    };
  }

  function selectPeriod(value) {
    setPeriod(value);
    setPage(0);
  }

  function resetFilters() {
    setSearchInput('');
    setSearch('');
    setUserIdInput('');
    setUserId('');
    setPeriod('all');
    setStartDate('');
    setEndDate('');
    setCategory('');
    setSentiment('');
    setPriority('');
    setStatus('');
    setSort('newest');
    setPage(0);
  }

  async function exportCsv() {
    setExporting(true);
    setExportNote('');
    try {
      const token = getStoredToken();
      const response = await fetch(`${getApiBase()}${getFeedbackCsvUrl(filterParams)}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) throw new Error('Export thất bại. Thử lại sau.');
      const truncated = response.headers.get('X-Truncated') === 'true';
      const rowsReturned = response.headers.get('X-Rows-Returned');
      const rowsTotal = response.headers.get('X-Rows-Total');
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = objectUrl;
      link.download = 'feedback-export.csv';
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(objectUrl);
      if (truncated) {
        setExportNote(`Đã xuất ${rowsReturned}/${rowsTotal} dòng (đạt giới hạn). Thu hẹp bộ lọc để xuất trọn bộ.`);
      }
    } catch (err) {
      setExportNote(err.message || 'Export thất bại.');
    } finally {
      setExporting(false);
    }
  }

  return (
    <MetricShell eyebrow="Voice of customer" title="Feedback explorer">
      <p className="-mt-2 mb-4 flex items-center gap-2 text-xs text-ink-500">
        <MessageSquareText className="h-3.5 w-3.5 text-gold" aria-hidden="true" />
        Toàn bộ feedback từ trước đến giờ — lọc theo thời gian, phân loại, hoặc user ID.
      </p>

      <div className="mb-4 space-y-3">
        <div className="flex flex-col gap-3 lg:flex-row">
          <div className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-500" aria-hidden="true" />
            <input
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
              placeholder="Tìm trong nội dung feedback hoặc user ID..."
              className="w-full rounded-full border border-hairline bg-paper py-2 pl-10 pr-4 text-sm text-ink-900 placeholder:text-ink-500"
              aria-label="Tìm kiếm feedback"
            />
          </div>
          <div className="min-w-0 flex-1 lg:max-w-xs">
            <input
              value={userIdInput}
              onChange={(event) => setUserIdInput(event.target.value)}
              placeholder="Lọc theo user ID (UUID đầy đủ)"
              className={`w-full rounded-full border bg-paper px-4 py-2 font-mono text-xs text-ink-900 placeholder:font-body placeholder:text-ink-500 ${userIdInvalid ? 'border-burgundy/50' : 'border-hairline'}`}
              aria-label="Lọc theo user ID"
              aria-invalid={userIdInvalid}
            />
            {userIdInvalid ? (
              <p className="mt-1 pl-4 text-[11px] text-burgundy">Nhập UUID đầy đủ để lọc chính xác (hoặc dùng ô tìm kiếm cho khớp một phần).</p>
            ) : null}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {feedbackPeriodOptions.map((item) => (
            <button
              key={item.value}
              type="button"
              onClick={() => selectPeriod(item.value)}
              className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${period === item.value ? 'border-ink-900 bg-ink-900 text-white' : 'border-hairline bg-paper text-ink-500 hover:bg-gold-50 hover:text-ink-900'}`}
              aria-pressed={period === item.value}
            >
              {item.label}
            </button>
          ))}
          {period === 'custom' ? (
            <div className="flex flex-wrap items-center gap-2">
              <input
                type="date"
                value={startDate}
                max={endDate || undefined}
                onChange={updateFilter(setStartDate)}
                className="rounded-full border border-hairline bg-paper px-3 py-1.5 text-xs text-ink-900"
                aria-label="Từ ngày"
              />
              <span className="text-xs text-ink-500">→</span>
              <input
                type="date"
                value={endDate}
                min={startDate || undefined}
                onChange={updateFilter(setEndDate)}
                className="rounded-full border border-hairline bg-paper px-3 py-1.5 text-xs text-ink-900"
                aria-label="Đến ngày"
              />
            </div>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Select label="Category" value={category} options={feedbackCategoryOptions} onChange={updateFilter(setCategory)} />
          <Select label="Sentiment" value={sentiment} options={feedbackSentimentOptions} onChange={updateFilter(setSentiment)} />
          <Select label="Priority" value={priority} options={feedbackPriorityOptions} onChange={updateFilter(setPriority)} />
          <Select label="Status" value={status} options={feedbackStatusOptions} onChange={updateFilter(setStatus)} />
          <Select label="Sort" value={sort} options={feedbackSortOptions} onChange={updateFilter(setSort)} />
          {activeFilterCount > 0 ? (
            <button
              type="button"
              onClick={resetFilters}
              className="inline-flex items-center gap-1.5 rounded-full border border-hairline bg-paper px-3 py-2 text-xs font-medium text-ink-700 transition hover:border-gold hover:text-gold"
            >
              <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
              Reset ({activeFilterCount})
            </button>
          ) : null}
          <button
            type="button"
            onClick={exportCsv}
            disabled={exporting || customIncomplete}
            className="ml-auto inline-flex items-center gap-2 rounded-full border border-hairline bg-paper px-3 py-2 text-xs font-semibold text-ink-700 transition hover:bg-gold-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Download className="h-3.5 w-3.5" aria-hidden="true" />
            {exporting ? 'Đang xuất...' : 'Export CSV'}
          </button>
        </div>
        {exportNote ? (
          <p className="rounded-2xl border border-orange/30 bg-orange/10 px-3 py-2 text-xs leading-5 text-orange">{exportNote}</p>
        ) : null}
      </div>

      {error ? <p className="mb-3 rounded-2xl border border-burgundy/30 bg-burgundy/10 p-3 text-sm text-burgundy" role="alert">{error}</p> : null}

      <div className="overflow-x-auto rounded-2xl border border-hairline">
        <table className="min-w-full divide-y divide-hairline text-sm">
          <thead className="bg-paper text-left text-[11px] uppercase tracking-[0.16em] text-ink-500">
            <tr>
              <th className="px-4 py-3">Thời gian</th>
              <th className="px-4 py-3">User</th>
              <th className="px-4 py-3">Nội dung</th>
              <th className="hidden px-4 py-3 md:table-cell">Phân loại</th>
              <th className="hidden px-4 py-3 lg:table-cell">Sentiment</th>
              <th className="hidden px-4 py-3 lg:table-cell">Ưu tiên</th>
              <th className="px-4 py-3">Trạng thái</th>
              <th className="hidden px-4 py-3 text-right xl:table-cell">Độ tin cậy</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-hairline bg-porcelain">
            {loading ? (
              <FeedbackRowsSkeleton />
            ) : customIncomplete ? (
              <tr>
                <td colSpan="8" className="px-4 py-10 text-center text-ink-500">
                  <span className="inline-flex items-center gap-2"><Filter className="h-4 w-4" aria-hidden="true" /> Chọn cả ngày bắt đầu và kết thúc để lọc theo khoảng tùy chọn.</span>
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr><td colSpan="8" className="px-4 py-10 text-center text-ink-500">Không có feedback khớp bộ lọc.</td></tr>
            ) : (
              items.map((item) => (
                <tr key={item.id} className="cursor-pointer align-top transition hover:bg-gold-50/50" onClick={() => setSelected(item)}>
                  <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-ink-500">{formatDateTime(item.created_at)}</td>
                  <td className="max-w-[160px] px-4 py-3">
                    <p className="truncate font-medium text-ink-900">{item.display_name || '—'}</p>
                    <p className="truncate font-mono text-[11px] text-ink-500">{shortId(item.user_id)}</p>
                    {item.telegram_id ? <p className="truncate font-mono text-[11px] text-ink-500">tg:{item.telegram_id}</p> : null}
                  </td>
                  <td className="max-w-[320px] px-4 py-3">
                    <p className="line-clamp-2 text-ink-900">{item.content}</p>
                    <p className="mt-1 text-[11px] text-ink-500">{item.trigger}</p>
                  </td>
                  <td className="hidden px-4 py-3 md:table-cell"><Badge value={item.category} options={feedbackCategoryOptions} classes={categoryClasses} /></td>
                  <td className="hidden px-4 py-3 lg:table-cell"><Badge value={item.sentiment} options={feedbackSentimentOptions} classes={sentimentClasses} /></td>
                  <td className="hidden px-4 py-3 lg:table-cell"><Badge value={item.priority} options={feedbackPriorityOptions} classes={priorityClasses} /></td>
                  <td className="px-4 py-3"><Badge value={item.status} options={feedbackStatusOptions} classes={feedbackStatusClasses} /></td>
                  <td className="hidden px-4 py-3 text-right font-mono text-xs text-ink-500 xl:table-cell">{formatConfidence(item.classification_confidence)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-4 flex flex-col gap-3 text-sm text-ink-500 sm:flex-row sm:items-center sm:justify-between">
        <p>{formatNumber(total)} feedback · trang {page + 1}/{pageCount}</p>
        <div className="flex gap-2">
          <button type="button" disabled={!canPrev} onClick={() => setPage((value) => Math.max(value - 1, 0))} className="inline-flex items-center gap-1 rounded-full border border-hairline px-3 py-2 disabled:cursor-not-allowed disabled:opacity-40">
            <ChevronLeft className="h-4 w-4" /> Trước
          </button>
          <button type="button" disabled={!canNext} onClick={() => setPage((value) => value + 1)} className="inline-flex items-center gap-1 rounded-full border border-hairline px-3 py-2 disabled:cursor-not-allowed disabled:opacity-40">
            Sau <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>

      {selected ? <FeedbackDetailModal item={selected} onClose={() => setSelected(null)} /> : null}
    </MetricShell>
  );
}

function FeedbackDetailModal({ item, onClose }) {
  useEffect(() => {
    function onKeyDown(event) {
      if (event.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-ink-900/45 p-4 sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-label="Chi tiết feedback"
      onClick={onClose}
    >
      <div
        className="max-h-[92vh] w-full max-w-2xl overflow-y-auto rounded-[2rem] border border-hairline bg-porcelain p-5 shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-gold">Feedback detail</p>
            <h3 className="mt-1 font-display text-2xl font-semibold text-ink-900">{item.display_name || shortId(item.user_id)}</h3>
            <p className="font-mono text-xs text-ink-500">{item.user_id}{item.telegram_id ? ` · tg:${item.telegram_id}` : ''}</p>
          </div>
          <button type="button" onClick={onClose} className="rounded-full border border-hairline p-2 text-ink-500 hover:text-ink-900" aria-label="Đóng chi tiết feedback">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="mb-4 flex flex-wrap gap-2">
          <Badge value={item.category} options={feedbackCategoryOptions} classes={categoryClasses} />
          <Badge value={item.sentiment} options={feedbackSentimentOptions} classes={sentimentClasses} />
          <Badge value={item.priority} options={feedbackPriorityOptions} classes={priorityClasses} />
          <Badge value={item.status} options={feedbackStatusOptions} classes={feedbackStatusClasses} />
        </div>

        <div className="rounded-2xl border border-hairline bg-paper p-4">
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-500">Nội dung</p>
          <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-ink-900">{item.content}</p>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <DetailTile label="Thời gian" value={formatDateTime(item.created_at)} />
          <DetailTile label="Phản hồi đầu tiên" value={item.first_responded_at ? formatDateTime(item.first_responded_at) : 'Chưa phản hồi'} />
          <DetailTile label="Trigger" value={item.trigger || '—'} />
          <DetailTile label="Độ tin cậy phân loại" value={formatConfidence(item.classification_confidence)} />
          <DetailTile label="Tín hiệu emoji onboarding" value={item.onboarding_emoji_signal || '—'} />
          <DetailTile label="Feedback ID" value={item.id} mono />
        </div>
      </div>
    </div>
  );
}

function DetailTile({ label, value, mono = false }) {
  return (
    <div className="rounded-2xl border border-hairline bg-paper p-4">
      <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-500">{label}</p>
      <p className={`mt-2 break-words text-sm font-medium text-ink-900 ${mono ? 'font-mono text-xs' : ''}`}>{value}</p>
    </div>
  );
}

function Badge({ value, options, classes }) {
  if (value === undefined || value === null || value === '') return <span className="text-ink-500">—</span>;
  return (
    <span className={`whitespace-nowrap rounded-full border px-2.5 py-1 text-xs font-semibold ${classes[value] || 'border-ink-100 bg-ink-100 text-ink-500'}`}>
      {optionLabel(options, value)}
    </span>
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

function FeedbackRowsSkeleton() {
  return Array.from({ length: 8 }).map((_, index) => (
    <tr key={index}>
      <td colSpan="8" className="px-4 py-3"><div className="h-9 animate-pulse rounded-xl bg-ink-100" /></td>
    </tr>
  ));
}
