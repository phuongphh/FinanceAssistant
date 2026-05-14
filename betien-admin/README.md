# Bé Tiền Admin Console

Phase 4.2.5 Epic 4 frontend foundation for the internal Admin Observability Layer.

## Stack

- Vite + React 18
- Tailwind CSS with Bé Tiền editorial tokens
- React Router protected routes
- Native Fetch API client for `/api/admin/*`
- Recharts + Lucide React ready for dashboard components

## Install

```bash
npm install
```

## Development

```bash
npm run dev
```

Vite proxies `/api` to `http://localhost:8000`, so the default API base is `/api/admin`.

Optional production API override:

```bash
VITE_API_BASE=https://admin.betien.vn/api/admin npm run build
```

## Build

```bash
npm run build
```

Output is written to `dist/`. Deployment can copy `dist/*` into the backend static admin directory when Epic 6 wires production serving.

## Auth behavior

- Access tokens are stored in `localStorage` per the Phase 4.2.5 story scope.
- `AuthProvider` hydrates `/auth/me` on reload.
- 401 responses clear local session state and send the operator back to `/login`.
- `force_password_change=true` restricts the operator to `/change-password` until the password is updated.
