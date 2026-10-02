/**
 * Announcements API — scoped feed plus authorized create/edit (BR-080..084).
 *
 * The server decides visibility from the authenticated session; the payload
 * only names which scope a new announcement targets.
 *
 * @module api/announcements
 */

import apiClient from './client';
import { ANNOUNCEMENT_ENDPOINTS } from './endpoints';

/**
 * Visible announcements for the logged-in user (published only).
 * Rejects with an Error carrying `.code` (UNAUTHORIZED, FORBIDDEN, ...).
 *
 * @returns {Promise<Array<{id: string, title: string, body: string, scope: string, scope_label: string, is_important: boolean, is_published: boolean, created_at: string}>>}
 */
export async function getAnnouncements() {
  const response = await apiClient.get(ANNOUNCEMENT_ENDPOINTS.LIST);
  return response.data;
}

/**
 * Create a scoped announcement (academic users only — BR-083).
 *
 * @param {object} payload - {title, body, scope, scope_id, is_important?, published?}
 * @returns {Promise<object>} The created announcement.
 */
export async function createAnnouncement(payload) {
  const response = await apiClient.post(ANNOUNCEMENT_ENDPOINTS.LIST, payload);
  return response.data;
}

/**
 * Partial edit of an announcement (academic users only — BR-083/084).
 *
 * @param {string} id
 * @param {object} payload - {title?, body?, is_important?, published?}
 * @returns {Promise<object>} The updated announcement.
 */
export async function updateAnnouncement(id, payload) {
  const response = await apiClient.patch(ANNOUNCEMENT_ENDPOINTS.DETAIL(id), payload);
  return response.data;
}
