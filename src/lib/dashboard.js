import api from './api';

const toData = async (promise) => {
  const res = await promise;
  const body = res?.data;
  if (body && typeof body === 'object' && 'data' in body) return body.data;
  return body;
};

/**
 * The aggregated dashboard endpoint.
 *
 * The backend picks the payload by role, so this one call replaces a fan-out to
 * five separate endpoints and the client never has to branch on role to fetch:
 *
 *   STUDENT   stats, courses, today_classes, announcements,
 *             active_projects, pending_tasks, attendance
 *   LECTURER  today_classes, my_courses, active_projects
 *   ADMIN     total_users, total_students, total_lecturers
 */
export const dashboardApi = {
  get: () => toData(api.get('/dashboard/')),
};

export default dashboardApi;
