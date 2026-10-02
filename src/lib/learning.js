import api from './api';

const toData = async (promise) => {
  const res = await promise;
  const body = res?.data;
  if (body && typeof body === 'object' && 'data' in body) return body.data;
  return body;
};

export const learningApi = {
  // Courses the current user participates in (student enrolled / lecturer teaching).
  getMyCourses: async (role) => {
    if (role === 'LECTURER') {
      return toData(api.get('/lecturers/me/courses/'));
    }
    if (role === 'admin') {
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
  // Combined grades: several CAs (each on its own marking scale) rolled up
  // into one reported grade, e.g. one CA out of 30.
  getGroups: (offeringId) => toData(api.get(`/course-offerings/${offeringId}/assessment-groups/`)),
  createGroup: (offeringId, data) => toData(api.post(`/course-offerings/${offeringId}/assessment-groups/`, data)),
  getGroup: (groupId) => toData(api.get(`/assessment-groups/${groupId}/`)),
  updateGroup: (groupId, data) => toData(api.patch(`/assessment-groups/${groupId}/`, data)),
  deleteGroup: (groupId) => api.delete(`/assessment-groups/${groupId}/`),
  groupExportUrl: (groupId) => `${api.defaults.baseURL}/assessment-groups/${groupId}/export.csv`,
};