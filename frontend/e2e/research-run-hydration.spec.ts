import { expect, test } from "@playwright/test";

const WORKSPACE = {
  tenantId: "5b376e3d-3983-44f0-b9ad-17917bb2e901",
  userId: "6e79df41-3ac0-4527-9c07-167ad4f3fa0d",
};
const RUN_ID = "89e4ac76-dfc4-4fc1-b0d7-a4ed6923f589";

// Exercises the capability added alongside GET /research-runs/{run_id}:
// navigating straight to a run's URL (a refresh, or a shared link) with no
// prior client-side state must hydrate from the server instead of showing
// nothing, because there was previously no per-run URL to refresh at all.
test.describe("direct navigation to a research run", () => {
  test("hydrates a completed run and its report from the API", async ({ page }) => {
    await page.addInitScript(
      ([key, value]) => window.localStorage.setItem(key, value),
      ["evident.workspace.v1", JSON.stringify(WORKSPACE)],
    );

    await page.route(`**/api/research-runs/${RUN_ID}`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          research_run_id: RUN_ID,
          llm_provider: "anthropic",
          status: "completed",
          query: "Compare HTTP/2 and HTTP/3 using current technical sources.",
          route: "deep_research",
          route_reason: "Comparison requires current sources.",
          error_message: null,
          created_at: "2026-08-05T12:00:00Z",
          started_at: "2026-08-05T12:00:01Z",
          completed_at: "2026-08-05T12:01:00Z",
        }),
      }),
    );
    await page.route(`**/api/research-runs/${RUN_ID}/report`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          report_id: "d38f3124-7d77-4bda-b711-10ca1e39f460",
          research_run_id: RUN_ID,
          content: "HTTP/3 reduces head-of-line blocking by running over QUIC.",
          workflow_status: "research_report_completed",
          citation_valid: true,
          citation_coverage: 0.9,
          reflection_status: "approved",
          reflection_reasons: [],
          reflection_attempts: 1,
          created_at: "2026-08-05T12:01:00Z",
          sources: [],
        }),
      }),
    );

    await page.goto(`/runs/${RUN_ID}`);

    await expect(page.getByRole("heading", { name: /Compare HTTP\/2 and HTTP\/3/ })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Research conclusion" })).toBeVisible();
    await expect(page.getByText(/reduces head-of-line blocking/)).toBeVisible();
  });
});
