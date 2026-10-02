import api from './api';

const toData = async (promise) => {
  const res = await promise;
  return res?.data && typeof res.data === 'object' && 'data' in res.data ? res.data.data : res?.data;
};

export const announcementsApi = {
  list: (params) => toData(api.get('/announcements/', { params })),
  listForCourse: (offeringId) => toData(api.get('/announcements/', { params: { course_offering_id: offeringId } })),
  create: (data) => toData(api.post('/announcements/', data)),
  update: (id, data) => toData(api.patch(`/announcements/${id}/`, data)),
  remove: (id) => api.delete(`/announcements/${id}/`),

  // Pinning goes through its own endpoint so a client can never set it
  // as a side effect of creating or editing an announcement.
  setPinned: (id, pinned) => toData(api.post(`/announcements/${id}/pin/`, { pinned })),

  // Read receipts. Marking read is idempotent, so it is safe to call on open.
  markRead: (id) => toData(api.post(`/announcements/${id}/read/`)),
  readers: (id) => toData(api.get(`/announcements/${id}/readers/`)),
  readState: () => toData(api.get('/announcements/read-state/')),
};
