/**
 * Academic API — read endpoints for faculties, departments, and courses.
 *
 * @module api/academic
 */

import apiClient from './client';
import { ACADEMIC_ENDPOINTS } from './endpoints';

/** @returns {Promise<Array<{id: string, name: string}>>} */
export async function getFaculties() {
  const response = await apiClient.get(ACADEMIC_ENDPOINTS.FACULTIES);
  return response.data;
}

/** @returns {Promise<Array<{id: string, name: string, faculty: string|null, faculty_name: string|null}>>} */
export async function getDepartments() {
  const response = await apiClient.get(ACADEMIC_ENDPOINTS.DEPARTMENTS);
  return response.data;
}

/**
 * Courses arrive with department_name/faculty_name resolved server-side.
 * @returns {Promise<Array<{id: string, code: string, name: string, department: string|null, department_name: string|null, faculty_name: string|null}>>}
 */
export async function getCourses() {
  const response = await apiClient.get(ACADEMIC_ENDPOINTS.COURSES);
  return response.data;
}

/**
 * Class sessions (course occurrence + lecturer) — feeds announcement scope
 * pickers and class listings.
 * @returns {Promise<Array<{id: string, course: string, course_code: string, lecturer: string, lecturer_name: string, starts_at: string|null}>>}
 */
export async function getClasses() {
  const response = await apiClient.get(ACADEMIC_ENDPOINTS.CLASSES);
  return response.data;
}

/**
 * The caller's own active course enrollments (BR-012).
 * Scoped server-side to request.user — there is no way to ask for a peer's.
 * @returns {Promise<Array<{id, course, course_code, course_name, is_active, status}>>}
 */
export async function getMyEnrollments() {
  const response = await apiClient.get(ACADEMIC_ENDPOINTS.ENROLLMENTS);
  return response.data;
}

/**
 * Enroll the caller in a course. BR-011/BR-013: an active enrollment is the
 * default source of class eligibility, and attendance eligibility derives from
 * it — so this is what the Enrol button must call.
 * @param {string} courseId
 * @param {string} [studentId] - administrator only; rejected for a student.
 */
export async function enrollInCourse(courseId, studentId) {
  const response = await apiClient.post(ACADEMIC_ENDPOINTS.ENROLLMENTS, {
    course: courseId,
    ...(studentId ? { student: studentId } : {}),
  });
  return response.data;
}

/**
 * End future eligibility. BR-014/BR-015: the enrollment row is deactivated,
 * never deleted, and prior attendance/assessment history is retained.
 * @param {string} courseId
 * @param {string} [studentId] - administrator only.
 */
export async function dropFromCourse(courseId, studentId) {
  const response = await apiClient.delete(
    ACADEMIC_ENDPOINTS.ENROLLMENT_DROP(courseId) +
      (studentId ? `?student=${encodeURIComponent(studentId)}` : '')
  );
  return response.data;
}
