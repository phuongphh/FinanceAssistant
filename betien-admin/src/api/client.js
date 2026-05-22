const API_BASE = import.meta.env.VITE_API_BASE || '/api/admin';
const TOKEN_KEY = 'betien_admin_token';
const ADMIN_KEY = 'betien_admin_user';
const FORCE_PASSWORD_KEY = 'betien_admin_force_password_change';

let onUnauthorized = null;

export function getApiBase() {
  return API_BASE;
}

export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

export function getStoredToken() {
  return window.localStorage.getItem(TOKEN_KEY);
}

export function getStoredAdmin() {
  const raw = window.localStorage.getItem(ADMIN_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    clearSession();
    return null;
  }
}

export function getStoredForcePasswordChange() {
  return window.localStorage.getItem(FORCE_PASSWORD_KEY) === 'true';
}

export function saveSession({ access_token: token, admin, force_password_change: forcePasswordChange }) {
  window.localStorage.setItem(TOKEN_KEY, token);
  window.localStorage.setItem(ADMIN_KEY, JSON.stringify(admin));
  window.localStorage.setItem(FORCE_PASSWORD_KEY, String(Boolean(forcePasswordChange)));
}

export function updateStoredAdmin(admin) {
  window.localStorage.setItem(ADMIN_KEY, JSON.stringify(admin));
  window.localStorage.setItem(FORCE_PASSWORD_KEY, String(Boolean(admin?.force_password_change)));
}

export function clearSession() {
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(ADMIN_KEY);
  window.localStorage.removeItem(FORCE_PASSWORD_KEY);
}

function safeErrorMessage(payload, fallback) {
  const detail = payload?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length > 0) return detail[0]?.msg || fallback;
  return fallback;
}

export async function apiFetch(path, options = {}) {
  const token = getStoredToken();
  const headers = new Headers(options.headers || {});
  headers.set('Accept', 'application/json');
  if (!(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  if (token) headers.set('Authorization', `Bearer ${token}`);

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    cache: 'no-store',
    headers,
  });

  let payload = null;
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) payload = await response.json();

  if (response.status === 401) {
    clearSession();
    onUnauthorized?.();
  }

  if (!response.ok) {
    const error = new Error(safeErrorMessage(payload, 'Không tải được dữ liệu.'));
    error.status = response.status;
    error.payload = payload;
    throw error;
  }

  return payload;
}

export function login(email, password) {
  return apiFetch('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
}

export function fetchMe() {
  return apiFetch('/auth/me');
}

export function logoutRequest() {
  return apiFetch('/auth/logout', { method: 'POST' });
}

export function changePassword(currentPassword, newPassword) {
  return apiFetch('/auth/change-password', {
    method: 'POST',
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
}
