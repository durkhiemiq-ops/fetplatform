import api from './api';

const toData = async (promise) => {
  const res = await promise;
  const body = res?.data;
  if (body && typeof body === 'object' && 'data' in body) return body.data;
  return body;
};

/**
 * Course registration and carry-over applications.
 *
 * Both hang off the student's own record, and both depend on the active
 * semester existing -- without one the backend answers
 * `NO_ACTIVE_SEMESTER`, which is worth surfacing rather than showing an
 * empty list that looks like "nothing to register for".
 */
export const enrollmentApi = {
  // GET returns { semester, registration_deadline, level, department, courses[] }
  availableCourses: () => toData(api.get('/students/me/available-courses/')),
  register: (offeringIds) => toData(api.post('/students/me/register/', { offering_ids: offeringIds })),
  myCourses: () => toData(api.get('/students/me/courses/')),

  // Students see their own applications, staff see all of them.
  listCarryOver: (status) =>
    toData(api.get('/carry-over/', status ? { params: { status } } : undefined)),
  applyCarryOver: (courseOfferingId, reason) =>
    toData(api.post('/carry-over/apply/', { course_offering_id: courseOfferingId, reason })),
  // Approving is what actually creates the enrollment (BR-031).
  reviewCarryOver: (applicationId, decision, note) =>
    toData(api.post(`/carry-over/${applicationId}/review/`, { decision, note })),
};

/** Pull the human message out of the standard error envelope. */
export const errorMessage = (err, fallback = 'Something went wrong.') =>
  err?.response?.data?.error?.message
  || err?.response?.data?.message
  || err?.response?.data?.error
  || err?.message
  || fallback;

export default enrollmentApi;
