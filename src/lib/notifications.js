import api from './api';

const toData = async (promise) => {
  const res = await promise;
  const body = res?.data;
  if (body && typeof body === 'object' && 'data' in body) return body.data;
  return body;
};

/**
 * In-app notifications.
 *
 * These are produced by the backend without being asked -- attendance
 * checkpoints and points writes both create them (apps/attendance/points.py,
 * token_store.py) -- so this screen is the only place they are ever seen.
 */
export const notificationsApi = {
  // The backend caps the list at 50 and supports ?unread=true.
  list: (unreadOnly = false) =>
    toData(api.get('/notifications/', unreadOnly ? { params: { unread: 'true' } } : undefined)),
  markRead: (notificationId) => toData(api.patch(`/notifications/${notificationId}/read/`)),
  markAllRead: () => toData(api.post('/notifications/read-all/')),
};

export default notificationsApi;
