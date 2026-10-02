import api from './api';

const toData = async (promise) => {
  const res = await promise;
  const body = res?.data;
  if (body && typeof body === 'object' && 'data' in body) return body.data;
  return body;
};

/**
 * Reference data and the weekly timetable.
 *
 * `departments` and `semesters` are mounted at the API root, not under an
 * `/academics/` prefix -- `apps/core/urls.py` includes these urlconf modules at
 * the root, so `/departments/` and `/semesters/` are the real paths.
 */
export const academicsApi = {
  // --- reference data ---
  departments: () => toData(api.get('/departments/')),
  publicDepartments: () => toData(api.get('/departments/public/')),
  createDepartment: (data) => toData(api.post('/departments/create/', data)),

  semesters: () => toData(api.get('/semesters/')),
  // Only administrators may activate; the backend rejects everyone else.
  activateSemester: (semesterId) => toData(api.post(`/semesters/${semesterId}/activate/`)),

  // Counts for the admin dashboard. The backend wraps this in { data: ... }.
  adminStats: () => toData(api.get('/admin/stats/')),

  // --- weekly timetable ---
  schedules: (offeringId) => toData(api.get(`/course-offerings/${offeringId}/schedules/`)),
  createSchedule: (offeringId, data) => toData(api.post(`/course-offerings/${offeringId}/schedules/`, data)),
  deleteSchedule: (scheduleId) => api.delete(`/schedules/${scheduleId}/`),
};

export const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

export default academicsApi;
