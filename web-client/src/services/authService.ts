import api from "./api";

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

export function logout(): void {
  localStorage.removeItem(TOKEN_KEY);
  window.location.href = "/login";
}

export async function register(email: string, password: string): Promise<void> {
  await api.post("/api/v1/users/register", { email, password });
}

export async function login(email: string, password: string): Promise<void> {
  const { data } = await api.post<{ access_token: string }>("/api/v1/users/login", {
    email,
    password,
  });
  storeToken(data.access_token);
}
