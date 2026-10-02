import api from './api';

/**
 * Audit log console (Security doc 08 §24; Roles doc 02 §28).
 *
 * The backend has always written audit records; this is the read surface.
 * Access is admin-only server-side - the UI guard is convenience only
 * (BR-211 is enforced by the API, not by hiding a link).
 */
const unwrap = (res) => res?.data?.data ?? res?.data;

export const auditApi = {
  list: ({ action = '', resourceType = '', search = '', page = 1, pageSize = 20 } = {}) => {
    const params = { page, page_size: pageSize };
    if (action) params.action = action;
    if (resourceType) params.resource_type = resourceType;
    if (search) params.search = search;
    return api.get('/audit/logs/', { params }).then(unwrap);
  },
  summary: () => api.get('/audit/summary/').then(unwrap),
};

/** Human labels for the actions the platform records. */
export const ACTION_LABELS = {
  LOGGED_IN: 'Signed in',
  LOGGED_OUT: 'Signed out',
  LOGIN_FAILED: 'Failed sign-in',
  ROLE_CHANGED: 'Role changed',
  PERMISSION_CHANGED: 'Permission changed',
  ATTENDANCE_STARTED: 'Attendance started',
  ATTENDANCE_CORRECTED: 'Attendance corrected',
  ASSESSMENT_CREATED: 'Assessment created',
  ASSESSMENT_UPDATED: 'Assessment updated',
  PROJECT_ARCHIVED: 'Project archived',
  ACCOUNT_CREATED: 'Account created',
  SELF_REGISTERED: 'Self-registered',
  PASSWORD_CHANGED: 'Password changed',
  FACULTY_CREATED: 'Faculty created',
  DEPARTMENT_CREATED: 'Department created',
  COURSE_CREATED: 'Course created',
  ANNOUNCEMENT_PINNED: 'Announcement pinned',
  ANNOUNCEMENT_UNPINNED: 'Announcement unpinned',
  ROSTER_UPLOADED: 'Roster uploaded',
};

export const actionLabel = (action) =>
  ACTION_LABELS[action] || action.replace(/_/g, ' ').toLowerCase();

/** Actions that should stand out in a security review. */
export const SENSITIVE_ACTIONS = new Set([
  'LOGIN_FAILED',
  'ROLE_CHANGED',
  'PERMISSION_CHANGED',
  'ATTENDANCE_CORRECTED',
  'ACCOUNT_CREATED',
  'SELF_REGISTERED',
  'PASSWORD_CHANGED',
]);
