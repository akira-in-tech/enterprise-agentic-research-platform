// One-off demo recorder covering the feature gaps the first two recordings
// left out: the direct-answer fast path, high-risk domain detection (the
// human-review banner), cancelling a running job, exporting a report, and
// tenant isolation. Not part of the committed test suite.
//
// Usage:
//   BASE_URL=https://<cloudfront-domain> node record-demo-extended.mjs
//
// Produces, in this script's directory:
//   video/            -- a .webm recording of the primary tenant's flow
//   demo.mp4          -- converted via the bundled ffmpeg binary
//   demo.gif          -- a lightweight loop for embedding in README.md
//   screenshots/*.png -- clean stills at each key moment (both tenants)

import { chromium } from "playwright";
import { spawnSync } from "node:child_process";
import { mkdirSync, readdirSync, renameSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const BASE_URL = process.env.BASE_URL;
if (!BASE_URL) {
  console.error("Set BASE_URL to the deployed app's public URL (CloudFront domain).");
  process.exit(1);
}

const FFMPEG = process.env.FFMPEG_PATH; // resolved by the caller from imageio_ffmpeg
if (!FFMPEG) {
  console.error("Set FFMPEG_PATH to a working ffmpeg binary.");
  process.exit(1);
}

const STAMP = Date.now();
const TENANT_A_EMAIL = `demo-ext-a-${STAMP}@example.com`;
const TENANT_B_EMAIL = `demo-ext-b-${STAMP}@example.com`;
const PASSWORD = "correct-horse-battery-demo-9";

const DIRECT_QUERY = "What is a mutex?";
const HIGH_RISK_QUERY =
  "What is the recommended maximum daily dosage of acetaminophen for a healthy adult, and what are the warning signs of overdose?";
const CANCEL_QUERY =
  "Compare the current best practices for API rate limiting across major cloud providers.";

const screenshotsDir = path.join(__dirname, "screenshots");
const videoDir = path.join(__dirname, "video");
mkdirSync(screenshotsDir, { recursive: true });
mkdirSync(videoDir, { recursive: true });

async function shoot(page, name) {
  await page.screenshot({ path: path.join(screenshotsDir, `${name}.png`), fullPage: false });
  console.log(`screenshot: ${name}`);
}

async function registerTenant(page, email) {
  await page.goto(`${BASE_URL}/register`);
  await page.getByLabel(/workspace name/i).fill("Demo Org");
  await page.getByLabel(/^email$/i).fill(email);
  await page.getByLabel(/^password$/i).fill(PASSWORD);
  await page.getByRole("button", { name: /create workspace/i }).click();
  await page.waitForURL(/\/(?!register)/, { timeout: 15_000 });
}

async function waitForReport(page, { timeoutMs }) {
  const evidenceToggle = page.getByRole("button", { name: /inspect evidence/i });
  await evidenceToggle.waitFor({ timeout: timeoutMs }).catch(() => {
    console.warn(`Report did not appear within ${timeoutMs}ms; capturing current state anyway.`);
  });
  return evidenceToggle;
}

const browser = await chromium.launch();

// --- Tenant A: the primary, recorded flow -----------------------------
const contextA = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  recordVideo: { dir: videoDir, size: { width: 1440, height: 900 } },
});
const pageA = await contextA.newPage();

try {
  console.log(`Registering tenant A against ${BASE_URL} ...`);
  await registerTenant(pageA, TENANT_A_EMAIL);
  await shoot(pageA, "01-signed-in");

  console.log(`Direct-answer fast path: "${DIRECT_QUERY}"`);
  await pageA.getByLabel(/research question/i).fill(DIRECT_QUERY);
  await pageA.getByRole("button", { name: /start research/i }).click();
  await pageA.waitForURL(/\/runs\//, { timeout: 15_000 });
  await waitForReport(pageA, { timeoutMs: 90_000 });
  await shoot(pageA, "02-direct-answer-report");

  console.log(`High-risk domain: "${HIGH_RISK_QUERY}"`);
  await pageA.goto(BASE_URL);
  await pageA.getByLabel(/research question/i).fill(HIGH_RISK_QUERY);
  await pageA.getByRole("button", { name: /start research/i }).click();
  await pageA.waitForURL(/\/runs\//, { timeout: 15_000 });
  await waitForReport(pageA, { timeoutMs: 8 * 60_000 });
  await shoot(pageA, "03-high-risk-report-with-review-banner");

  console.log("Exporting the high-risk report as PDF ...");
  const downloadButton = pageA.locator("button.download-button");
  if (await downloadButton.isVisible().catch(() => false)) {
    await downloadButton.click();
    const downloadPromise = pageA.waitForEvent("download", { timeout: 20_000 }).catch(() => null);
    await pageA.locator('[role="option"]', { hasText: /pdf/i }).first().click();
    const download = await downloadPromise;
    if (download) {
      console.log(`Download fired: ${download.suggestedFilename()}`);
    } else {
      console.warn("No download event observed within timeout.");
    }
    await shoot(pageA, "04-report-exported");
  } else {
    console.warn("Download button not visible; skipping export step.");
  }

  console.log(`Starting a cancellable run: "${CANCEL_QUERY}"`);
  await pageA.goto(BASE_URL);
  await pageA.getByLabel(/research question/i).fill(CANCEL_QUERY);
  await pageA.getByRole("button", { name: /start research/i }).click();
  await pageA.waitForURL(/\/runs\//, { timeout: 15_000 });
  await shoot(pageA, "05-run-started-before-cancel");

  const cancelButton = pageA.getByRole("button", { name: /cancel research/i });
  await cancelButton.waitFor({ timeout: 20_000 });
  await cancelButton.click();
  await pageA.getByText("Research cancelled", { exact: true }).waitFor({ timeout: 10_000 });
  await shoot(pageA, "06-run-cancelled");

  console.log("Demo flow for tenant A complete.");
} finally {
  await contextA.close();
}

// --- Tenant B: isolation check (screenshots only, no recording) --------
const contextB = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const pageB = await contextB.newPage();

try {
  console.log(`Registering tenant B against ${BASE_URL} to check isolation ...`);
  await registerTenant(pageB, TENANT_B_EMAIL);

  await pageB.locator("button.product-nav-button", { hasText: "Private Knowledge" }).click();
  await pageB.waitForURL(/\/knowledge/, { timeout: 10_000 });
  await pageB.getByText(/no private sources yet/i).waitFor({ timeout: 10_000 });
  await shoot(pageB, "07-tenant-b-sees-no-shared-documents");

  console.log("Tenant isolation check complete: a brand-new tenant sees zero documents.");
} finally {
  await contextB.close();
  await browser.close();
}

// context.close() finalizes the .webm file; find it and convert.
const webmFiles = readdirSync(videoDir).filter((f) => f.endsWith(".webm"));
if (webmFiles.length === 0) {
  console.error("No video file was produced.");
  process.exit(1);
}
const rawWebm = path.join(videoDir, webmFiles[0]);
const finalWebm = path.join(__dirname, "demo.webm");
renameSync(rawWebm, finalWebm);

console.log("Converting to mp4 ...");
spawnSync(
  FFMPEG,
  [
    "-y",
    "-i",
    finalWebm,
    "-c:v",
    "libx264",
    "-pix_fmt",
    "yuv420p",
    path.join(__dirname, "demo.mp4"),
  ],
  { stdio: "inherit" },
);

console.log("Converting to a looping GIF for README embedding ...");
spawnSync(
  FFMPEG,
  [
    "-y",
    "-i",
    finalWebm,
    "-vf",
    "fps=10,scale=960:-1:flags=lanczos",
    "-loop",
    "0",
    path.join(__dirname, "demo.gif"),
  ],
  { stdio: "inherit" },
);

console.log(`Done. Assets in ${__dirname}`);
