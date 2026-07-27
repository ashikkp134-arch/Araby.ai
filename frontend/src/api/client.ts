import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios';

/**
 * Resolve API base URL.
 *
 * Prefer an empty value so requests stay same-origin via the Vite `/api` proxy.
 * Absolute URLs that point at the Vite dev server are treated as empty.
 *
 * @returns Normalized API origin without trailing slash, or empty string.
 */
function resolveApiOrigin(): string {
  const raw = (import.meta.env.VITE_API_BASE_URL || '').trim().replace(/\/$/, '');
  if (!raw) {
    return '';
  }
  // Common misconfiguration: pointing at the Vite frontend instead of the API.
  try {
    const parsed = new URL(raw);
    if (parsed.port === '5173') {
      return '';
    }
    if (typeof window !== 'undefined' && raw === window.location.origin) {
      return '';
    }
  } catch {
    return '';
  }
  return raw;
}

const RAW_API_BASE = resolveApiOrigin();
export const API_BASE_URL = RAW_API_BASE;
const API_V1_BASE = RAW_API_BASE ? `${RAW_API_BASE}/api/v1` : '/api/v1';

let accessTokenMemory: string | null = null;
let refreshPromise: Promise<string | null> | null = null;

/**
 * Store the access token in memory only.
 *
 * @param token - Access token string or null to clear.
 */
export function setAccessToken(token: string | null): void {
  accessTokenMemory = token;
}

/**
 * Read the in-memory access token.
 *
 * @returns Current access token or null.
 */
export function getAccessToken(): string | null {
  return accessTokenMemory;
}

/**
 * Build an absolute or same-origin API path.
 *
 * @param path - Path under `/api/v1`, e.g. `/auth/refresh`.
 * @returns Full request URL path.
 */
export function apiUrl(path: string): string {
  const normalized = path.startsWith('/') ? path : `/${path}`;
  return `${API_V1_BASE}${normalized}`;
}

export const apiClient: AxiosInstance = axios.create({
  baseURL: API_V1_BASE,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  if (accessTokenMemory) {
    config.headers.Authorization = `Bearer ${accessTokenMemory}`;
  }
  return config;
});

/**
 * Rotate the refresh cookie into a new access token.
 *
 * @returns New access token or null when rotation fails.
 */
async function refreshAccessToken(): Promise<string | null> {
  try {
    const response = await axios.post(
      apiUrl('/auth/refresh'),
      {},
      { withCredentials: true },
    );
    const token = response.data?.data?.access_token as string | undefined;
    if (token) {
      setAccessToken(token);
      return token;
    }
    return null;
  } catch {
    // Do not clear a valid in-memory access token here. Cookie refresh can fail
    // independently (missing cookie) while the access token is still usable.
    return null;
  }
}

/**
 * Determine whether a failed request should attempt token refresh.
 *
 * @param url - Request URL.
 * @returns True when refresh retry is allowed.
 */
function shouldAttemptRefresh(url?: string): boolean {
  if (!url) {
    return true;
  }
  return !url.includes('/auth/refresh') && !url.includes('/auth/login') && !url.includes('/auth/signup');
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & { _retry?: boolean };
    if (
      error.response?.status === 401 &&
      original &&
      !original._retry &&
      shouldAttemptRefresh(original.url)
    ) {
      original._retry = true;
      if (!refreshPromise) {
        refreshPromise = refreshAccessToken().finally(() => {
          refreshPromise = null;
        });
      }
      const token = await refreshPromise;
      if (token) {
        original.headers.Authorization = `Bearer ${token}`;
        return apiClient(original);
      }
    }
    return Promise.reject(error);
  },
);
