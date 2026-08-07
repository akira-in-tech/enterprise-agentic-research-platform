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

async function mockUnauthenticated(page: Page): Promise<void> {
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({ status: 401, contentType: "application/json", body: "{}" }),
  );
}

test.describe("authentication", () => {
  test("registering a new workspace signs the user in and redirects home", async ({ page }) => {
    await mockUnauthenticated(page);
    await page.route("**/api/auth/register", (route) =>
      route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(IDENTITY),
      }),
    );

    await page.goto("/register");
    await page.getByLabel("Workspace name").fill("ACME Platform");
    await page.getByLabel("Email").fill("engineer@acme.example");
    await page.getByLabel("Password", { exact: true }).fill("correct-horse-battery");
    await page.getByRole("button", { name: "Create workspace" }).click();

    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("heading", { name: "Recent research" })).toBeVisible();
    await expect(page.getByText("ACME Platform").first()).toBeVisible();
  });

  test("logging in redirects back to the originally requested page", async ({ page }) => {
    await mockUnauthenticated(page);
    await page.route("**/api/auth/login", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(IDENTITY),
      }),
    );

    await page.goto("/knowledge");
    await expect(page).toHaveURL(/\/login/);

    await page.getByLabel("Email").fill("engineer@acme.example");
    await page.getByLabel("Password").fill("correct-horse-battery");
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page).toHaveURL(/\/knowledge$/);
  });

  test("an invalid login shows an inline error and does not navigate", async ({ page }) => {
    await mockUnauthenticated(page);
    await page.route("**/api/auth/login", (route) =>
      route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Invalid email or password." }),
      }),
    );

    await page.goto("/login");
    await page.getByLabel("Email").fill("engineer@acme.example");
    await page.getByLabel("Password").fill("wrong-password");
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page.getByRole("alert")).toContainText("Invalid email or password.");
    await expect(page).toHaveURL(/\/login/);
  });

  test("signed-in users can submit research and then log out", async ({ page }) => {
    await page.route("**/api/auth/me", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(IDENTITY),
      }),
    );
    await page.route("**/api/research-runs/jobs", (route) =>
      route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          research_run_id: "89e4ac76-dfc4-4fc1-b0d7-a4ed6923f589",
          status: "queued",
          progress_url: "/research-runs/89e4ac76-dfc4-4fc1-b0d7-a4ed6923f589/progress",
          events_url: "/research-runs/89e4ac76-dfc4-4fc1-b0d7-a4ed6923f589/events",
          report_url: "/research-runs/89e4ac76-dfc4-4fc1-b0d7-a4ed6923f589/report",
        }),
      }),
    );
    await page.route("**/api/research-runs/89e4ac76-dfc4-4fc1-b0d7-a4ed6923f589/events", (route) =>
      route.fulfill({ status: 200, contentType: "text/event-stream", body: "" }),
    );

    await page.goto("/");
    await page.getByLabel("Research question").fill("Compare HTTP/2 and HTTP/3.");
    await page.getByRole("button", { name: "Start research" }).click();

    await expect(page).toHaveURL(/\/runs\/89e4ac76-dfc4-4fc1-b0d7-a4ed6923f589$/);

    await page.route("**/api/auth/logout", (route) => route.fulfill({ status: 204, body: "" }));
    await page.getByRole("button", { name: "Account menu" }).click();
    await page.getByRole("menuitem", { name: "Log out" }).click();

    await expect(page).toHaveURL(/\/login/);
  });
});
