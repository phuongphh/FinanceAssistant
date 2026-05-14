import { useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { LockKeyhole, Mail } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export default function LoginPage() {
  const { isAuthenticated, forcePasswordChange, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  if (isAuthenticated) {
    return <Navigate to={forcePasswordChange ? '/change-password' : '/'} replace />;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError('');
    setLoading(true);
    try {
      const payload = await login(email, password);
      const target = payload.force_password_change ? '/change-password' : location.state?.from?.pathname || '/';
      navigate(target, { replace: true });
    } catch (err) {
      setError(err.message || 'Đăng nhập thất bại.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-paper px-4 py-10 font-body text-ink-900">
      <section className="w-full max-w-md rounded-[2rem] border border-hairline bg-porcelain p-8 shadow-hairline">
        <div className="mb-8">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-gold">Internal console</p>
          <h1 className="mt-3 font-display text-4xl font-semibold">Đăng nhập Admin</h1>
          <p className="mt-3 text-sm leading-6 text-ink-500">Dành riêng cho operator Bé Tiền. Phiên đăng nhập có thời hạn ngắn để bảo vệ dữ liệu user.</p>
        </div>

        <form className="space-y-4" onSubmit={handleSubmit}>
          <label className="block text-sm font-medium text-ink-700" htmlFor="email">
            Email
            <span className="mt-2 flex items-center gap-2 rounded-2xl border border-hairline bg-white px-4 py-3 focus-within:border-gold">
              <Mail className="h-4 w-4 text-gold" aria-hidden="true" />
              <input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="w-full bg-transparent text-sm outline-none placeholder:text-ink-500"
                placeholder="phuong@betien.vn"
              />
            </span>
          </label>

          <label className="block text-sm font-medium text-ink-700" htmlFor="password">
            Mật khẩu
            <span className="mt-2 flex items-center gap-2 rounded-2xl border border-hairline bg-white px-4 py-3 focus-within:border-gold">
              <LockKeyhole className="h-4 w-4 text-gold" aria-hidden="true" />
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="w-full bg-transparent text-sm outline-none placeholder:text-ink-500"
                placeholder="••••••••••••"
              />
            </span>
          </label>

          {error ? (
            <p className="rounded-2xl border border-burgundy/30 bg-burgundy/10 px-4 py-3 text-sm text-burgundy" role="alert">
              {error}
            </p>
          ) : null}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-full bg-ink-900 px-5 py-3 text-sm font-semibold text-white transition hover:bg-ink-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {loading ? 'Đang đăng nhập…' : 'Đăng nhập'}
          </button>
        </form>
      </section>
    </main>
  );
}
