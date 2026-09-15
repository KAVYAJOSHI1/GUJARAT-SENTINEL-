import { chromium } from "playwright-core";
import fs from "fs";

const BASE = "http://localhost:3000";
const USER = process.env.ADMIN_USERNAME;
const PASS = process.env.ADMIN_PASSWORD;
const VIDEO_DIR = "/home/lenovo/Desktop/GUJARAT-SENTINEL/pitch_video/full_demo_raw";
const LOG_PATH = "/home/lenovo/Desktop/GUJARAT-SENTINEL/pitch_video/full_demo_timeline.json";
fs.mkdirSync(VIDEO_DIR, { recursive: true });

const INC = "88708683-c1ec-45d7-a64d-db61177a3690";
const CASE = "199198c8-8dc4-4b7a-966a-8f3ac22df6e6";

let recordingStart = null;
const timeline = [];
const sectionErrors = [];

function easeInOutQuad(t) { return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; }

async function smoothMoveTo(page, x, y, opts = {}) {
  const steps = opts.steps ?? 22;
  const start = page.__mouse || { x: 960, y: 540 };
  for (let i = 1; i <= steps; i++) {
    const p = easeInOutQuad(i / steps);
    await page.mouse.move(start.x + (x - start.x) * p, start.y + (y - start.y) * p);
    await page.waitForTimeout(9);
  }
  page.__mouse = { x, y };
}
async function smoothClick(page, locator, opts = {}) {
  const el = typeof locator === "string" ? page.locator(locator).first() : locator;
  await el.scrollIntoViewIfNeeded().catch(() => {});
  const box = await el.boundingBox();
  if (!box) throw new Error("element not visible for click");
  await smoothMoveTo(page, box.x + box.width / 2, box.y + box.height / 2);
  await page.waitForTimeout(250);
  await el.click({ force: opts.force ?? false, timeout: 5000 });
  await page.waitForTimeout(opts.after ?? 600);
}
async function smoothHover(page, locator, ms = 1000) {
  const el = typeof locator === "string" ? page.locator(locator).first() : locator;
  await el.scrollIntoViewIfNeeded().catch(() => {});
  const box = await el.boundingBox({ timeout: 3000 }).catch(() => null);
  if (!box) return;
  await smoothMoveTo(page, box.x + box.width / 2, box.y + box.height / 2);
  await page.waitForTimeout(ms);
}
async function smoothScroll(page, deltaY, steps = 14) {
  for (let i = 0; i < steps; i++) { await page.mouse.wheel(0, deltaY / steps); await page.waitForTimeout(55); }
}
async function typeSlowly(page, locator, text, delay = 60) {
  const el = typeof locator === "string" ? page.locator(locator).first() : locator;
  await el.click({ timeout: 5000 });
  await el.type(text, { delay });
}
async function runSection(page, name, route, purpose, fn) {
  const t0 = (Date.now() - recordingStart) / 1000;
  timeline.push({ name, route, purpose, start: Number(t0.toFixed(2)), end: null });
  console.log(`>>> [${t0.toFixed(1)}s] START ${name}`);
  try {
    await fn();
  } catch (e) {
    console.log(`    !! ${name} sub-step failed (continuing): ${e.message?.slice(0, 200)}`);
    sectionErrors.push({ name, error: String(e.message || e).slice(0, 300) });
    await page.waitForTimeout(800);
  }
  const t1 = (Date.now() - recordingStart) / 1000;
  timeline[timeline.length - 1].end = Number(t1.toFixed(2));
  console.log(`<<< [${t1.toFixed(1)}s] END ${name} (${(t1 - t0).toFixed(1)}s)`);
}

async function main() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: "/home/lenovo/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome",
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    recordVideo: { dir: VIDEO_DIR, size: { width: 1920, height: 1080 } },
  });
  const page = await context.newPage();
  page.__mouse = { x: 960, y: 540 };
  const consoleErrors = [];
  page.on("pageerror", (e) => consoleErrors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text()); });

  recordingStart = Date.now();

  // ---------- LANDING PAGE: full smooth scroll, riding the site's own Lenis easing ----------
  await runSection(page, "Landing Page", "/", "Full smooth scroll through the entire cinematic landing page", async () => {
    await page.goto(BASE + "/", { waitUntil: "load", timeout: 20000 });
    await page.waitForTimeout(2500);
    const scrollable = await page.evaluate(() => document.documentElement.scrollHeight - window.innerHeight);
    const stepMs = 1250; // just past Lenis's 1.05s animation duration, so each nudge fully settles
    const introMs = 2500, outroMs = 3000;
    const steps = Math.max(8, Math.round((60000 - introMs - outroMs) / stepMs));
    const delta = scrollable / steps;
    for (let i = 0; i < steps; i++) {
      await page.mouse.wheel(0, delta);
      await page.waitForTimeout(stepMs);
    }
    await page.waitForTimeout(outroMs);
  });

  // ---------- LOGIN: via the real inline form the scroll lands on ----------
  await runSection(page, "Login", "/", "Signing in via the landing page's own inline form", async () => {
    await typeSlowly(page, page.locator('input[autocomplete="username"]'), USER, 95);
    await page.waitForTimeout(450);
    await typeSlowly(page, page.locator('input[autocomplete="current-password"]'), PASS, 95);
    await page.waitForTimeout(650);
    await smoothClick(page, page.getByRole("button", { name: "Enter Command Center", exact: true }), { after: 2200 });
  });

  await runSection(page, "Command Center", "/command-center", "Statewide overview: alerts, cameras, map, quick actions", async () => {
    await page.waitForTimeout(2500);
    await smoothHover(page, "text=Active Alerts", 1800);
    await smoothHover(page, "text=Live Situation", 2500);
    await smoothHover(page, "text=Camera Health", 1800);
    await smoothHover(page, "text=Recent Anomalies", 1800);
    await smoothScroll(page, 300, 8);
    await page.waitForTimeout(1500);
  });

  await runSection(page, "Live Monitoring Wall", "/live-monitoring", "Multi-camera honest-playback wall", async () => {
    await page.goto(BASE + "/live-monitoring", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3500);
    await smoothHover(page, "text=Paldi Circle", 1800);
    const grid1 = page.getByRole("button", { name: "1×1" });
    if (await grid1.count()) await smoothClick(page, grid1, { after: 2500 });
    const grid3 = page.getByRole("button", { name: "3×3" });
    if (await grid3.count()) await smoothClick(page, grid3, { after: 2500 });
    await page.waitForTimeout(2000);
  });

  await runSection(page, "Camera Network", "/cameras", "Operational camera grid with live status", async () => {
    await page.goto(BASE + "/cameras", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);
    await smoothHover(page, "text=Income Tax Circle", 1500);
    await smoothHover(page, "text=Naranpura Telephone Exchange", 1500);
  });

  await runSection(page, "Camera Detail Modal", "/cameras (modal)", "Per-camera health, metadata, detection frame", async () => {
    await smoothClick(page, page.getByText("Paldi Circle").first(), { after: 2500 });
    await page.waitForTimeout(2500);
    await smoothHover(page, "text=HEALTH HISTORY", 1500);
    await smoothHover(page, "text=LAST DETECTION", 1200);
    await page.keyboard.press("Escape");
    await page.waitForTimeout(700);
  });

  await runSection(page, "Camera Management", "/cameras/manage", "Admin registry: source, health, coordinates", async () => {
    await page.goto(BASE + "/cameras/manage", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3200);
    await smoothHover(page, "text=CAM-07", 1500);
    await page.waitForTimeout(1500);
  });

  await runSection(page, "Camera Reliability Intelligence", "/camera-intelligence", "Health-based reliability + video quality scoring", async () => {
    await page.goto(BASE + "/camera-intelligence", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3200);
    await smoothHover(page, "text=Naranpura Telephone Exchange", 2000);
    await smoothHover(page, "text=Usmanpura Char Rasta", 1500);
    await page.waitForTimeout(1200);
  });

  await runSection(page, "Global Search (Command Palette)", "any page", "Ctrl+K instant entity search", async () => {
    await smoothClick(page, page.locator('button[title="Command palette (Ctrl+K)"]'), { after: 900 });
    const paletteInput = page.locator('input[placeholder*="CAM-07"]');
    await typeSlowly(page, paletteInput, "GJ18TC0450", 75);
    await page.waitForTimeout(2200);
    await page.keyboard.press("Escape");
    await page.waitForTimeout(600);
  });

  await runSection(page, "Advanced Investigation Search", "/search", "Structured filters + plain-English AI search", async () => {
    await page.goto(BASE + "/search", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2200);
    const plateExact = page.locator('input[placeholder="Plate (exact)"]');
    if (await plateExact.count()) { await smoothHover(page, plateExact, 900); }
    await typeSlowly(page, 'input[placeholder*="Ask in plain English"]', "vehicles detected near CAM-04 after 9 PM", 45);
    await page.waitForTimeout(700);
    await smoothClick(page, page.getByRole("button", { name: /ai search/i }), { after: 3200 });
    await smoothScroll(page, 300, 8);
    await page.waitForTimeout(1200);
  });

  await runSection(page, "Alert Log", "/alerts", "Watchlist + anomaly alerts, escalation workflow", async () => {
    await page.goto(BASE + "/alerts", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);
    await smoothHover(page, page.getByRole("button", { name: "Investigate" }).first(), 1800);
    await smoothHover(page, page.getByRole("button", { name: "View evidence" }).first(), 1800);
    await smoothHover(page, page.getByRole("button", { name: "Escalate" }).first(), 1500);
    await page.waitForTimeout(1200);
  });

  await runSection(page, "Watchlist Management", "/watchlists", "Wanted/stolen plate registry", async () => {
    await page.goto(BASE + "/watchlists", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3200);
    await smoothHover(page, "text=GJ18TC0450", 2000);
    await page.waitForTimeout(1200);
  });

  await runSection(page, "Vehicle Investigation Workspace", "/workspace", "Unified sightings + evidence + timeline + map", async () => {
    await page.goto(BASE + "/workspace", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2200);
    await typeSlowly(page, page.locator('input[placeholder="Registration plate…"]'), "GJ18TC0450", 85);
    await page.keyboard.press("Enter");
    await page.waitForTimeout(4500);
    await smoothHover(page, "text=Ask SENTINEL", 1200).catch(() => {});
    await smoothScroll(page, 500, 12);
    await page.waitForTimeout(2200);
    await smoothScroll(page, 500, 12);
    await page.waitForTimeout(2200);
    await smoothScroll(page, 500, 12);
    await page.waitForTimeout(2000);
  });

  await runSection(page, "GIS Investigation Console", "/investigation", "Chronological journey plotted on the map", async () => {
    await page.goto(BASE + "/investigation", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2200);
    await typeSlowly(page, 'input[placeholder="GJ01AB1234"]', "GJ18TC0450", 85);
    await smoothClick(page, page.getByRole("button", { name: "Search", exact: true }).first(), { after: 3800 });
    const mapEl = page.locator(".gis-map").first();
    if (await mapEl.count()) {
      await mapEl.scrollIntoViewIfNeeded();
      await page.waitForTimeout(2800);
    } else {
      await smoothScroll(page, 2000, 14);
      await page.waitForTimeout(1500);
    }
    const playBtn = page.getByRole("button", { name: /play/i });
    if (await playBtn.count()) await smoothClick(page, playBtn, { after: 2500 });
    await page.waitForTimeout(1500);
  });

  await runSection(page, "Investigation Graph", "/graph", "Deterministic entity relationship graph", async () => {
    await page.goto(BASE + "/graph", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1800);
    await typeSlowly(page, page.locator('input[placeholder="Registration plate…"]'), "GJ18TC0450", 85);
    await smoothClick(page, page.getByRole("button", { name: /build/i }), { after: 3000 });
    await smoothHover(page, "text=CASE-2026-9001", 1800);
    await smoothHover(page, "text=mockcam01", 1500).catch(() => {});
    await page.waitForTimeout(1500);
  });

  await runSection(page, "Traffic Intelligence", "/traffic", "Live vehicle-flow aggregates + heatmap", async () => {
    await page.goto(BASE + "/traffic", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3200);
    await smoothScroll(page, 500, 12);
    await page.waitForTimeout(2200);
    await smoothHover(page, "text=Density heatmap", 1500).catch(() => {});
  });

  await runSection(page, "AI Anomaly Detection", "/anomalies", "Wrong-way, restricted-zone, stopped-vehicle detection", async () => {
    await page.goto(BASE + "/anomalies", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);
    await smoothHover(page, "text=RESTRICTED-ZONE ENTRY", 2200);
    await smoothHover(page, "text=WRONG-WAY MOVEMENT", 1800);
    await page.waitForTimeout(1200);
  });

  await runSection(page, "ANPR Intelligence", "/anpr-intelligence", "Plate-recognition throughput and quality", async () => {
    await page.goto(BASE + "/anpr-intelligence", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3200);
    await smoothHover(page, "text=FAILURE REASONS", 1500);
    await page.waitForTimeout(1200);
  });

  await runSection(page, "AI Copilot", "/copilot", "Deterministic natural-language investigation assistant", async () => {
    await page.goto(BASE + "/copilot", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2200);
    await smoothClick(page, page.getByText("Show the journey of GJ18TC0450."), { after: 3500 });
    await smoothScroll(page, 400, 10);
    await page.waitForTimeout(2500);
    await smoothScroll(page, 400, 10);
    await page.waitForTimeout(2000);
  });

  await runSection(page, "Incident Detail", `/incidents/${INC}`, "Full incident workflow: evidence, AI summary, notes", async () => {
    await page.goto(BASE + `/incidents/${INC}`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2800);
    await smoothHover(page, "text=Evidence", 1500);
    const genBtn = page.getByRole("button", { name: /generate ai summary/i });
    if (await genBtn.count()) await smoothClick(page, genBtn, { after: 3200 });
    await smoothScroll(page, 400, 10);
    await page.waitForTimeout(1500);
  });

  await runSection(page, "Case Detail", `/cases/${CASE}`, "Case grouping incidents + evidence, report export", async () => {
    await page.goto(BASE + `/cases/${CASE}`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2800);
    await smoothHover(page, "text=Export Case Report", 1500);
    await smoothScroll(page, 400, 10);
    await page.waitForTimeout(2200);
    await smoothScroll(page, 400, 10);
    await page.waitForTimeout(1500);
  });

  await runSection(page, "Reports Center", "/reports", "One-click CSV/PDF operational reports", async () => {
    await page.goto(BASE + "/reports", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3200);
    await smoothHover(page, "text=Vehicle Journey Report", 1500);
    await page.waitForTimeout(1200);
  });

  await runSection(page, "My Work Queue", "/my-work", "Personal urgent/overdue work bucket", async () => {
    await page.goto(BASE + "/my-work", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3200);
    await page.waitForTimeout(1200);
  });

  await runSection(page, "Operations Dashboard", "/dashboard", "Legacy dense single-page ops view", async () => {
    await page.goto(BASE + "/dashboard", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);
  });

  await runSection(page, "GIS Camera Map", "/map", "Standalone clustered camera map", async () => {
    await page.goto(BASE + "/map", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3200);
    await smoothScroll(page, -200, 6);
    await page.waitForTimeout(1200);
  });

  await runSection(page, "System / Observability", "/system", "Pipeline health, capacity model, notifications", async () => {
    await page.goto(BASE + "/system", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3200);
    await smoothScroll(page, 500, 12);
    await page.waitForTimeout(2200);
    await smoothScroll(page, 500, 12);
    await page.waitForTimeout(1500);
  });

  await runSection(page, "Admin Audit Log", "/admin", "Append-only privileged-action record", async () => {
    await page.goto(BASE + "/admin", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3200);
    await smoothHover(page, "text=EVIDENCE_ACCESSED", 1200).catch(() => {});
  });

  await runSection(page, "Final System Overview", "/command-center", "Closing shot of the complete platform", async () => {
    await page.goto(BASE + "/command-center", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(4500);
  });

  const totalDuration = (Date.now() - recordingStart) / 1000;
  fs.writeFileSync(LOG_PATH, JSON.stringify({ timeline, totalDuration, consoleErrors, sectionErrors }, null, 2));
  console.log("TOTAL_DURATION_S:", totalDuration.toFixed(1));
  console.log("SECTION_ERRORS:", JSON.stringify(sectionErrors));
  console.log("CONSOLE_ERRORS_COUNT:", consoleErrors.length);

  await context.close();
  await browser.close();
}

main().catch((e) => { console.error("FATAL:", e); process.exit(1); });
