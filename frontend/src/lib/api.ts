import axios, {
  AxiosError,
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
} from "axios";
import { useAuthStore } from "../stores/authStore";
import type { ApiErrorDetail, Envelope, TokenPair } from "../types";

const baseURL =
  import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

export const api = axios.create({ baseURL });

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Single-flight refresh so concurrent 401s don't trigger multiple refreshes.
let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const { refreshToken, setTokens, clearAuth } = useAuthStore.getState();
  if (!refreshToken) {
    clearAuth();
    return null;
  }
  try {
    const res = await axios.post<Envelope<TokenPair>>(
      `${baseURL}/auth/refresh`,
      { refresh_token: refreshToken },
    );
    const tokens = res.data.data;
    if (!tokens) {
      clearAuth();
      return null;
    }
    setTokens(tokens.access_token, tokens.refresh_token);
    return tokens.access_token;
  } catch {
    clearAuth();
    return null;
  }
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as
      | (AxiosRequestConfig & { _retry?: boolean })
      | undefined;

    if (error.response?.status === 401 && original && !original._retry) {
      original._retry = true;
      refreshPromise = refreshPromise ?? refreshAccessToken();
      const newToken = await refreshPromise;
      refreshPromise = null;
      if (newToken) {
        original.headers = {
          ...original.headers,
          Authorization: `Bearer ${newToken}`,
        };
        return api(original);
      }
    }
    return Promise.reject(error);
  },
);

/** Extract a human-readable message from an Axios error envelope. */
export function getErrorMessage(error: unknown, fallback = "Something went wrong."): string {
  if (error instanceof AxiosError) {
    const detail = (error.response?.data as Envelope<unknown> | undefined)?.error as
      | ApiErrorDetail
      | undefined;
    if (detail?.message) {
      return detail.message;
    }
    if (error.message) {
      return error.message;
    }
  }
  return fallback;
}
