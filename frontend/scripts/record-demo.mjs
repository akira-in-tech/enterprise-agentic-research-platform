// One-off demo recorder for the deployed AWS staging app.
// Not part of the committed test suite -- a scratch utility for producing
// LinkedIn/README demo assets against a real, live deployment.
//
// Usage:
//   BASE_URL=https://<cloudfront-domain> node record-demo.mjs
//
// Produces, in this script's directory:
//   video/           -- a .webm recording of the whole flow (Playwright native)
//   demo.mp4         -- converted via the bundled ffmpeg binary
//   demo.gif         -- a lightweight loop for embedding in README.md
//   screenshots/*.png -- clean stills at each key moment

import { chromium } from "playwright";
import { spawnSync } from "node:child_process";
import { mkdirSync } from "node:fs";
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

const DEMO_QUERY = "Compare HTTP/2 and HTTP/3 using current technical sources.";
const DEMO_EMAIL = `demo-${Date.now()}@example.com`;
const DEMO_PASSWORD = "correct-horse-battery-demo-9";

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
  await shoot(page, "02-home-signed-in");

  console.log(`Submitting research query: ${DEMO_QUERY}`);
  await page.getByLabel(/research question/i).fill(DEMO_QUERY);
  await shoot(page, "03-composer-filled");

  await page.getByRole("button", { name: /start research/i }).click();
  await page.waitForURL(/\/runs\//, { timeout: 15_000 });
  await shoot(page, "04-run-started");

  console.log("Waiting for the agent workflow to progress (this is a real deep-research run) ...");
  // Capture the eight-agent flow diagram mid-run -- one of the project's
  // most distinctive visuals -- before waiting for full completion.
  await page.waitForTimeout(20_000);
  await shoot(page, "05-agent-workflow-in-progress");

  // The detail page renders the report in place once it's ready (no
  // separate navigation) -- the evidence toggle only exists once the
  // report has loaded, so waiting on it is a reliable completion signal.
  const evidenceToggle = page.getByRole("button", { name: /inspect evidence/i });
  await evidenceToggle.waitFor({ timeout: 8 * 60_000 }).catch(() => {
    console.warn("Report did not appear within 8 minutes; capturing current state anyway.");
  });
  await shoot(page, "06-report-or-in-progress");

  if (await evidenceToggle.isVisible().catch(() => false)) {
    await evidenceToggle.click();
    await shoot(page, "07-evidence-expanded");
  }

  console.log("Demo flow complete.");
} finally {
  await context.close();
  await browser.close();
}

// context.close() finalizes the .webm file; find it and convert.
import { readdirSync, renameSync } from "node:fs";
const webmFiles = readdirSync(videoDir).filter((f) => f.endsWith(".webm"));
if (webmFiles.length === 0) {
  console.error("No video file was produced.");
  process.exit(1);
}
const rawWebm = path.join(videoDir, webmFiles[0]);
const finalWebm = path.join(__dirname, "demo.webm");
renameSync(rawWebm, finalWebm);

console.log("Converting to mp4 ...");
spawnSync(FFMPEG, ["-y", "-i", finalWebm, "-c:v", "libx264", "-pix_fmt", "yuv420p", path.join(__dirname, "demo.mp4")], {
  stdio: "inherit",
});

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
