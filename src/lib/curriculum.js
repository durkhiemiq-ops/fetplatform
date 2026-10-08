import api from './api';

const toData = async (promise) => {
  const res = await promise;
  const body = res?.data;
  if (body && typeof body === 'object' && 'data' in body) return body.data;
  return body;
};

/**
 * Curriculum-driven registration.
 *
 * Unlike the legacy offering-picker flow, the server owns every academic fact
 * here: programme, level, curriculum, required offerings. The client submits
 * at most a specialization choice drawn from the server-provided options, and
 * the backend resolves and creates everything else. There is deliberately no
 * way to submit programme, level, curriculum, course, or offering IDs, nor to
 * act for another student: the service layer derives all of that from the
 * authenticated session.
 */
export const curriculumApi = {
  // GET returns { programme, level, cohort, semester, curriculum,
  //   specialization_required, specializations[], specialization,
  //   required_offerings[], completed, registration }
  state: () => toData(api.get('/students/me/curriculum-registration/')),
  // POST { specialization? } returns the state plus created_enrollments[].
  // Omit specialization entirely when none is required or already selected;
  // sending specialization: null explicitly clears nothing and is rejected
  // once a specialization is pinned (SPECIALIZATION_LOCKED).
  complete: (specialization) => toData(api.post(
    '/students/me/curriculum-registration/',
    specialization ? { specialization } : {},
  )),
};

export default curriculumApi;
