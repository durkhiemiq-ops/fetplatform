/**
 * Authentication API functions.
 *
 * All functions talk to the Django backend via the shared apiClient.
 * The CSRF token is attached automatically by the client interceptor.
 *
 * @module api/auth
 */

import apiClient from './client';
import { AUTH_ENDPOINTS } from './endpoints';

/**
 * Fetch a CSRF token from the backend.
 * The token is set as an HttpOnly-exempt cookie by Django.
 * @returns {Promise<object>} CSRF response
 */
export async function getCsrfToken() {
  const response = await apiClient.get(AUTH_ENDPOINTS.CSRF);
  return response.data;
}

/**
 * Register a new user account.
 * @param {{email: string, username: string, first_name: string, last_name: string, password: string}} data
 * @returns {Promise<object>} Created user object
 */
export async function register(data) {
  const response = await apiClient.post(AUTH_ENDPOINTS.REGISTER, data);
  return response.data;
}

/**
 * Log in with email, matricule, or staffid plus password.
 * Sets a session cookie on success.
 * @param {{identifier: string, password: string}} data - `identifier` is the
 *   email, matricule, or staffid entered by the user.
 * @returns {Promise<object>} Authenticated user object
 */
export async function login(data) {
  const response = await apiClient.post(AUTH_ENDPOINTS.LOGIN, data);
  return response.data;
}

/**
 * Log out the current user. Destroys the session on the backend.
 * @returns {Promise<object>}
 */
export async function logout() {
  const response = await apiClient.post(AUTH_ENDPOINTS.LOGOUT);
  return response.data;
}

/**
 * Get the currently authenticated user.
 * @returns {Promise<object>} Current user object
 */
export async function getCurrentUser() {
  const response = await apiClient.get(AUTH_ENDPOINTS.ME);
  return response.data;
}

/**
 * Update the current user's profile.
 * @param {object} data - Partial user fields to update
 * @returns {Promise<object>} Updated user object
 */
export async function updateProfile(data) {
  const response = await apiClient.patch(AUTH_ENDPOINTS.ME, data);
  return response.data;
}

/**
 * Change a user's role (admin only).
 * @param {{user_id: string, new_role: string}} data
 * @returns {Promise<object>} Updated user object
 */
export async function changeRole(data) {
  const response = await apiClient.post(AUTH_ENDPOINTS.CHANGE_ROLE, data);
  return response.data;
}

/**
 * Verify a registration OTP (six-digit code).
 * The response is intentionally generic for every failure mode on the backend.
 * @param {{email: string, code: string}} data
 * @returns {Promise<object>} {message} on success
 */
export async function verifyEmail(data) {
  const response = await apiClient.post(AUTH_ENDPOINTS.VERIFY_EMAIL, data);
  return response.data;
}

/**
 * Request a fresh verification code for an address awaiting verification.
 * Backend returns the same generic response whether or not the address exists.
 * @param {{email: string}} data
 * @returns {Promise<object>} {message}
 */
export async function resendVerification(data) {
  const response = await apiClient.post(AUTH_ENDPOINTS.RESEND_VERIFICATION, data);
  return response.data;
}

/**
 * List all users (admin only).
 * @returns {Promise<object[]>} Array of user objects
 */
export async function listUsers() {
  const response = await apiClient.get(AUTH_ENDPOINTS.USERS);
  return response.data;
}
