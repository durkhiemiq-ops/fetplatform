import axios from 'axios';

export const apiBaseUrl = (base, isDevelopment) => {
  if (isDevelopment || !base) return '/api/v1';
  const normalized = base.replace(/\/+$/, '');
  return normalized.endsWith('/api/v1') ? normalized : `${normalized}/api/v1`;
};

// Credentials live ONLY in httpOnly cookies set by the backend. This client
// never reads or writes session tokens from JS-accessible storage.
const api = axios.create({
  baseURL: apiBaseUrl(import.meta.env?.VITE_API_BASE, import.meta.env?.DEV),
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
  if (typeof FormData !== 'undefined' && config.data instanceof FormData) {
    // File uploads (roster CSV) must go out as multipart/form-data with a
    // browser-generated boundary. The instance default is application/json,
    // which would otherwise be sent verbatim: Django then sees no multipart
    // body, request.FILES is empty, and the upload fails with
    // "A CSV file is required." even though a file was chosen. Deleting the
    // header lets the browser set the correct one automatically.
    config.headers = config.headers || {};
    delete config.headers['Content-Type'];
  }
  if (UNSAFE_METHODS.has(method)) {
    const token = await ensureCsrfToken();
    if (token) {
      config.headers = config.headers || {};
      config.headers['X-CSRFToken'] = token;
    }
  }
  return config;
});

// Nothing is cached in localStorage any more (AGENTS.md): identity lives in
// React state via SessionProvider, and the httpOnly session cookie is the only
// authority. This hook tells the app to
// drop to the login screen.
const notifySessionExpired = () => {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('fet-session-expired'));
  }
};

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const path = error.config?.url || '';
    const isSignInRequest = /\/(?:auth|accounts)\/(?:login|register|self-register|verify-email)\//.test(path);
    const status = error.response?.status;
    const detail = error.response?.data?.error;
    // DRF SessionAuthentication reports missing credentials as 403. Other
    // 403 responses (including CSRF and permission failures) keep the session.
    const missingSession = status === 401 || (
      status === 403 && detail?.code === 'FORBIDDEN' &&
      detail?.message === 'Authentication credentials were not provided.'
    );
    if (!isSignInRequest && missingSession) {
      notifySessionExpired();
    }
    return Promise.reject(error);
  }
);

export default api;
