/**
 * Notifications API — owner-scoped inbox (BR §23, API §45).
 *
 * The server returns only the requesting user's own notifications; there is
 * no parameter that can name another account, and mutating another user's
 * notification answers with the same NOT_FOUND as a missing id (§25).
 *
 * @module api/notifications
 */

import apiClient from './client';
import { NOTIFICATION_ENDPOINTS } from './endpoints';

/**
 * The requesting user's notification inbox, newest first.
 *
 * @param {object} [options] - {unread?: boolean}
 * @returns {Promise<Array<{id: string, category: string, title: string, body: string,
 *   related_type: string, related_id: string, is_read: boolean, read_at: string|null,
 *   created_at: string}>>}
 */
export async function getNotifications(options = {}) {
  const params = {};
  if (options.unread) params.unread = 'true';
  const response = await apiClient.get(NOTIFICATION_ENDPOINTS.LIST, { params });
  return response.data;
}

/**
 * Mark one notification as read (idempotent).
 *
 * @param {string} id
 * @returns {Promise<object>} The updated notification row.
 */
export async function markNotificationRead(id) {
  const response = await apiClient.patch(NOTIFICATION_ENDPOINTS.READ(id), {});
  return response.data;
}

/**
 * Mark every unread notification as read.
 *
 * @returns {Promise<{updated_count: number}>}
 */
export async function markAllNotificationsRead() {
  const response = await apiClient.post(NOTIFICATION_ENDPOINTS.READ_ALL, {});
  return response.data;
}