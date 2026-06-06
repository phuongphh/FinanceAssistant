import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import { AuthProvider } from './context/AuthContext';
import './styles.css';

// SPA is served at both / (legacy bookmarks) and /admin/ (canonical, matches
// Cloudflare ingress). Detect at runtime so React Router treats /admin/login
// as /login instead of falling through to the catch-all `*` route.
const routerBasename = window.location.pathname.startsWith('/admin') ? '/admin' : '/';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter basename={routerBasename}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
