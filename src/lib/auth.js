import api from './api';

const unwrap = (res) => {
  const body = res?.data;
  if (body && typeof body === 'object' && 'data' in body) return body.data;
  return body;
};

export const authApi = {
  login: (credentials) => api.post('/auth/login/', credentials),
  logout: () => api.post('/auth/logout/'),
  me: () => api.get('/auth/me/'),
  refresh: () => api.post('/auth/refresh/'),
  changePassword: (data) => api.post('/auth/change-password/', data),
};

/**
 * Public self-registration.
 *
 * Unauthenticated by design: this is the one endpoint an anonymous caller may
 * reach. The payload carries `account_type` (`student` | `lecturer`) — a
 * *request*, never an authorization. The server resolves the stored role and
 * creates lecturer applicants PENDING, so no field here can grant a privilege.
 *
 * There is deliberately no `role` parameter to pass, forged or otherwise.
 */
export const publicApi = {
  register: async (payload) => unwrap(await api.post('/auth/self-register/', payload)),
  verifyEmail: async (payload) => unwrap(await api.post('/auth/verify-email/', payload)),
  resendVerification: async (email) => unwrap(await api.post('/auth/resend-verification/', { email })),
  forgotPassword: async (email) => unwrap(await api.post('/auth/forgot-password/', { email })),
  resetPassword: async (payload) => unwrap(await api.post('/auth/reset-password/', payload)),
};

/** Administrator decision on a pending lecturer application. */
export const lecturerApprovalApi = {
  /**
   * The lecturer roster, administrator-only (`GET /accounts/lecturers/`).
   *
   * `lecturer_approval_status` is server-owned: PENDING for a self-registered
   * applicant, APPROVED/REJECTED once decided, and null for a lecturer that did
   * not apply through the portal (pre-existing rows, admin-created, roster).
   * Null is not a third decision state and is rendered as such.
   *
   * The endpoint is paginated with the project's standard paginator, so it
   * answers `{count, next, previous, results}`. Following `next` keeps the
   * approval queue complete instead of silently showing only the first page —
   * an admin deciding on a subset of applicants is a correctness problem, not
   * a cosmetic one.
   */
  list: async () => {
    const rows = [];
    let page = unwrap(await api.get('/accounts/lecturers/'));
    // Bounded so a malformed `next` cannot spin forever.
    for (let guard = 0; guard < 50; guard += 1) {
      if (Array.isArray(page)) {
        rows.push(...page);
        break;
      }
      rows.push(...(page?.results ?? []));
      if (!page?.next) break;
      // DRF returns an absolute `next`. Keep the request on the configured
      // base URL (and therefore on the same origin / proxy) by forwarding only
      // its query string.
      const query = String(page.next).split('?')[1];
      if (!query) break;
      page = unwrap(await api.get(`/accounts/lecturers/?${query}`));
    }
    return rows;
  },
  decide: async (userId, decision, reason = '') =>
    unwrap(await api.post(`/accounts/lecturers/${userId}/approval/`, { decision, reason })),
};

export default authApi;
