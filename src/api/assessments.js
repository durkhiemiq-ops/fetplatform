/**
 * Assessments API — BR-130..132.
 *
 * Students receive only their own released records (private notes are
 * stripped server-side); academic users manage the full set.
 *
 * @module api/assessments
 */

import apiClient from './client';
import { ASSESSMENT_ENDPOINTS } from './endpoints';

/**
 * Assessments visible to the logged-in user.
 *
 * @returns {Promise<Array<{id: string, student: string, student_name: string, course: string|null, score: string|null, status: string, released: boolean, private_notes: string|null}>>}
 */
export async function getAssessments() {
  const response = await apiClient.get(ASSESSMENT_ENDPOINTS.LIST);
  return response.data;
}

/**
 * Create an assessment for a student (academic users only — BR-130).
 *
 * @param {object} payload - {student, score?, private_notes?, released?, course?, class_session?}
 * @returns {Promise<object>} The created assessment.
 */
export async function createAssessment(payload) {
  const response = await apiClient.post(ASSESSMENT_ENDPOINTS.LIST, payload);
  return response.data;
}

/**
 * Partial edit of an assessment; every mutation is audited (BR-132).
 *
 * @param {string} id
 * @param {object} payload - {score?, private_notes?, released?}
 * @returns {Promise<object>} The updated assessment.
 */
export async function updateAssessment(id, payload) {
  const response = await apiClient.patch(ASSESSMENT_ENDPOINTS.DETAIL(id), payload);
  return response.data;
}
