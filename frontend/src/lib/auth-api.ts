import type { AuthIdentity } from "../types/research";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

export class AuthApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "AuthApiError";
  }
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string };
    return body.detail ?? `Request failed with status ${response.status}.`;
  } catch {
    return `Request failed with status ${response.status}.`;
  }
}

export interface RegisterParams {
  email: string;
  password: string;
  tenantName: string;
  displayName?: string;
}

export async function register(params: RegisterParams): Promise<AuthIdentity> {
  const response = await fetch(`${API_BASE_URL}/auth/register`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email: params.email,
      password: params.password,
      tenant_name: params.tenantName,
      display_name: params.displayName || null,
    }),
  });

  if (!response.ok) {
    throw new AuthApiError(await errorMessage(response), response.status);
  }

  return (await response.json()) as AuthIdentity;
}

export interface LoginParams {
  email: string;
  password: string;
}

export async function login(params: LoginParams): Promise<AuthIdentity> {
  const response = await fetch(`${API_BASE_URL}/auth/login`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: params.email, password: params.password }),
  });

  if (!response.ok) {
    throw new AuthApiError(await errorMessage(response), response.status);
  }

  return (await response.json()) as AuthIdentity;
}

export async function logout(): Promise<void> {
  await fetch(`${API_BASE_URL}/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
}

export async function getCurrentUser(): Promise<AuthIdentity | null> {
  const response = await fetch(`${API_BASE_URL}/auth/me`, {
    credentials: "include",
    headers: { Accept: "application/json" },
  });

  if (response.status === 401) {
    return null;
  }

  if (!response.ok) {
    throw new AuthApiError(await errorMessage(response), response.status);
  }

  return (await response.json()) as AuthIdentity;
}
