import { useCallback, useEffect, useState } from 'react';
import { ChevronLeft, ChevronRight, Eye, EyeOff, Flame, Pencil, Plus, Trash2, X } from 'lucide-react';
import Header from '../components/Header';
import MetricShell from '../components/MetricShell';
import { createSocialBuzz, deleteSocialBuzz, getSocialBuzzList, updateSocialBuzz } from '../api/adminDashboard';
import { formatDateTime, formatNumber, optionLabel } from '../utils/adminDashboardUtils';

const PAGE_SIZE = 50;

const CATEGORY_OPTIONS = [
  { value: 'social', label: 'MXH' },
  { value: 'tech', label: 'Công nghệ' },
  { value: 'economy', label: 'Kinh tế' },
];

const SOURCE_OPTIONS = [
  { value: 'thread', label: 'Threads' },
  { value: 'tiktok', label: 'TikTok' },
  { value: 'manual', label: 'Khác' },
];

const ACTIVE_OPTIONS = [
  { value: 'true', label: 'Đang hiện' },
  { value: 'false', label: 'Đã ẩn' },
];

const EMPTY_FORM = {
  title: '',
  summary: '',
  url: '',
  image_url: '',
  source_type: 'thread',
  category: 'social',
  is_active: true,
};

function toForm(item) {
  return {
    title: item.title || '',
    summary: item.summary || '',
    url: item.url || '',
    image_url: item.image_url || '',
    source_type: item.source_type,
    category: item.category,
    is_active: item.is_active,
  };
}

// Blank optional fields are sent as null so an edit can clear them.
function toBody(form) {
  return {
    title: form.title.trim(),
    summary: form.summary.trim() || null,
    url: form.url.trim() || null,
    image_url: form.image_url.trim() || null,
    source_type: form.source_type,
    category: form.category,
    is_active: form.is_active,
  };
}

export default function SocialBuzzPage() {
  return (
    <main className="min-h-screen bg-paper font-body text-ink-900">
      <Header showDateControls={false} />
      <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6 lg:px-8">
        <SocialBuzzManager />
      </div>
    </main>
  );
}

function SocialBuzzManager() {
  const [category, setCategory] = useState('');
  const [active, setActive] = useState('');
  const [page, setPage] = useState(0);
  const [payload, setPayload] = useState({ total: 0, items: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(null); // null | 'new' | item
  const [reloadKey, setReloadKey] = useState(0);

  const reload = useCallback(() => setReloadKey((key) => key + 1), []);

  useEffect(() => {
    let alive = true;
    async function load() {
      setLoading(true);
      setError('');
      try {
        const next = await getSocialBuzzList({
          category,
          isActive: active,
          limit: PAGE_SIZE,
          offset: page * PAGE_SIZE,
        });
        if (alive) setPayload(next);
      } catch (err) {
        if (alive) setError(err.message || 'Không tải được danh sách tin.');
      } finally {
        if (alive) setLoading(false);
      }
    }
    load();
    return () => {
      alive = false;
    };
  }, [category, active, page, reloadKey]);

  async function toggleActive(item) {
    setError('');
    try {
      await updateSocialBuzz(item.id, { is_active: !item.is_active });
      reload();
    } catch (err) {
      setError(err.message || 'Không cập nhật được tin.');
    }
  }

  async function remove(item) {
    if (!window.confirm(`Xoá tin "${item.title}"? Tin sẽ biến mất khỏi portal và bản tin.`)) return;
    setError('');
    try {
      await deleteSocialBuzz(item.id);
      reload();
    } catch (err) {
      setError(err.message || 'Không xoá được tin.');
    }
  }

  const items = payload.items || [];
  const total = payload.total || 0;
  const pageCount = Math.max(Math.ceil(total / PAGE_SIZE), 1);

  return (
    <MetricShell eyebrow="Nội dung" title="Hóng hớt">
      <p className="-mt-2 mb-4 flex items-center gap-2 text-xs text-ink-500">
        <Flame className="h-3.5 w-3.5 text-gold" aria-hidden="true" />
        Tin hot MXH (Threads, TikTok), công nghệ, kinh tế — nhập tay cho bản tin Hóng hớt hằng ngày.
      </p>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <FilterSelect label="Category" value={category} options={CATEGORY_OPTIONS} onChange={(value) => { setCategory(value); setPage(0); }} />
        <FilterSelect label="Trạng thái" value={active} options={ACTIVE_OPTIONS} onChange={(value) => { setActive(value); setPage(0); }} />
        <button
          type="button"
          onClick={() => setEditing('new')}
          className="ml-auto inline-flex items-center gap-2 rounded-full bg-ink-900 px-4 py-2 text-xs font-semibold text-white transition hover:bg-ink-700"
        >
          <Plus className="h-3.5 w-3.5" aria-hidden="true" />
          Thêm tin
        </button>
      </div>

      {error ? <p className="mb-3 rounded-2xl border border-burgundy/30 bg-burgundy/10 p-3 text-sm text-burgundy" role="alert">{error}</p> : null}

      <div className="overflow-x-auto rounded-2xl border border-hairline">
        <table className="min-w-full divide-y divide-hairline text-sm">
          <thead className="bg-paper text-left text-[11px] uppercase tracking-[0.16em] text-ink-500">
            <tr>
              <th className="px-4 py-3">Thời gian</th>
              <th className="px-4 py-3">Tiêu đề</th>
              <th className="hidden px-4 py-3 md:table-cell">Category</th>
              <th className="hidden px-4 py-3 md:table-cell">Nguồn</th>
              <th className="px-4 py-3">Trạng thái</th>
              <th className="px-4 py-3 text-right">Thao tác</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-hairline bg-porcelain">
            {loading ? (
              <tr><td colSpan="6" className="px-4 py-10 text-center text-ink-500">Đang tải...</td></tr>
            ) : items.length === 0 ? (
              <tr><td colSpan="6" className="px-4 py-10 text-center text-ink-500">Chưa có tin nào khớp bộ lọc.</td></tr>
            ) : (
              items.map((item) => (
                <tr key={item.id} className="align-top">
                  <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-ink-500">{formatDateTime(item.created_at)}</td>
                  <td className="max-w-md px-4 py-3">
                    <p className="font-medium text-ink-900">{item.title}</p>
                    {item.summary ? <p className="mt-1 line-clamp-2 text-xs text-ink-500">{item.summary}</p> : null}
                    {item.url ? (
                      <a href={item.url} target="_blank" rel="noopener noreferrer" className="mt-1 block truncate text-[11px] text-gold hover:underline">{item.url}</a>
                    ) : null}
                  </td>
                  <td className="hidden px-4 py-3 text-xs md:table-cell">{optionLabel(CATEGORY_OPTIONS, item.category)}</td>
                  <td className="hidden px-4 py-3 text-xs md:table-cell">{optionLabel(SOURCE_OPTIONS, item.source_type)}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex rounded-full px-2.5 py-1 text-[11px] font-semibold ${item.is_active ? 'bg-sage/15 text-sage' : 'bg-ink-500/10 text-ink-500'}`}>
                      {item.is_active ? 'Đang hiện' : 'Đã ẩn'}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right">
                    <IconButton label="Sửa" onClick={() => setEditing(item)} icon={Pencil} />
                    <IconButton label={item.is_active ? 'Ẩn' : 'Hiện'} onClick={() => toggleActive(item)} icon={item.is_active ? EyeOff : Eye} />
                    <IconButton label="Xoá" onClick={() => remove(item)} icon={Trash2} danger />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-3 flex items-center justify-between text-xs text-ink-500">
        <span>{formatNumber(total)} tin</span>
        <div className="flex items-center gap-2">
          <button type="button" onClick={() => setPage((p) => p - 1)} disabled={page === 0} className="rounded-full border border-hairline p-1.5 disabled:opacity-40" aria-label="Trang trước">
            <ChevronLeft className="h-4 w-4" aria-hidden="true" />
          </button>
          <span>{page + 1}/{pageCount}</span>
          <button type="button" onClick={() => setPage((p) => p + 1)} disabled={page + 1 >= pageCount} className="rounded-full border border-hairline p-1.5 disabled:opacity-40" aria-label="Trang sau">
            <ChevronRight className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </div>

      {editing ? (
        <SocialBuzzForm
          item={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            reload();
          }}
        />
      ) : null}
    </MetricShell>
  );
}

function SocialBuzzForm({ item, onClose, onSaved }) {
  const [form, setForm] = useState(item ? toForm(item) : EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  function setField(key) {
    return (event) => {
      const value = event.target.type === 'checkbox' ? event.target.checked : event.target.value;
      setForm((prev) => ({ ...prev, [key]: value }));
    };
  }

  async function submit(event) {
    event.preventDefault();
    if (!form.title.trim()) {
      setError('Tiêu đề không được để trống.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      if (item) await updateSocialBuzz(item.id, toBody(form));
      else await createSocialBuzz(toBody(form));
      onSaved();
    } catch (err) {
      setError(err.message || 'Không lưu được tin.');
    } finally {
      setSaving(false);
    }
  }

  const inputClass = 'w-full rounded-2xl border border-hairline bg-paper px-3 py-2 text-sm text-ink-900 placeholder:text-ink-500';

  return (
    <div className="fixed inset-0 z-30 flex items-center justify-center bg-ink-900/40 p-4" role="dialog" aria-modal="true" aria-label={item ? 'Sửa tin Hóng hớt' : 'Thêm tin Hóng hớt'}>
      <form onSubmit={submit} className="max-h-[90vh] w-full max-w-xl space-y-3 overflow-y-auto rounded-3xl border border-hairline bg-porcelain p-5">
        <div className="flex items-center justify-between">
          <h3 className="font-display text-lg font-medium text-ink-900">{item ? 'Sửa tin' : 'Thêm tin mới'}</h3>
          <button type="button" onClick={onClose} className="rounded-full p-1.5 text-ink-500 hover:bg-gold-50" aria-label="Đóng">
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        <Field label="Tiêu đề *">
          <input value={form.title} onChange={setField('title')} maxLength={300} className={inputClass} required />
        </Field>
        <Field label="Tóm tắt">
          <textarea value={form.summary} onChange={setField('summary')} rows={4} maxLength={5000} className={inputClass} />
        </Field>
        <Field label="Link gốc (không bắt buộc)">
          <input type="url" value={form.url} onChange={setField('url')} placeholder="https://..." className={inputClass} />
        </Field>
        <Field label="Ảnh minh hoạ — URL (không bắt buộc)">
          <input type="url" value={form.image_url} onChange={setField('image_url')} placeholder="https://..." className={inputClass} />
        </Field>
        {form.image_url.trim().startsWith('http') ? (
          <img src={form.image_url.trim()} alt="Xem trước ảnh minh hoạ" className="max-h-40 rounded-2xl border border-hairline object-contain" />
        ) : null}

        <div className="grid grid-cols-2 gap-3">
          <Field label="Category">
            <select value={form.category} onChange={setField('category')} className={inputClass}>
              {CATEGORY_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </Field>
          <Field label="Nguồn">
            <select value={form.source_type} onChange={setField('source_type')} className={inputClass}>
              {SOURCE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </Field>
        </div>

        <label className="flex items-center gap-2 text-sm text-ink-700">
          <input type="checkbox" checked={form.is_active} onChange={setField('is_active')} />
          Hiện trong bản tin
        </label>

        {error ? <p className="rounded-2xl border border-burgundy/30 bg-burgundy/10 p-3 text-sm text-burgundy" role="alert">{error}</p> : null}

        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="rounded-full border border-hairline px-4 py-2 text-sm text-ink-700 hover:bg-gold-50">Huỷ</button>
          <button type="submit" disabled={saving} className="rounded-full bg-ink-900 px-4 py-2 text-sm font-semibold text-white hover:bg-ink-700 disabled:opacity-50">
            {saving ? 'Đang lưu...' : 'Lưu'}
          </button>
        </div>
      </form>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block space-y-1">
      <span className="text-xs font-medium text-ink-500">{label}</span>
      {children}
    </label>
  );
}

function FilterSelect({ label, value, options, onChange }) {
  return (
    <select
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="rounded-full border border-hairline bg-paper px-3 py-2 text-xs text-ink-900"
      aria-label={label}
    >
      <option value="">{label}: tất cả</option>
      {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
    </select>
  );
}

function IconButton({ label, onClick, icon: Icon, danger = false }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={label}
      aria-label={label}
      className={`ml-1 inline-flex rounded-full border border-hairline p-1.5 transition ${danger ? 'text-burgundy hover:bg-burgundy/10' : 'text-ink-700 hover:bg-gold-50'}`}
    >
      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
    </button>
  );
}
