import { expect, test } from "@playwright/test";

const WORKSPACE = {
  tenantId: "5b376e3d-3983-44f0-b9ad-17917bb2e901",
  userId: "6e79df41-3ac0-4527-9c07-167ad4f3fa0d",
};

test.describe("routed navigation", () => {
  test("home page loads with the composer and recent-research section", async ({ page }) => {
    await page.goto("/");

    await expect(page).toHaveTitle(/Evident/);
    await expect(page.getByRole("heading", { name: "Recent research" })).toBeVisible();
    await expect(page.getByLabel("Research question")).toBeVisible();
  });

  test("header navigation moves between / and /knowledge with real URLs", async ({ page }) => {
    await page.goto("/");

    await page.getByRole("button", { name: "Private Knowledge" }).click();
    await expect(page).toHaveURL(/\/knowledge$/);
    await expect(page.getByRole("heading", { name: "Bring your own evidence." })).toBeVisible();

    await page.getByRole("button", { name: "Research", exact: true }).click();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("heading", { name: "Recent research" })).toBeVisible();
  });

  test("a research run that does not exist shows a not-found state instead of crashing", async ({
    page,
  }) => {
    await page.addInitScript(
      ([key, value]) => window.localStorage.setItem(key, value),
      ["evident.workspace.v1", JSON.stringify(WORKSPACE)],
    );
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
});
