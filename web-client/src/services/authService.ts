import api, { refreshAccessToken } from "./api";

const TOKEN_KEY = "access_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function isLoggedIn(): boolean {
  return !!getToken();
}

export function storeToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

/**
 * Try to obtain a fresh access token from the refresh-token cookie. Returns
 * true when a valid session exists (used to support 30-day "remember me" even
 * after the short-lived access token has expired or been cleared).
 */
export async function refreshSession(): Promise<boolean> {
  return (await refreshAccessToken()) != null;
}

export async function logout(): Promise<void> {
  try {
    // Revoke this session's refresh token server-side. Best-effort.
    await api.post("/api/v1/auth/logout");
  } catch {
    // ignore — clear locally regardless
  }
  localStorage.removeItem(TOKEN_KEY);
  window.location.href = "/login";
}

export async function register(email: string, password: string): Promise<void> {
  // Creates the account only; the user signs in afterward to start a session.
  await api.post("/api/v1/users/register", { email, password });
}

export async function login(email: string, password: string): Promise<void> {
  const { data } = await api.post<{ access_token: string }>("/api/v1/users/login", {
    email,
    password,
  });
  storeToken(data.access_token);
}
