import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";

import type { ApiError } from "@/lib/types/document";
import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setTokens,
} from "@/lib/auth-storage";

const baseURL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export const apiClient = axios.create({
  baseURL,
  timeout: 120000,
  headers: {
    Accept: "application/json",
  },
});

let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const refresh = getRefreshToken();
  if (!refresh) {
    clearTokens();
    return null;
  }

  try {
    const { data } = await axios.post<{ access: string }>(
      `${baseURL}/auth/token/refresh/`,
      { refresh }
    );
    setTokens(data.access, refresh);
    return data.access;
  } catch {
    clearTokens();
    return null;
  }
}

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiError>) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };
    const isAuthEndpoint = originalRequest?.url?.includes("/auth/login/") ||
      originalRequest?.url?.includes("/auth/token/refresh/");

    if (
      error.response?.status === 401 &&
      originalRequest &&
      !originalRequest._retry &&
      !isAuthEndpoint
    ) {
      originalRequest._retry = true;
      refreshPromise ??= refreshAccessToken().finally(() => {
        refreshPromise = null;
      });
      const newToken = await refreshPromise;
      if (newToken) {
        originalRequest.headers.Authorization = `Bearer ${newToken}`;
        return apiClient(originalRequest);
      }
      if (typeof window !== "undefined" && window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
    }

    const message =
      error.response?.data?.error?.message ??
      error.message ??
      "An unexpected error occurred";
    const wrapped = new Error(message) as Error & {
      status?: number;
      data?: unknown;
    };
    // Preserve status + payload so callers can handle structured errors
    // (e.g. 409 duplicate-document with existing-document info).
    wrapped.status = error.response?.status;
    wrapped.data = error.response?.data;
    return Promise.reject(wrapped);
  }
);
