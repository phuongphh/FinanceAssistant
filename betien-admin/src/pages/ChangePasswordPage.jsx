import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ShieldAlert } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export default function ChangePasswordPage() {
  const { changePassword } = useAuth();
  const navigate = useNavigate();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError('');
    if (newPassword !== confirmPassword) {
      setError('Mật khẩu xác nhận chưa khớp.');
      return;
    }
    if (newPassword.length < 12 || !/[A-Za-zÀ-ỹ]/.test(newPassword) || !/\d/.test(newPassword)) {
      setError('Mật khẩu mới cần tối thiểu 12 ký tự, có chữ và số.');
      return;
    }
    setLoading(true);
    try {
      await changePassword(currentPassword, newPassword);
      navigate('/', { replace: true });
    } catch (err) {
      setError(err.message || 'Không đổi được mật khẩu.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-paper px-4 py-10 font-body text-ink-900">
      <section className="w-full max-w-lg rounded-[2rem] border border-hairline bg-porcelain p-8 shadow-hairline">
        <div className="mb-8 flex gap-4">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gold-50 text-gold">
            <ShieldAlert className="h-6 w-6" aria-hidden="true" />
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-gold">Security required</p>
            <h1 className="mt-2 font-display text-3xl font-semibold">Đổi mật khẩu lần đầu</h1>
            <p className="mt-2 text-sm leading-6 text-ink-500">Tài khoản đang ở chế độ restricted. Vui lòng đổi mật khẩu trước khi xem dashboard.</p>
          </div>
        </div>

        <form className="space-y-4" onSubmit={handleSubmit}>
          <PasswordField id="current" label="Mật khẩu hiện tại" value={currentPassword} onChange={setCurrentPassword} autoComplete="current-password" />
          <PasswordField id="new" label="Mật khẩu mới" value={newPassword} onChange={setNewPassword} autoComplete="new-password" />
          <PasswordField id="confirm" label="Xác nhận mật khẩu mới" value={confirmPassword} onChange={setConfirmPassword} autoComplete="new-password" />

          {error ? <p className="rounded-2xl border border-burgundy/30 bg-burgundy/10 px-4 py-3 text-sm text-burgundy" role="alert">{error}</p> : null}

          <button type="submit" disabled={loading} className="w-full rounded-full bg-ink-900 px-5 py-3 text-sm font-semibold text-white transition hover:bg-ink-700 disabled:cursor-not-allowed disabled:opacity-60">
            {loading ? 'Đang cập nhật…' : 'Cập nhật mật khẩu'}
          </button>
        </form>
      </section>
    </main>
  );
}

function PasswordField({ id, label, value, onChange, autoComplete }) {
  return (
    <label className="block text-sm font-medium text-ink-700" htmlFor={id}>
      {label}
      <input
        id={id}
        type="password"
        required
        autoComplete={autoComplete}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-2 w-full rounded-2xl border border-hairline bg-white px-4 py-3 text-sm outline-none transition focus:border-gold"
      />
    </label>
  );
}
