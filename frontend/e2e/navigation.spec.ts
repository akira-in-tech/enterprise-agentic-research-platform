import { expect, test, type Page } from "@playwright/test";

const IDENTITY = {
  user: {
    id: "6e79df41-3ac0-4527-9c07-167ad4f3fa0d",
    email: "engineer@acme.example",
    display_name: "ACME Engineer",
  },
  tenant: {
    id: "5b376e3d-3983-44f0-b9ad-17917bb2e901",
    name: "ACME Platform",
    slug: "acme-platform-a1b2c3d4",
  },
};

// The router guard resolves a session via GET /auth/me before allowing
// navigation past /login; mocking it lets these tests exercise the
// authenticated app without a running backend.
async function mockAuthenticatedSession(page: Page): Promise<void> {
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(IDENTITY),
    }),
  );
}

test.describe("routed navigation", () => {
  test("home page loads with the composer and recent-research section", async ({ page }) => {
    await mockAuthenticatedSession(page);
    await page.goto("/");

    await expect(page).toHaveTitle(/Evident/);
    await expect(page.getByRole("heading", { name: "Recent research" })).toBeVisible();
    await expect(page.getByLabel("Research question")).toBeVisible();
  });

  test("header navigation moves between / and /knowledge with real URLs", async ({ page }) => {
    await mockAuthenticatedSession(page);
    await page.goto("/");

    await page.getByRole("button", { name: "Private Knowledge", exact: true }).click();
    await expect(page).toHaveURL(/\/knowledge$/);
    await expect(page.getByRole("heading", { name: "Bring your own evidence." })).toBeVisible();

    await page.getByRole("button", { name: "Research", exact: true }).click();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("heading", { name: "Recent research" })).toBeVisible();
  });

  test("a research run that does not exist shows a not-found state instead of crashing", async ({
    page,
  }) => {
    await mockAuthenticatedSession(page);
    await page.route("**/api/research-runs/00000000-0000-0000-0000-000000000000", (route) =>
      route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Research run was not found." }),
      }),
    );

    await page.goto("/runs/00000000-0000-0000-0000-000000000000");

    await expect(page.getByRole("alert")).toContainText("could not be found");
    await page.getByRole("link", { name: "Back to research" }).click();
    await expect(page).toHaveURL(/\/$/);
  });

  test("visiting a protected route while unauthenticated redirects to login", async ({ page }) => {
    await page.route("**/api/auth/me", (route) =>
      route.fulfill({ status: 401, contentType: "application/json", body: "{}" }),
    );

    await page.goto("/");

    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  });
});
