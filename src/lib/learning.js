import api from './api';
import { normalizeRole } from './profile';

const toData = async (promise) => {
  const res = await promise;
  const body = res?.data;
  if (body && typeof body === 'object' && 'data' in body) return body.data;
  return body;
};

/**
 * Fetch a binary resource *through the authenticated axios instance* and save it.
 *
 * The previous helpers returned a bare absolute URL for use as an `<a href>`.
 * A plain link navigation does not send the session cookie cross-origin and
 * bypasses the axios client's withCredentials/CSRF setup, so every material
 * download and CSV export failed with 401/403 outside a same-origin proxy.
 * Going through `api.get(..., { responseType: 'blob' })` keeps the session.
 */
const downloadBlob = async (path, fallbackName) => {
  const res = await api.get(path, { responseType: 'blob' });
  const disposition = res.headers?.['content-disposition'] || '';
  // Prefer the server's filename; fall back to something sensible.
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition);
  const name = match ? decodeURIComponent(match[1].trim()) : fallbackName;

  const href = URL.createObjectURL(res.data);
  const anchor = document.createElement('a');
  anchor.href = href;
  anchor.download = name;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(href);
  return name;
};

export const learningApi = {
  // Courses the current user participates in (student enrolled / lecturer teaching).
  getMyCourses: async (role) => {
    // Compare through normalizeRole. Callers pass anything from the raw
    // 'ADMINISTRATOR' the server sends down to a literal 'student'. The old
    // literals ('LECTURER' / 'admin') matched neither consistently, so a real
    // administrator matched no branch and silently fell through to the
    // *student* endpoint.
    const normalized = normalizeRole(role);
    if (normalized === 'lecturer') {
      return toData(api.get('/lecturers/me/courses/'));
    }
    if (normalized === 'admin') {
      const data = await toData(api.get('/course-offerings/'));
      return (data || []).map((c) => ({
        offering_id: c.id,
        course_code: c.course_code,
        course_title: c.course_title,
        semester: c.semester_name,
        lecturer_name: c.lecturer_name || 'Staff',
        materials_count: 0,
        announcements_count: 0,
      }));
    }
    return toData(api.get('/students/me/courses/'));
  },
  // All offerings (admin browse).
  getAllCourses: () => toData(api.get('/course-offerings/')),
  getCourse: (offeringId) => toData(api.get(`/course-offerings/${offeringId}/`)),
  // Materials for a course offering
  getMaterials: (offeringId) => toData(api.get(`/course-offerings/${offeringId}/materials/`)),
  createMaterial: (data) => toData(api.post(`/course-offerings/${data.course_offering}/materials/`, data)),
  updateMaterial: (materialId, data) => toData(api.patch(`/materials/${materialId}/`, data)),
  deleteMaterial: (materialId) => api.delete(`/materials/${materialId}/`),
  // Upload the raw file first (POST /files/), then attach the returned id to a material.
  uploadFile: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await api.post('/files/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    const body = res?.data;
    return body && typeof body === 'object' && 'data' in body ? body.data : body;
  },
  getDownloadUrl: (fileId) => `${api.defaults.baseURL}/files/${fileId}/`,
  // Authenticated download. Prefer this over `getDownloadUrl`, which returns a
  // bare cross-origin URL that cannot carry the session cookie.
  downloadFile: (fileId) => downloadBlob(`/files/${fileId}/`, `download-${fileId}`),
  // Assignments (teacher sets due date, late policy, submission limit).
  getAssignments: (offeringId) => toData(api.get(`/course-offerings/${offeringId}/assignments/`)),
  createAssignment: (offeringId, data) => toData(api.post(`/course-offerings/${offeringId}/assignments/`, data)),
  deleteAssignment: (assignmentId) => api.delete(`/assignments/${assignmentId}/`),
  getSubmissions: (assignmentId) => toData(api.get(`/assignments/${assignmentId}/submissions/`)),
  submitAssignment: (assignmentId, data) => toData(api.post(`/assignments/${assignmentId}/submissions/`, data)),
  gradeSubmission: (submissionId, data) => toData(api.patch(`/submissions/${submissionId}/`, data)),
  // Classrooms: a lecturer opens a classroom for one of their own courses and
  // every registered student for that course is enrolled automatically.
  availableClassroomCourses: () => toData(api.get('/classrooms/available-courses/')),
  createClassroom: (data) => toData(api.post('/classrooms/', data)),
  // Assessment marks: lecturer creates a CA/exam sheet, types the marks,
  // publishes it; students review and can dispute. CSV export for the lecturer.
  getAssessments: (offeringId) => toData(api.get(`/course-offerings/${offeringId}/assessments/`)),
  createAssessment: (offeringId, data) => toData(api.post(`/course-offerings/${offeringId}/assessments/`, data)),
  getAssessment: (assessmentId) => toData(api.get(`/assessments/${assessmentId}/`)),
  updateAssessment: (assessmentId, data) => toData(api.patch(`/assessments/${assessmentId}/`, data)),
  deleteAssessment: (assessmentId) => api.delete(`/assessments/${assessmentId}/`),
  saveMarks: (assessmentId, marks) => toData(api.put(`/assessments/${assessmentId}/marks/`, { marks })),
  raiseDispute: (markId, reason) => toData(api.patch(`/assessment-marks/${markId}/`, { dispute_reason: reason })),
  resolveDispute: (markId, response) => toData(api.patch(`/assessment-marks/${markId}/`, { dispute_response: response })),
  myAssessments: () => toData(api.get('/students/me/assessments/')),
  assessmentExportUrl: (assessmentId) => `${api.defaults.baseURL}/assessments/${assessmentId}/export.csv`,
  downloadAssessmentExport: (assessmentId) =>
    downloadBlob(`/assessments/${assessmentId}/export.csv`, `assessment-${assessmentId}.csv`),
  // Combined grades: several CAs (each on its own marking scale) rolled up
  // into one reported grade, e.g. one CA out of 30.
  getGroups: (offeringId) => toData(api.get(`/course-offerings/${offeringId}/assessment-groups/`)),
  createGroup: (offeringId, data) => toData(api.post(`/course-offerings/${offeringId}/assessment-groups/`, data)),
  getGroup: (groupId) => toData(api.get(`/assessment-groups/${groupId}/`)),
  updateGroup: (groupId, data) => toData(api.patch(`/assessment-groups/${groupId}/`, data)),
  deleteGroup: (groupId) => api.delete(`/assessment-groups/${groupId}/`),
  groupExportUrl: (groupId) => `${api.defaults.baseURL}/assessment-groups/${groupId}/export.csv`,
  downloadGroupExport: (groupId) =>
    downloadBlob(`/assessment-groups/${groupId}/export.csv`, `assessment-group-${groupId}.csv`),
};