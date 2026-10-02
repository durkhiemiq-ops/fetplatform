/**
 * Users directory API — academic-readable student pickers.
 *
 * The general user list (/accounts/) is administrator-only; assessment and
 * membership pickers use this narrower endpoint instead.
 *
 * @module api/users
 */

import apiClient from './client';

/**
 * List students (academic users only — lecturer/admin).
 * Rejects with Error.code UNAUTHORIZED for non-academic sessions.
 *
 * @returns {Promise<Array<{id: string, first_name: string, last_name: string, username: string}>>}
 */
export async function getStudents() {
  const response = await apiClient.get('/accounts/students/');
  return response.data;
}
