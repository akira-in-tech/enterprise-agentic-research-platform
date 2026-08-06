import { expect, test } from "@playwright/test";

// design-preview is a dev-only mode (gated by import.meta.env.DEV) that
// seeds the app with fixture data instead of calling a real backend --
// see src/lib/design-fixtures.ts. It lets these end-to-end tests exercise
// full routed flows (list -> detail, operational-issue states) without a
// running FastAPI/Postgres/Redis stack.

test.describe("design preview", () => {
  test("lists fixture runs and navigates to a running run's detail page", async ({ page }) => {
    await page.goto("/?design-preview");

    const runRow = page
      .getByRole("button", { name: /How should a multi-tenant API isolate data/ })
      .first();
    await expect(runRow).toBeVisible();

    await runRow.click();

    await expect(page).toHaveURL(/\/runs\/d38f3124-7d77-4bda-b711-10ca1e39f460$/);
    await expect(page.getByRole("heading", { name: /multi-tenant API/ })).toBeVisible();
  });

  test("navigates to a completed run and renders its fixture report", async ({ page }) => {
    await page.goto("/?design-preview");

    await page
      .getByRole("button", { name: /transactional outbox/ })
      .first()
      .click();

    await expect(page).toHaveURL(/\/runs\/7d955d06-04a0-4d87-a2af-3a9b69f00ae5$/);
    await expect(page.getByRole("heading", { name: "Research conclusion" })).toBeVisible();
    await expect(page.getByText("Verified")).toBeVisible();
  });

  test("state=citation renders the completed fixture report as needing revision", async ({
    page,
  }) => {
    await page.goto("/?design-preview&state=citation");

    await page
      .getByRole("button", { name: /transactional outbox/ })
      .first()
      .click();

    await expect(page.getByText("Revision required", { exact: true })).toBeVisible();
    await expect(page.getByRole("alert")).toContainText("Citation revision required");
  });

  test("state=redis surfaces the operational notice on the home page", async ({ page }) => {
    await page.goto("/?design-preview&state=redis");

    await expect(page.getByRole("alert")).toContainText("Redis is temporarily unavailable");
  });
});
