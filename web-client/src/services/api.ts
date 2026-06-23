import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";

const TOKEN_KEY = "access_token";

// In production the Next.js rewrite proxies /api/* to the backend,
// so no baseURL is needed. In local dev, fall back to localhost:8000.
const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || undefined,
  headers: { "Content-Type": "application/json" },
  // Send the httpOnly refresh cookie on /auth/* calls.
  withCredentials: true,
});

api.interceptors.request.use((config) => {
  const token =
    typeof window !== "undefined" ? localStorage.getItem(TOKEN_KEY) : null;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// --- Silent access-token refresh on 401 -------------------------------------
// When a request 401s (expired access token), exchange the refresh cookie for a
// fresh access token and replay the request once. Concurrent 401s share a single
// in-flight refresh so we never stampede the endpoint.
let refreshPromise: Promise<string | null> | null = null;

async function requestRefresh(): Promise<string | null> {
  try {
    const { data } = await axios.post<{ access_token: string }>(
      "/api/v1/auth/refresh",
      {},
      { baseURL: api.defaults.baseURL, withCredentials: true },
    );
    if (typeof window !== "undefined") {
      localStorage.setItem(TOKEN_KEY, data.access_token);
    }
    return data.access_token;
  } catch {
    return null;
  }
}

export function refreshAccessToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = requestRefresh().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as
      | (InternalAxiosRequestConfig & { _retry?: boolean })
      | undefined;
    const url = original?.url ?? "";
    const isAuthCall = url.includes("/auth/refresh") || url.includes("/auth/logout");

    if (error.response?.status === 401 && original && !original._retry && !isAuthCall) {
      original._retry = true;
      const newToken = await refreshAccessToken();
      if (newToken) {
        original.headers.Authorization = `Bearer ${newToken}`;
        return api(original);
      }
      // Refresh failed — the session is gone. Bounce to login (once).
      if (
        typeof window !== "undefined" &&
        !window.location.pathname.startsWith("/login")
      ) {
        localStorage.removeItem(TOKEN_KEY);
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  },
);

export default api;
