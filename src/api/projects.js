/**
 * Projects API — lifecycle, groups, tasks, contributions (BR-100..161).
 *
 * Rejections carry `.code` from the standard envelope, e.g.:
 *   UNAUTHORIZED, INVALID_STATUS, DUPLICATE_MEMBER, NOT_PARTICIPANT,
 *   INVALID_EVIDENCE, NOT_FOUND.
 *
 * @module api/projects
 */

import apiClient from './client';
import { PROJECT_ENDPOINTS } from './endpoints';

/** Projects visible to the logged-in user (own/supervised/participating). */
export async function getProjects() {
  const response = await apiClient.get(PROJECT_ENDPOINTS.LIST);
  return response.data;
}

/** Create a project (the server forces the initial draft state). */
export async function createProject(payload) {
  const response = await apiClient.post(PROJECT_ENDPOINTS.LIST, payload);
  return response.data;
}

/**
 * Project detail bundle: {project, groups, members, tasks, contributions}.
 * @param {string} id
 */
export async function getProject(id) {
  const response = await apiClient.get(PROJECT_ENDPOINTS.DETAIL(id));
  return response.data;
}

/**
 * Lifecycle transition (draft→active→completed) or archive.
 * @param {string} id
 * @param {string} status - One step forward, or 'archived'.
 */
export async function updateProjectStatus(id, status) {
  const response = await apiClient.patch(PROJECT_ENDPOINTS.DETAIL(id), { status });
  return response.data;
}

/** Create a group inside a project (owner/supervisor/admin only). */
export async function createGroup(projectId, payload) {
  const response = await apiClient.post(PROJECT_ENDPOINTS.GROUPS(projectId), payload);
  return response.data;
}

/** Add a student to the project, optionally into a group (no duplicates). */
export async function addMember(projectId, payload) {
  const response = await apiClient.post(PROJECT_ENDPOINTS.MEMBERS(projectId), payload);
  return response.data;
}

/** Create a task in a project (participants only for assignments). */
export async function createTask(projectId, payload) {
  const response = await apiClient.post(PROJECT_ENDPOINTS.TASKS(projectId), payload);
  return response.data;
}

/**
 * Move a task along its status flow (assignee/creator only).
 * @param {string} taskId
 * @param {string} status - e.g. 'todo' | 'in_progress' | 'done'
 */
export async function updateTaskStatus(taskId, status) {
  const response = await apiClient.patch(PROJECT_ENDPOINTS.TASK_STATUS(taskId), { status });
  return response.data;
}

/**
 * Submit a contribution (self-only) with task evidence from the same project.
 * @param {string} projectId
 * @param {object} payload - {evidence_type: 'task', evidence_ref: taskId}
 */
export async function submitContribution(projectId, payload) {
  const response = await apiClient.post(PROJECT_ENDPOINTS.CONTRIBUTIONS(projectId), payload);
  return response.data;
}

/** Contributions visible to the logged-in user (own + visible projects'). */
export async function getContributions() {
  const response = await apiClient.get(PROJECT_ENDPOINTS.CONTRIBUTION_LIST);
  return response.data;
}

/**
 * Review a contribution (project academics only — audited, BR-122/210).
 * @param {string} id
 * @param {object} payload - {approved: boolean, notes?: string}
 */
export async function reviewContribution(id, payload) {
  const response = await apiClient.patch(PROJECT_ENDPOINTS.CONTRIBUTION_REVIEW(id), payload);
  return response.data;
}
