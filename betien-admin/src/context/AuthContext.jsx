import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  changePassword as changePasswordRequest,
  clearSession,
  fetchMe,
  getStoredAdmin,
  getStoredForcePasswordChange,
  getStoredToken,
  login as loginRequest,
  logoutRequest,
  saveSession,
  setUnauthorizedHandler,
  updateStoredAdmin,
} from '../api/client';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const navigate = useNavigate();
  const [admin, setAdmin] = useState(() => getStoredAdmin());
  const [token, setToken] = useState(() => getStoredToken());
  const [forcePasswordChange, setForcePasswordChange] = useState(() => getStoredForcePasswordChange());
  const [bootstrapping, setBootstrapping] = useState(Boolean(getStoredToken()));

  const performLogout = useCallback(async ({ remote = true } = {}) => {
    if (remote && getStoredToken()) {
      try {
        await logoutRequest();
      } catch {
        // Local logout must always finish even when the session is already expired.
      }
    }
    clearSession();
    setAdmin(null);
    setToken(null);
    setForcePasswordChange(false);
    navigate('/login', { replace: true });
  }, [navigate]);

  useEffect(() => {
    setUnauthorizedHandler(() => performLogout({ remote: false }));
    return () => setUnauthorizedHandler(null);
  }, [performLogout]);

  useEffect(() => {
    let alive = true;
    async function hydrate() {
      if (!getStoredToken()) {
        setBootstrapping(false);
        return;
      }
      try {
        const currentAdmin = await fetchMe();
        if (!alive) return;
        updateStoredAdmin(currentAdmin);
        setAdmin(currentAdmin);
        setForcePasswordChange(Boolean(currentAdmin.force_password_change));
      } catch {
        if (alive) {
          clearSession();
          setAdmin(null);
          setToken(null);
          setForcePasswordChange(false);
        }
      } finally {
        if (alive) setBootstrapping(false);
      }
    }
    hydrate();
    return () => {
      alive = false;
    };
  }, []);

  const login = useCallback(async (email, password) => {
    const payload = await loginRequest(email, password);
    saveSession(payload);
    setAdmin(payload.admin);
    setToken(payload.access_token);
    setForcePasswordChange(Boolean(payload.force_password_change));
    return payload;
  }, []);

  const changePassword = useCallback(async (currentPassword, newPassword) => {
    const updatedAdmin = await changePasswordRequest(currentPassword, newPassword);
    updateStoredAdmin(updatedAdmin);
    setAdmin(updatedAdmin);
    setForcePasswordChange(false);
    return updatedAdmin;
  }, []);

  const value = useMemo(() => ({
    admin,
    token,
    isAuthenticated: Boolean(token),
    forcePasswordChange,
    bootstrapping,
    login,
    logout: performLogout,
    changePassword,
  }), [admin, token, forcePasswordChange, bootstrapping, login, performLogout, changePassword]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside AuthProvider');
  return context;
}
