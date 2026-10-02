/**
 * API Client — Axios instance with interceptors for session-based auth.
 *
 * - Attaches CSRF token from cookie on mutating requests.
 * - Unwraps the {success, data, error} envelope returned by Django REST views.
 * - Handles 403, 404, 409, 429 and 500 responses.
 *
 * @module api/client
 */

import axios from 'axios';

/**
 * M1: the base URL comes from the environment with NO silent fallback.
 *
 * The previous `|| 'http://localhost:8000/api/v1'` meant a missing .env flipped
 * the app from the same-origin Vite proxy to a cross-origin request, where
 * SESSION_COOKIE_SAMESITE=Lax + CORS_ALLOW_CREDENTIALS is untested and breaks
 * session auth. Fail loudly at startup rather than guessing a backend URL.
 */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;
if (!API_BASE_URL) {
  throw new Error(
    'VITE_API_BASE_URL is not set.\n' +
      'Create Attendî/.env containing:\n' +
      '  VITE_API_BASE_URL=/api/v1\n' +
      'Refusing to guess a backend URL — a cross-origin fallback breaks session auth.'
  );
}

/**
 * Read a cookie value by name.
 * @param {string} name
 * @returns {string|null}
 */
function getCookie(name) {
  const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
  return match ? decodeURIComponent(match[2]) : null;
}

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

/**
 * Request interceptor — attaches CSRF token to mutating requests.
 * The token comes from the readable `csrftoken` cookie, which is correct
 * because CSRF_COOKIE_HTTPONLY is False.
 */
apiClient.interceptors.request.use(
  (config) => {
    const method = config.method?.toUpperCase();
    if (method && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
      const csrfToken = getCookie('csrftoken');
      if (csrfToken) {
        config.headers['X-CSRFToken'] = csrfToken;
      }
    }
    return config;
  },
  (error) => Promise.reject(error)
);

/**
 * Notified when the backend reports the session is gone, so the app can return
 * to the login screen IN-REACT rather than reloading the page.
 */
let onSessionExpired = null;
export function setSessionExpiredHandler(handler) {
  onSessionExpired = handler;
}

/**
 * Response interceptor — unwraps the {success, data, error} envelope and
 * normalizes error codes.
 */
apiClient.interceptors.response.use(
  (response) => {
    const body = response.data;
    if (body && typeof body === 'object' && 'success' in body) {
      if (body.success) {
        return { ...response, data: body.data };
      }
      const err = new Error(body.error?.message || 'Request failed');
      err.code = body.error?.code || 'UNKNOWN';
      err.status = response.status;
      return Promise.reject(err);
    }
    return response;
  },
  (error) => {
    if (error.response) {
      const { status, data } = error.response;
      const message = data?.error?.message || data?.detail || 'An error occurred';
      const code = data?.error?.code;

      // M2: DRF's SessionAuthentication answers UNAUTHENTICATED requests with
      // 403, not 401. Distinguish "not signed in" from "signed in but not
      // allowed" using the code, and only tear the session down for the former.
      // The old `window.location.href='/'` on 401 was dead code that would also
      // have discarded React state (including the in-memory OTP credentials).
      //
      // A 401 that CARRIES a code is not a lost session: the backend sends
      // INVALID_CREDENTIALS when a sign-in is rejected. Collapsing those into
      // "Session expired" made a wrong password read as a broken login, and
      // discarded the backend's own reason. Only a bare 401 (no code) is
      // treated as an expired session; coded 401s fall through to the generic
      // handler below, which preserves the server's message and code.
      if (code === 'UNAUTHENTICATED' || (status === 401 && !code)) {
        if (typeof onSessionExpired === 'function') onSessionExpired();
        const err = new Error('Session expired. Please log in again.');
        err.status = status;
        err.code = code || 'UNAUTHENTICATED';
        return Promise.reject(err);
      }

      if (status === 403) {
        const err = new Error(message || 'You do not have permission to perform this action.');
        err.status = status;
        err.code = code || 'FORBIDDEN';
        return Promise.reject(err);
      }

      const err = new Error(message);
      err.status = status;
      err.code = code || `HTTP_${status}`;
      return Promise.reject(err);
    }
    return Promise.reject(new Error('Network error. Please check your connection.'));
  }
);

export default apiClient;
