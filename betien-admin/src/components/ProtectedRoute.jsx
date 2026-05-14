import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function ProtectedRoute({ allowRestricted = false }) {
  const { isAuthenticated, forcePasswordChange, bootstrapping } = useAuth();
  const location = useLocation();

  if (bootstrapping) {
    return (
      <div className="min-h-screen bg-paper p-6 font-body text-ink-900">
        <div className="mx-auto h-28 max-w-xl animate-pulse rounded-3xl border border-hairline bg-porcelain" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  if (forcePasswordChange && !allowRestricted) {
    return <Navigate to="/change-password" replace />;
  }

  if (!forcePasswordChange && location.pathname === '/change-password') {
    return <Navigate to="/" replace />;
  }

  return <Outlet />;
}
