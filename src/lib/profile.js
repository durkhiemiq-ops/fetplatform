import api from './api';
import { authApi } from './auth';

// normalizeRole is defined once, in the session layer, and re-exported here
// because most call sites already import it from this module.
export { normalizeRole } from '../context/SessionContext';

const unwrap = (res) => (res?.data && typeof res.data === 'object' && 'data' in res.data ? res.data.data : res?.data);

export const profileApi = {
  me: () => authApi.me().then(unwrap),
  updateMe: (data) => api.patch('/auth/me/', data).then(unwrap),
  activity: (studentId) =>
    api.get(studentId ? `/students/${studentId}/activity/` : '/students/me/activity/').then(unwrap),
};

export default profileApi;