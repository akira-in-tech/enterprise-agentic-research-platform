// One-off demo recorder for the Private Knowledge flow against the deployed
// AWS staging app -- complements record-demo.mjs, which only exercises the
// public-web research path. Not part of the committed test suite.
//
// Usage:
//   BASE_URL=https://<cloudfront-domain> node record-demo-private-knowledge.mjs
//
// Produces, in this script's directory:
//   video/           -- a .webm recording of the whole flow (Playwright native)
//   demo.mp4         -- converted via the bundled ffmpeg binary
//   demo.gif         -- a lightweight loop for embedding in README.md
//   screenshots/*.png -- clean stills at each key moment

import { chromium } from "playwright";
import { spawnSync } from "node:child_process";
import { mkdirSync, writeFileSync, readdirSync, renameSync } from "node:fs";
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

const DEMO_EMAIL = `demo-private-${Date.now()}@example.com`;
const DEMO_PASSWORD = "correct-horse-battery-demo-9";
const DOCUMENT_FILENAME = "edge-http3-rollout-notes.txt";
const DOCUMENT_CONTENT = `Internal Engineering Note: Edge Proxy HTTP/3 Rollout

Our edge proxy fleet enabled HTTP/3 (QUIC) in Q2 2026 using a BBRv2
congestion-control profile. Internal load testing against the edge fleet
measured a 14% median time-to-first-byte (TTFB) improvement compared to the
prior HTTP/2 configuration, tested across the us-west-2 and ap-northeast-1
points of presence.

The rollout is owned by the Edge Platform team, tracked internally under the
codename "Skyway". Skyway's next milestone is enabling 0-RTT connection
resumption fleet-wide by the end of Q3 2026.
`;
const DEMO_QUERY =
  "What congestion-control profile does our edge proxy fleet use for its HTTP/3 rollout, and what TTFB improvement did internal testing show?";

const documentPath = path.join(__dirname, DOCUMENT_FILENAME);
writeFileSync(documentPath, DOCUMENT_CONTENT, "utf-8");

const screenshotsDir = path.join(__dirname, "screenshots");
const videoDir = path.join(__dirname, "video");
mkdirSync(screenshotsDir, { recursive: true });
mkdirSync(videoDir, { recursive: true });

async function shoot(page, name) {
  await page.screenshot({ path: path.join(screenshotsDir, `${name}.png`), fullPage: false });
  console.log(`screenshot: ${name}`);
}

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  recordVideo: { dir: videoDir, size: { width: 1440, height: 900 } },
});
const page = await context.newPage();

try {
  console.log(`Registering demo account against ${BASE_URL} ...`);
  await page.goto(`${BASE_URL}/register`);
  await shoot(page, "01-register");

  await page.getByLabel(/workspace name/i).fill("Demo Org");
  await page.getByLabel(/^email$/i).fill(DEMO_EMAIL);
  await page.getByLabel(/^password$/i).fill(DEMO_PASSWORD);
  await page.getByRole("button", { name: /create workspace/i }).click();
  await page.waitForURL(/\/(?!register)/, { timeout: 15_000 });

  console.log("Opening Private Knowledge ...");
  await page.locator("button.product-nav-button", { hasText: "Private Knowledge" }).click();
  await page.waitForURL(/\/knowledge/, { timeout: 10_000 });
  await shoot(page, "02-knowledge-empty");

  console.log(`Uploading ${DOCUMENT_FILENAME} ...`);
  await page.locator('input[type="file"]').setInputFiles(documentPath);
  await page.getByRole("button", { name: /upload and index/i }).click();
  await page.getByText("Ready", { exact: true }).waitFor({ timeout: 30_000 });
  await shoot(page, "03-document-indexed");

  console.log("Returning to the composer ...");
  await page.goto(BASE_URL);
  await page.waitForURL(/\/(?!knowledge)/, { timeout: 10_000 });

  await page.getByLabel(/research question/i).fill(DEMO_QUERY);

  console.log("Scoping research to the uploaded private document ...");
  await page.locator("button.knowledge-button").click();
  await page.locator(".knowledge-option", { hasText: DOCUMENT_FILENAME }).click();
  await page.keyboard.press("Escape");
  await shoot(page, "04-composer-scoped-to-private-doc");

  await page.getByRole("button", { name: /start research/i }).click();
  await page.waitForURL(/\/runs\//, { timeout: 15_000 });
  await shoot(page, "05-run-started");

  console.log("Waiting for the agent workflow to progress (this is a real deep-research run) ...");
  await page.waitForTimeout(20_000);
  await shoot(page, "06-agent-workflow-in-progress");

  const evidenceToggle = page.getByRole("button", { name: /inspect evidence/i });
  await evidenceToggle.waitFor({ timeout: 8 * 60_000 }).catch(() => {
    console.warn("Report did not appear within 8 minutes; capturing current state anyway.");
  });
  await shoot(page, "07-report-completed");

  if (await evidenceToggle.isVisible().catch(() => false)) {
    await evidenceToggle.click();
    await shoot(page, "08-evidence-with-private-source");
  }

  console.log("Demo flow complete.");
} finally {
  await context.close();
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
