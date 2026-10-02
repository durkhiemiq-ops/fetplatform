import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

// Credentials live ONLY in httpOnly cookies set by the backend. This client
// never reads or writes session tokens from JS-accessible storage, so an XSS
// cannot steal them.
const api = axios.create({
  baseURL: `${API_BASE}/api/v1`,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

const UNSAFE_METHODS = new Set(['post', 'put', 'patch', 'delete']);

const readCookie = (name) =>
  document.cookie
    .split('; ')
    .find((row) => row.startsWith(`${name}=`))
    ?.split('=')[1] ?? null;

const decode = (value) => {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
};

const csrfToken = () => {
  const raw = readCookie('csrftoken');
  return raw ? decode(raw) : null;
};

let csrfReady = null;

// The backend authenticates with a Django session cookie, so every unsafe
// request is CSRF-enforced. GET /accounts/csrf/ both returns the token and
// sets the `csrftoken` cookie (CSRF_COOKIE_HTTPONLY is False, so JS can read
// it). Fetch it once, lazily, and memoise the in-flight promise so parallel
// requests do not each trigger a round trip.
const ensureCsrfToken = () => {
  if (csrfToken()) return Promise.resolve(csrfToken());
  if (!csrfReady) {
    csrfReady = api
      .get('/accounts/csrf/')
      .then(() => csrfToken())
      .finally(() => {
        csrfReady = null;
      });
  }
  return csrfReady;
};

api.interceptors.request.use(async (config) => {
  const method = (config.method || 'get').toLowerCase();
  if (UNSAFE_METHODS.has(method)) {
    const token = await ensureCsrfToken();
    if (token) {
      config.headers = config.headers || {};
      config.headers['X-CSRFToken'] = token;
    }
  }
  return config;
});

const clearAuthCache = () => {
  localStorage.removeItem('fet_auth');
  localStorage.removeItem('fet_user');
  localStorage.removeItem('fet_user_role');
  localStorage.removeItem('fet_user_name');
};

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (error.response?.status === 401 && originalRequest && !originalRequest._retry) {
      originalRequest._retry = true;
      try {
        // Session auth has no rotating token; this endpoint reports whether the
        // session is still alive so the retry below is meaningful.
        await ensureCsrfToken();
        await api.post('/auth/refresh/', null);
        return api(originalRequest);
      } catch {
        clearAuthCache();
        if (window.location.pathname !== '/login') {
          window.location.href = '/login';
        }
      }
    }
    return Promise.reject(error);
  }
);

export default api;