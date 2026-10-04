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
};

/** Administrator decision on a pending lecturer application. */
export const lecturerApprovalApi = {
  decide: async (userId, decision, reason = '') =>
    unwrap(await api.post(`/accounts/lecturers/${userId}/approval/`, { decision, reason })),
};

export default authApi;