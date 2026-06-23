import axios from "axios";

// In production the Next.js rewrite proxies /api/* to the backend,
// so no baseURL is needed. In local dev, fall back to localhost:8000.
const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || undefined,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  const token =
    typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export default api;
