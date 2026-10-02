import api from './api';
import { authApi } from './auth';

const unwrap = (res) => (res?.data && typeof res.data === 'object' && 'data' in res.data ? res.data.data : res?.data);

export const profileApi = {
  me: () => authApi.me().then(unwrap),
  updateMe: (data) => api.patch('/auth/me/', data).then(unwrap),
  activity: (studentId) =>
    api.get(studentId ? `/students/${studentId}/activity/` : '/students/me/activity/').then(unwrap),
};

export const normalizeRole = (role) => {
  const r = (role || '').toLowerCase();
  if (r === 'student' || r === 'lecturer') return r;
  // The backend emits User.Role.ADMINISTRATOR ('ADMINISTRATOR' -- see
  // backend/apps/accounts/models.py). The old check was `r.endsWith('_admin')`,
  // which is FALSE for 'administrator'. So every real administrator normalised
  // to 'administrator', matched no branch anywhere, and RequireRole bounced
  // them off all four /admin/* routes. Only the lowercase 'admin', which the
  // server never sends, used to work.
  if (r === 'admin' || r === 'administrator' || r.endsWith('_admin')) return 'admin';
  return r || 'student';
};

export default profileApi;