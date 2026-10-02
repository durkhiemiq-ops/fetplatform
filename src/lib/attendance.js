import api from './api';

const unwrap = (res) => {
  const body = res?.data;
  if (body && typeof body === 'object' && 'data' in body) return body.data;
  return body;
};

export const attendanceApi = {
  // Lecturer: the offerings they teach (used to launch sessions)
  lecturerCourses: () => api.get('/lecturers/me/courses/').then(unwrap),

  // Student: courses they are enrolled in
  myCourses: () => api.get('/students/me/courses/').then(unwrap),

  // Start a flexible attendance session (creates ClassSession + AttendanceSession)
  startFlex: (data) => api.post('/attendance/start-flex/', data).then(unwrap),

  // Live status of a session (eligible, present, remaining, headcount)
  status: (sessionId) => api.get(`/attendance/${sessionId}/`).then(unwrap),
  // The lecturer's own sessions (survives a page reload)
  mySessions: () => api.get('/attendance/sessions/').then(unwrap),
  closeSession: (sessionId) => api.post(`/attendance/${sessionId}/close/`).then(unwrap),

  // Checkpoints (stations)
  checkpoints: (sessionId) => api.get(`/attendance/${sessionId}/checkpoints/`).then(unwrap),
  createCheckpoints: (sessionId, studentIds) =>
    api.post(`/attendance/${sessionId}/checkpoints/`, { student_ids: studentIds }).then(unwrap),
  removeCheckpoint: (sessionId, checkpointId) =>
    api.delete(`/attendance/${sessionId}/checkpoints/${checkpointId}/`).then(unwrap),
  autoSelectStations: (sessionId, count = 3) =>
    api.post(`/attendance/${sessionId}/checkpoints/auto-select/`, { count }).then(unwrap),

  // Tokens (projector rotation)
  generateTokens: (sessionId) => api.post(`/attendance/${sessionId}/tokens/`).then(unwrap),

  // Student scans a QR token
  scan: (token) => api.post('/attendance/scan/', { token }).then(unwrap),

  // Student acting as a station: poll fresh tokens for their QR display
  myStation: () => api.get('/students/me/station/').then(unwrap),
  myStationToken: (sessionId) => api.get(`/attendance/${sessionId}/my-station-token/`).then(unwrap),

  // Student history + points
  myAttendance: () => api.get('/students/me/attendance/').then(unwrap),
  myPoints: () => api.get('/students/me/points/').then(unwrap),

  // Lecturer helpers
  eligibleStudents: (classSessionId) => api.get(`/class-sessions/${classSessionId}/eligible-students/`).then(unwrap),
  manualAttendance: (sessionId, data) => api.post(`/attendance/${sessionId}/manual/`, data).then(unwrap),
  correctRecord: (recordId, data) => api.patch(`/attendance/records/${recordId}/`, data).then(unwrap),
  deleteRecord: (recordId) => api.delete(`/attendance/records/${recordId}/`).then(unwrap),
  studentOfClass: (sessionId) => api.post(`/attendance/${sessionId}/student-of-class/`).then(unwrap),
  sessionRecords: (classSessionId) =>
    api.get(`/class-sessions/${classSessionId}/attendance/records/`).then(unwrap),
};

export default attendanceApi;