/**
 * Academic calendar API — school years and semesters.
 *
 * Reads are open to authenticated users; writes return 403 UNAUTHORIZED
 * unless the session belongs to an administrator.
 *
 * @module api/calendar
 */

import apiClient from './client';
import { ACADEMIC_ENDPOINTS } from './endpoints';

/** @returns {Promise<Array<{id: string, name: string, start_date: string, end_date: string}>>} */
export async function getSchoolYears() {
  const response = await apiClient.get(ACADEMIC_ENDPOINTS.SCHOOL_YEARS);
  return response.data;
}

/**
 * School years are effectively READ-ONLY over this API.
 *
 * L3/H3/H4: the backend exposes GET for school years plus an admin-only POST,
 * but NO PATCH and NO DELETE, and the `SchoolYear` model has no active-year
 * flag. The old `createSchoolYear` wrapper was therefore unusable — the UI sent
 * camelCase dates the serializer rejects, and the paired "switch current year"
 * control resolved to a silent no-op. SchoolYearManager is now a read-only
 * list, and no create/update/delete wrapper is exported here so nothing can
 * call a capability the API does not have.
 */

/**
 * @returns {Promise<Array<{id: string, school_year: string, school_year_name: string, name: string, start_date: string, end_date: string, is_current: boolean}>>}
 */
export async function getSemesters() {
  const response = await apiClient.get(ACADEMIC_ENDPOINTS.SEMESTERS);
  return response.data;
}

/**
 * Admin-only.
 *
 * The backend expects the real field names — `school_year` is a UUID, not a
 * year name, and the dates are snake_case. Note there is deliberately NO delete
 * wrapper: the API exposes no DELETE for semesters.
 *
 * @param {object} payload - {school_year, name, start_date, end_date, is_current?}
 */
export async function createSemester(payload) {
  const response = await apiClient.post(ACADEMIC_ENDPOINTS.SEMESTERS, payload);
  return response.data;
}

/**
 * Admin-only partial edit. Setting is_current true demotes the previous
 * current semester server-side (at most one current semester).
 * @param {string} id
 * @param {object} payload - {is_current?: boolean, name?, start_date?, end_date?}
 */
export async function updateSemester(id, payload) {
  const response = await apiClient.patch(`${ACADEMIC_ENDPOINTS.SEMESTERS}${id}/`, payload);
  return response.data;
}
