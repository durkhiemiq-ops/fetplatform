import api from './api';

const unwrap = (res) => {
  const body = res?.data;
  if (body && typeof body === 'object' && 'data' in body) return body.data;
  return body;
};

// Deliberately absent from this client: `myCourses`, `scan`, `manualAttendance`,
// `deleteRecord` and `studentOfClass`. Each had no caller anywhere in the app —
// QRScanner posts to /attendance/scan/ itself on the shared axios instance —
// and neither permanent record deletion nor manual attendance is a supported
// MVP surface, so a helper for them would only advertise a route the backend
// does not offer.
export const attendanceApi = {
  // Lecturer: the offerings they teach (used to launch sessions)
  lecturerCourses: () => api.get('/lecturers/me/courses/').then(unwrap),

  // Start a flexible attendance session (creates ClassSession + AttendanceSession)
  startFlex: (data) => api.post('/attendance/start-flex/', data).then(unwrap),

  // Live status of a session (eligible, present, remaining, headcount)
  status: (sessionId) => api.get(`/attendance/${sessionId}/`).then(unwrap),
  // The lecturer's own sessions (survives a page reload)
  mySessions: () => api.get('/attendance/sessions/').then(unwrap),
  closeSession: (sessionId) => api.post(`/attendance/${sessionId}/close/`).then(unwrap),

  // Checkpoints (stations)
  checkpoints: (sessionId) =>
    api.get(`/attendance/${sessionId}/`).then(unwrap).then((data) => data?.checkpoints || []),
  createCheckpoints: (sessionId, studentIds) =>
    api.post(`/attendance/${sessionId}/checkpoints/`, { student_ids: studentIds }).then(unwrap),
  removeCheckpoint: (sessionId, checkpointId) =>
    api.delete(`/attendance/${sessionId}/checkpoints/${checkpointId}/`).then(unwrap),
  autoSelectStations: (sessionId, count = 3) =>
    api.post(`/attendance/${sessionId}/checkpoints/auto-select/`, { count }).then(unwrap),

  // Issue the code the room scans. The session's mode decides the contract:
  // a PROJECTOR session mints the room's single 10-second code, while a
  // STATIONS session hands out the next unmarked station's code. The client
  // never supplies a student identity; scope and binding are server-derived.
  generateTokens: async (sessionId) => {
    const detail = await api.get(`/attendance/${sessionId}/`).then(unwrap);
    if (detail?.mode === 'PROJECTOR') {
      const token = await api.post(`/attendance/${sessionId}/token/`).then(unwrap);
      return {
        tokens: [{ token: token.token }],
        expires_in_seconds: token.ttl_seconds || token.expires_in_seconds || 10,
      };
    }
    const checkpoint = (detail?.checkpoints || []).find((row) => !row.marked);
    if (!checkpoint) {
      throw new Error('Select at least one unmarked student before projecting a QR code.');
    }
    const token = await api.post(`/attendance/checkpoints/${checkpoint.id}/token/`).then(unwrap);
    return {
      tokens: [{ ...token, student_name: checkpoint.student_name }],
      expires_in_seconds: token.ttl_seconds,
    };
  },

  // Student acting as a station: poll fresh tokens for their QR display
  myStation: () => api.get('/students/me/station/').then(unwrap),
  myStationToken: (sessionId) => api.get(`/attendance/${sessionId}/my-station-token/`).then(unwrap),

  // Student history (points have no backend surface in the MVP)
  myAttendance: () => api.get('/students/me/attendance/').then(unwrap),

  // Lecturer helpers
  eligibleStudents: (sessionId) =>
    api.get(`/attendance/${sessionId}/`).then(unwrap).then((data) => data?.eligible_students || []),
  correctRecord: (recordId, data) => api.patch(`/attendance/records/${recordId}/`, data).then(unwrap),
  sessionRecords: (sessionId) =>
    api.get(`/attendance/${sessionId}/`).then(unwrap).then((data) => data?.records || []),
};

export default attendanceApi;