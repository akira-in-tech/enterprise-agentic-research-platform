import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAuthStore } from "./auth";

const identity = {
  user: { id: "user-1", email: "engineer@acme.example", display_name: "ACME Engineer" },
  tenant: { id: "tenant-1", name: "ACME Platform", slug: "acme-platform-a1b2c3d4" },
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  setActivePinia(createPinia());
});

afterEach(() => vi.unstubAllGlobals());

describe("useAuthStore", () => {
  it("starts unauthenticated until bootstrap resolves", () => {
    const store = useAuthStore();

    expect(store.status).toBe("idle");
    expect(store.isAuthenticated()).toBe(false);
  });

  it("bootstraps into authenticated state when a session cookie is valid", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse(identity)),
    );
    const store = useAuthStore();

    await store.bootstrap();

    expect(store.isAuthenticated()).toBe(true);
    expect(store.user).toEqual(identity.user);
    expect(store.tenant).toEqual(identity.tenant);
  });

  it("bootstraps into unauthenticated state when there is no valid session", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 401 })),
    );
    const store = useAuthStore();

    await store.bootstrap();

    expect(store.isAuthenticated()).toBe(false);
    expect(store.user).toBeNull();
  });

  it("only calls /auth/me once across repeated bootstrap calls", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(identity));
    vi.stubGlobal("fetch", fetchMock);
    const store = useAuthStore();

    await Promise.all([store.bootstrap(), store.bootstrap()]);

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("registers and stores the returned identity", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse(identity, 201)),
    );
    const store = useAuthStore();

    const success = await store.register({
      email: identity.user.email,
      password: "correct-horse-battery",
      tenantName: identity.tenant.name,
    });

    expect(success).toBe(true);
    expect(store.isAuthenticated()).toBe(true);
    expect(store.user).toEqual(identity.user);
  });

  it("surfaces a duplicate-email registration error without authenticating", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ detail: "Email is already registered." }, 409)),
    );
    const store = useAuthStore();

    const success = await store.register({
      email: identity.user.email,
      password: "correct-horse-battery",
      tenantName: identity.tenant.name,
    });

    expect(success).toBe(false);
    expect(store.error).toBe("Email is already registered.");
    expect(store.isAuthenticated()).toBe(false);
  });

  it("logs in and stores the returned identity", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse(identity)),
    );
    const store = useAuthStore();

    const success = await store.login({
      email: identity.user.email,
      password: "correct-horse-battery",
    });

    expect(success).toBe(true);
    expect(store.isAuthenticated()).toBe(true);
  });

  it("surfaces an invalid-credentials login error without authenticating", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ detail: "Invalid email or password." }, 401)),
    );
    const store = useAuthStore();

    const success = await store.login({
      email: identity.user.email,
      password: "wrong-password",
    });

    expect(success).toBe(false);
    expect(store.error).toBe("Invalid email or password.");
    expect(store.isAuthenticated()).toBe(false);
  });

  it("clears identity on logout", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse(identity)),
    );
    const store = useAuthStore();
    await store.login({ email: identity.user.email, password: "correct-horse-battery" });

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    await store.logout();

    expect(store.isAuthenticated()).toBe(false);
    expect(store.user).toBeNull();
    expect(store.tenant).toBeNull();
  });

  it("sets a preview identity without calling the API", () => {
    const store = useAuthStore();

    store.setForPreview(identity);

    expect(store.isAuthenticated()).toBe(true);
    expect(store.user).toEqual(identity.user);
  });
});
