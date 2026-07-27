import { apiClient } from '@/api/client';
import type { ApiResponse, AuthTokens, User } from '@/types';

/**
 * Register a new user account.
 *
 * @param payload - Signup fields.
 * @returns Auth tokens payload.
 */
export async function signup(payload: {
  email: string;
  password: string;
  full_name: string;
}): Promise<AuthTokens> {
  const { data } = await apiClient.post<ApiResponse<AuthTokens>>('/auth/signup', payload);
  return data.data;
}

/**
 * Authenticate an existing user.
 *
 * @param payload - Login fields.
 * @returns Auth tokens payload.
 */
export async function login(payload: {
  email: string;
  password: string;
}): Promise<AuthTokens> {
  const { data } = await apiClient.post<ApiResponse<AuthTokens>>('/auth/login', payload);
  return data.data;
}

/**
 * Log out the current session.
 */
export async function logout(): Promise<void> {
  await apiClient.post('/auth/logout');
}

/**
 * Fetch the current authenticated user.
 *
 * @returns User profile.
 */
export async function fetchMe(): Promise<User> {
  const { data } = await apiClient.get<ApiResponse<User>>('/auth/me');
  return data.data;
}

/**
 * Refresh the access token using the HTTP-only cookie.
 *
 * @returns Auth tokens payload.
 */
export async function refreshSession(): Promise<AuthTokens> {
  const { data } = await apiClient.post<ApiResponse<AuthTokens>>('/auth/refresh');
  return data.data;
}
