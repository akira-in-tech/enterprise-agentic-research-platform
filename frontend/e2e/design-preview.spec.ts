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

  test("downloads the report through the download menu with the chosen format and citation style", async ({
    page,
  }) => {
    const researchRunId = "7d955d06-04a0-4d87-a2af-3a9b69f00ae5";
    let exportQuery = "";
    let downloadQuery = "";

    await page.route(`**/api/research-runs/${researchRunId}/report/export**`, async (route) => {
      const url = new URL(route.request().url());

      if (route.request().method() === "POST") {
        exportQuery = url.search;
        await route.fulfill({
          status: 201,
          contentType: "application/json",
          body: JSON.stringify({
            storage_key: "tenants/x/report-exports/y/report-footnote.pdf",
          }),
        });
      } else {
        downloadQuery = url.search;
        await route.fulfill({
          status: 200,
          contentType: "application/pdf",
          body: "%PDF-1.7 fixture bytes",
        });
      }
    });

    await page.goto("/?design-preview");
    await page
      .getByRole("button", { name: /transactional outbox/ })
      .first()
      .click();
    await expect(page).toHaveURL(new RegExp(`/runs/${researchRunId}$`));

    await page.locator(".download-button").click();
    const options = page.getByRole("option");
    await expect(options).toHaveCount(4);

    const downloadPromise = page.waitForEvent("download");
    await options.nth(3).click(); // PDF · Footnote is the fourth listed option
    const download = await downloadPromise;

    expect(exportQuery).toBe("?format=pdf&citation_style=footnote");
    expect(downloadQuery).toBe("?format=pdf&citation_style=footnote");
    expect(download.suggestedFilename()).toMatch(/report-.*-footnote\.pdf$/);
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
    await expect(page.locator(".operational-notice")).toContainText("Citation revision required");
  });

  test("state=redis surfaces the operational notice on the home page", async ({ page }) => {
    await page.goto("/?design-preview&state=redis");

    await expect(page.getByRole("alert")).toContainText("Redis is temporarily unavailable");
  });
});
