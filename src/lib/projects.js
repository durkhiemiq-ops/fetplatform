import api from './api';

const unwrap = (res) => (res?.data && typeof res.data === 'object' && 'data' in res.data ? res.data.data : res?.data);
const detail = (id) => api.get('/projects/' + id + '/').then(unwrap);
const unavailable = (feature) => Promise.reject(new Error(feature + ' is not available yet.'));

export const projectsApi = {
  listProjects: (params) => api.get('/projects/', { params }).then(unwrap),
  createProject: (data) => api.post('/projects/', data).then(unwrap),
  getProject: detail,
  updateProject: (id, data) => api.patch('/projects/' + id + '/', data).then(unwrap),
  listArchive: () => api.get('/projects/').then(unwrap).then((rows) => rows.filter((row) => row.status === 'archived')),
  listGroups: (id) => detail(id).then((bundle) => bundle.groups),
  createGroup: (id, data) => api.post('/projects/' + id + '/groups/', data).then(unwrap),
  candidates: (id) => api.get('/projects/' + id + '/candidates/').then(unwrap),
  addMember: (id, groupId, data) => api.post('/projects/' + id + '/members/', {
    student: data.student ?? data.student_id,
    group: groupId || null,
  }).then(unwrap),
  removeMember: (id, groupId, studentId) => api.delete(
    '/projects/' + id + '/groups/' + groupId + '/members/' + studentId + '/'
  ).then(unwrap),
  listTasks: (id) => detail(id).then((bundle) => bundle.tasks),
  createTask: (id, data) => api.post('/projects/' + id + '/tasks/', data).then(unwrap),
  updateTask: (id, data) => api.patch('/projects/tasks/' + id + '/', data).then(unwrap),
  completeTask: (id) => api.patch('/projects/tasks/' + id + '/', { status: 'completed' }).then(unwrap),
  listMilestones: (id) => api.get('/projects/' + id + '/milestones/').then(unwrap),
  createMilestone: (id, data) => api.post('/projects/' + id + '/milestones/', data).then(unwrap),
  updateMilestone: (id, data) => api.patch('/projects/milestones/' + id + '/', data).then(unwrap),
  deleteMilestone: (id) => api.delete('/projects/milestones/' + id + '/').then(unwrap),
  listContributions: (id) => detail(id).then((bundle) => bundle.contributions),
  createContribution: (id, data) => api.post('/projects/' + id + '/contributions/', data).then(unwrap),
  reviewContribution: (id, data) => api.patch('/projects/contributions/' + id + '/', data).then(unwrap),
  // These reference-backend features have no route in the integrated backend.
  // Retain explicit rejections for other screens until their UI is migrated.
  deleteProject: () => unavailable('Project deletion'),
  overview: () => unavailable('Project overview reports'),
  syncMembers: () => unavailable('Automatic membership synchronization'),
  updateGroup: () => unavailable('Group editing'),
  deleteGroup: () => unavailable('Group deletion'),
  groupReport: () => unavailable('Group reports'),
  unassigned: () => unavailable('Course enrollment group assignment'),
  getDelegate: () => unavailable('Class delegates'),
  appointDelegate: () => unavailable('Class delegates'),
  removeDelegate: () => unavailable('Class delegates'),
  delegateCandidates: () => unavailable('Class delegates'),
  offeringGroups: () => unavailable('Course offering groups'),
  listDocuments: () => unavailable('Project documents'),
  listAssessments: () => unavailable('Project assessment components'),
  createAssessment: () => unavailable('Project assessment components'),
  recordAssessment: () => unavailable('Project assessment components'),
};

export default projectsApi;
