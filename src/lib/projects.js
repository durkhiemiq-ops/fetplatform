import api from './api';

const unwrap = (res) => (res?.data && typeof res.data === 'object' && 'data' in res.data ? res.data.data : res?.data);

export const projectsApi = {
  listProjects: (params) => api.get('/projects/', { params }).then(unwrap),
  createProject: (data) => api.post('/projects/create/', data).then(unwrap),
  getProject: (id) => api.get(`/projects/${id}/`).then(unwrap),
  updateProject: (id, data) => api.patch(`/projects/${id}/`, data).then(unwrap),
  deleteProject: (id) => api.delete(`/projects/${id}/`).then(unwrap),
  listArchive: () => api.get('/projects/archive/').then(unwrap),

  // Lecturer's "every group at a glance" screen
  overview: (projectId) => api.get(`/projects/${projectId}/overview/`).then(unwrap),
  syncMembers: (projectId) => api.post(`/projects/${projectId}/sync-members/`).then(unwrap),

  listGroups: (projectId) => api.get(`/projects/${projectId}/groups/`).then(unwrap),
  createGroup: (projectId, data) => api.post(`/projects/${projectId}/groups/`, data).then(unwrap),
  updateGroup: (projectId, groupId, data) =>
    api.patch(`/projects/${projectId}/groups/${groupId}/`, data).then(unwrap),
  deleteGroup: (projectId, groupId) =>
    api.delete(`/projects/${projectId}/groups/${groupId}/`).then(unwrap),
  groupReport: (projectId, groupId) =>
    api.get(`/projects/${projectId}/groups/${groupId}/report/`).then(unwrap),
  candidates: (projectId) => api.get(`/projects/${projectId}/candidates/`).then(unwrap),
  addMember: (projectId, groupId, data) =>
    api.post(`/projects/${projectId}/groups/${groupId}/members/`, data).then(unwrap),
  removeMember: (projectId, groupId, studentId) =>
    api.delete(`/projects/${projectId}/groups/${groupId}/members/${studentId}/`).then(unwrap),

  // The "Unassigned" bucket: enrolled students not yet in a group
  unassigned: (projectId) => api.get(`/projects/${projectId}/unassigned/`).then(unwrap),

  // Class delegate, one per course offering
  getDelegate: (offeringId) => api.get(`/course-offerings/${offeringId}/delegate/`).then(unwrap),
  appointDelegate: (offeringId, studentId) =>
    api.post(`/course-offerings/${offeringId}/delegate/`, { student: studentId }).then(unwrap),
  removeDelegate: (offeringId) => api.delete(`/course-offerings/${offeringId}/delegate/`).then(unwrap),
  delegateCandidates: (offeringId) =>
    api.get(`/course-offerings/${offeringId}/delegate-candidates/`).then(unwrap),
  offeringGroups: (offeringId) =>
    api.get(`/course-offerings/${offeringId}/groups/`).then(unwrap),

  listTasks: (projectId) => api.get(`/projects/${projectId}/tasks/`).then(unwrap),
  createTask: (projectId, data) => api.post(`/projects/${projectId}/tasks/`, data).then(unwrap),
  updateTask: (taskId, data) => api.patch(`/tasks/${taskId}/`, data).then(unwrap),
  completeTask: (taskId) => api.post(`/tasks/${taskId}/complete/`).then(unwrap),

  listMilestones: (projectId) => api.get(`/projects/${projectId}/milestones/`).then(unwrap),
  createMilestone: (projectId, data) =>
    api.post(`/projects/${projectId}/milestones/`, data).then(unwrap),
  updateMilestone: (milestoneId, data) => api.patch(`/milestones/${milestoneId}/`, data).then(unwrap),
  deleteMilestone: (milestoneId) => api.delete(`/milestones/${milestoneId}/`).then(unwrap),

  listContributions: (projectId) =>
    api.get(`/projects/${projectId}/contributions/`).then(unwrap),
  createContribution: (projectId, data) =>
    api.post(`/projects/${projectId}/contributions/`, data).then(unwrap),

  listDocuments: (projectId) => api.get(`/projects/${projectId}/documents/`).then(unwrap),

  listAssessments: (projectId) => api.get(`/projects/${projectId}/assessments/`).then(unwrap),
  createAssessment: (projectId, data) =>
    api.post(`/projects/${projectId}/assessments/`, data).then(unwrap),
  recordAssessment: (assessmentId, data) =>
    api.post(`/assessments/${assessmentId}/records/`, data).then(unwrap),
};

export default projectsApi;