/**
 * API Endpoint constants — never hardcode URLs in components.
 *
 * @module api/endpoints
 */

export const AUTH_ENDPOINTS = {
  CSRF: '/accounts/csrf/',
  REGISTER: '/accounts/register/',
  LOGIN: '/accounts/login/',
  LOGOUT: '/accounts/logout/',
  ME: '/accounts/me/',
  CHANGE_ROLE: '/accounts/change-role/',
  USERS: '/accounts/',
  VERIFY_EMAIL: '/accounts/verify-email/',
  RESEND_VERIFICATION: '/accounts/resend-verification/',
};

export const ATTENDANCE_ENDPOINTS = {
  SCAN: '/attendance/scan/',
  SESSIONS: '/attendance/sessions/',
  SESSION_DETAIL: (id) => `/attendance/sessions/${id}/`,
  SESSION_CLOSE: (id) => `/attendance/sessions/${id}/close/`,
  SESSION_CHECKPOINTS: (id) => `/attendance/sessions/${id}/checkpoints/`,
  CHECKPOINT_TOKEN: (id) => `/attendance/checkpoints/${id}/token/`,
  RECORDS: '/attendance/records/',
  RECORD_CORRECTIONS: (id) => `/attendance/records/${id}/corrections/`,
  REVIEW: '/attendance/review/',
};

export const ACADEMIC_ENDPOINTS = {
  FACULTIES: '/academic/faculties/',
  DEPARTMENTS: '/academic/departments/',
  COURSES: '/academic/courses/',
  CLASSES: '/academic/classes/',
  SCHOOL_YEARS: '/academic/school-years/',
  SEMESTERS: '/academic/semesters/',
  ENROLLMENTS: '/academic/enrollments/',
  ENROLLMENT_DROP: (courseId) => `/academic/enrollments/${courseId}/`,
};

export const ANNOUNCEMENT_ENDPOINTS = {
  LIST: '/announcements/',
  DETAIL: (id) => `/announcements/${id}/`,
};

export const ASSESSMENT_ENDPOINTS = {
  LIST: '/assessments/',
  DETAIL: (id) => `/assessments/${id}/`,
};

export const PROJECT_ENDPOINTS = {
  LIST: '/projects/',
  DETAIL: (id) => `/projects/${id}/`,
  GROUPS: (id) => `/projects/${id}/groups/`,
  MEMBERS: (id) => `/projects/${id}/members/`,
  TASKS: (id) => `/projects/${id}/tasks/`,
  CONTRIBUTIONS: (id) => `/projects/${id}/contributions/`,
  TASK_STATUS: (id) => `/projects/tasks/${id}/`,
  CONTRIBUTION_LIST: '/projects/contributions/',
  CONTRIBUTION_REVIEW: (id) => `/projects/contributions/${id}/`,
};

export const NOTIFICATION_ENDPOINTS = {
  LIST: '/notifications/',
  READ: (id) => `/notifications/${id}/read/`,
  READ_ALL: '/notifications/read-all/',
};
