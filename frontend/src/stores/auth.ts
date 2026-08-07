import { defineStore } from "pinia";
import { ref } from "vue";

import {
  AuthApiError,
  changePassword as apiChangePassword,
  getCurrentUser,
  login as apiLogin,
  logout as apiLogout,
  register as apiRegister,
  updateProfile as apiUpdateProfile,
  type ChangePasswordParams,
  type LoginParams,
  type RegisterParams,
} from "../lib/auth-api";
import type { AuthIdentity, AuthTenant, AuthUser } from "../types/research";

export type AuthStatus = "idle" | "loading" | "authenticated" | "unauthenticated";

export const useAuthStore = defineStore("auth", () => {
  const user = ref<AuthUser | null>(null);
  const tenant = ref<AuthTenant | null>(null);
  const status = ref<AuthStatus>("idle");
  const error = ref("");

  let bootstrapPromise: Promise<void> | null = null;

  function setIdentity(identity: AuthIdentity | null): void {
    user.value = identity?.user ?? null;
    tenant.value = identity?.tenant ?? null;
    status.value = identity ? "authenticated" : "unauthenticated";
  }

  function isAuthenticated(): boolean {
    return status.value === "authenticated";
  }

  function bootstrap(): Promise<void> {
    if (!bootstrapPromise) {
      bootstrapPromise = (async () => {
        status.value = "loading";
        try {
          setIdentity(await getCurrentUser());
        } catch {
          setIdentity(null);
        }
      })();
    }

    return bootstrapPromise;
  }

  async function register(params: RegisterParams): Promise<boolean> {
    error.value = "";
    try {
      setIdentity(await apiRegister(params));
      return true;
    } catch (caught) {
      error.value = caught instanceof AuthApiError ? caught.message : "Registration failed.";
      return false;
    }
  }

  async function login(params: LoginParams): Promise<boolean> {
    error.value = "";
    try {
      setIdentity(await apiLogin(params));
      return true;
    } catch (caught) {
      error.value = caught instanceof AuthApiError ? caught.message : "Login failed.";
      return false;
    }
  }

  async function logout(): Promise<void> {
    await apiLogout();
    setIdentity(null);
  }

  async function updateDisplayName(displayName: string): Promise<boolean> {
    error.value = "";
    try {
      setIdentity(await apiUpdateProfile(displayName.trim() || null));
      return true;
    } catch (caught) {
      error.value = caught instanceof AuthApiError ? caught.message : "Profile update failed.";
      return false;
    }
  }

  async function changePassword(params: ChangePasswordParams): Promise<boolean> {
    error.value = "";
    try {
      await apiChangePassword(params);
      return true;
    } catch (caught) {
      error.value = caught instanceof AuthApiError ? caught.message : "Password change failed.";
      return false;
    }
  }

  /** Test- and design-preview-only override, bypassing the API. */
  function setForPreview(identity: AuthIdentity): void {
    setIdentity(identity);
  }

  return {
    user,
    tenant,
    status,
    error,
    isAuthenticated,
    bootstrap,
    register,
    login,
    logout,
    updateDisplayName,
    changePassword,
    setForPreview,
  };
});
