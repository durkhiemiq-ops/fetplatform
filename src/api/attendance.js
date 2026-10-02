/**
 * Attendance API — full attendance lifecycle, endpoint for every surface.
 *
 * Students scan a short-lived checkpoint QR (identity is never sent — the
 * backend derives it from the session) and read their own history.
 * Lecturers start/close sessions, select checkpoints, issue QR tokens,
 * monitor records, correct them (audited), and review BR-064 flags.
 *
 * Every function rejects with an Error carrying `.code` (e.g. TOKEN_EXPIRED,
 * SESSION_ALREADY_ACTIVE, CHECKPOINT_REJECTED, UNAUTHORIZED, RATE_LIMITED)
 * from the standard error envelope.
 *
 * @module api/attendance
 */

import apiClient from './client';
import { ATTENDANCE_ENDPOINTS } from './endpoints';

/**
 * Submit a QR token to record attendance for the logged-in student.
 * @param {string} token - Raw QR content from the lecturer's checkpoint.
 * @returns {Promise<{attendance_record_id: string, attendance_session_id: string, recorded_at: string}>}
 */
export async function scanAttendance(token) {
  const response = await apiClient.post(ATTENDANCE_ENDPOINTS.SCAN, { token });
  return response.data;
}

/**
 * List attendance sessions (lecturer: their classes; admin: all).
 * ACADEMIC USERS ONLY — a student receives 403 UNAUTHORIZED. Callers must
 * role-gate this (see AppContext.reload).
 * @returns {Promise<Array>}
 */
export async function listSessions() {
  const response = await apiClient.get(ATTENDANCE_ENDPOINTS.SESSIONS);
  return response.data;
}

/**
 * Start an attendance session for a class the lecturer teaches.
 * @param {string} classSessionId - UUID of the ClassSession.
 * @param {number} [durationSeconds] - 10-600; defaults to server setting (60).
 * @returns {Promise<{id: string, status: string, started_at: string, expires_at: string}>}
 */
export async function startSession(classSessionId, durationSeconds) {
  const payload = { class_session: classSessionId };
  if (durationSeconds != null) payload.duration_seconds = durationSeconds;
  const response = await apiClient.post(ATTENDANCE_ENDPOINTS.SESSIONS, payload);
  return response.data;
}

/**
 * Full session detail: checkpoints + records + corrections + eligible roster.
 * @param {string} sessionId
 * @returns {Promise<Object>}
 */
export async function getSessionDetail(sessionId) {
  const response = await apiClient.get(ATTENDANCE_ENDPOINTS.SESSION_DETAIL(sessionId));
  return response.data;
}

/**
 * Close an active attendance session (owner or admin).
 * @param {string} sessionId
 * @returns {Promise<{id: string, status: string}>}
 */
export async function closeSession(sessionId) {
  const response = await apiClient.post(ATTENDANCE_ENDPOINTS.SESSION_CLOSE(sessionId));
  return response.data;
}

/**
 * Confirm which physically-present students become checkpoints (BR-050/051).
 * @param {string} sessionId
 * @param {string[]} studentIds - Eligible students selected as checkpoints.
 * @returns {Promise<{checkpoints: Array}>}
 */
export async function selectCheckpoints(sessionId, studentIds) {
  const response = await apiClient.post(ATTENDANCE_ENDPOINTS.SESSION_CHECKPOINTS(sessionId), {
    student_ids: studentIds,
  });
  return response.data;
}

/**
 * The lecturer's QR generator: one short-TTL token for one confirmed checkpoint.
 * @param {string} checkpointId
 * @returns {Promise<{token: string, ttl_seconds: number}>}
 */
export async function issueCheckpointToken(checkpointId) {
  const response = await apiClient.post(ATTENDANCE_ENDPOINTS.CHECKPOINT_TOKEN(checkpointId));
  return response.data;
}

/**
 * Attendance records: students get their own; academics their classes'.
 * @param {string} [sessionId] - For academics, scope to one session.
 * @returns {Promise<Array>}
 */
export async function listRecords(sessionId) {
  const params = sessionId ? { params: { session: sessionId } } : undefined;
  const response = await apiClient.get(ATTENDANCE_ENDPOINTS.RECORDS, params);
  return response.data;
}

/**
 * Append a traceable correction to an attendance record (BR-042).
 * @param {string} recordId
 * @param {string} reason
 * @returns {Promise<Object>}
 */
export async function submitCorrection(recordId, reason) {
  const response = await apiClient.post(ATTENDANCE_ENDPOINTS.RECORD_CORRECTIONS(recordId), { reason });
  return response.data;
}

/**
 * BR-064 'Attendance Requiring Review' flags for the caller's classes.
 * @returns {Promise<Array>}
 */
export async function listReviewFlags() {
  const response = await apiClient.get(ATTENDANCE_ENDPOINTS.REVIEW);
  return response.data;
}