import api from './api';

/**
 * Roster-based account provisioning (BR-002, BR-003).
 *
 * Public self-registration is disabled, so this CSV is the only way a student
 * account comes into existence. The response carries the one-time temp
 * passwords for the accounts it just created -- they are never retrievable
 * again, so the UI has to hand them back to the administrator now.
 */
export const ROSTER_COLUMNS = [
  'matricule',
  'first_name',
  'last_name',
  'email',
  'level',
  'department_code',
];

export const rosterApi = {
  upload: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    // Let the browser set Content-Type so the multipart boundary is present.
    const res = await api.post('/admin/roster/upload/', formData);
    // Every 2xx is wrapped as { success, data } by SuccessRenderer.
    const body = res?.data;
    return body && typeof body === 'object' && 'data' in body ? body.data : body;
  },
};

export default rosterApi;
