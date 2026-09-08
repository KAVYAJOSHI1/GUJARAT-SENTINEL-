// Phase 16 — shared helpers for the headless-browser UI validation suite.
import { chromium } from "playwright-core";

export const BASE = process.env.E2E_BASE_URL || "http://localhost:3000";
export const API = process.env.E2E_API_URL || "http://localhost:8001";
const PW = process.env.E2E_ADMIN_PASSWORD || "admin";

let _pass = 0;
let _fail = 0;
const _failures = [];

export function ok(name, cond, detail = "") {
  if (cond) { _pass++; console.log(`  \x1b[32mPASS\x1b[0m ${name}`); }
  else { _fail++; _failures.push(name + (detail ? ` — ${detail}` : "")); console.log(`  \x1b[31mFAIL\x1b[0m ${name}${detail ? " — " + detail : ""}`); }
}

export function summary() {
  console.log(`\n${_pass} passed, ${_fail} failed`);
  if (_failures.length) { console.log("FAILURES:"); _failures.forEach((f) => console.log("  - " + f)); }
  process.exit(_fail ? 1 : 0);
}

export async function newBrowser() {
  const browser = await chromium.launch({ headless: true, args: ["--no-sandbox", "--disable-dev-shm-usage"] });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const consoleErrors = [];
  page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text()); });
  // set E2E_TRACE_AUTH=1 to print any 401/403 URL (diagnosing an auth race)
  if (process.env.E2E_TRACE_AUTH) {
    page.on("response", (r) => {
      if (r.status() === 401 || r.status() === 403)
        console.log("   [HTTP " + r.status() + "] " + r.request().method() + " " + r.url());
    });
  }
  page.on("pageerror", (e) => consoleErrors.push("pageerror: " + e.message));
  page.on("requestfailed", (r) => {
    const u = r.url();
    if (u.startsWith(BASE) && !u.includes("favicon")) consoleErrors.push("reqfail: " + u + " " + (r.failure()?.errorText || ""));
  });
  return { browser, ctx, page, consoleErrors };
}

export async function login(page) {
  await page.goto(BASE + "/", { waitUntil: "domcontentloaded", timeout: 20000 });
  // login form
  await page.waitForSelector('input', { timeout: 10000 });
  const inputs = page.locator("input");
  await inputs.nth(0).fill("admin");
  await inputs.nth(1).fill(PW);
  await page.getByRole("button", { name: /sign in|log ?in/i }).click();
  await page.waitForLoadState("networkidle", { timeout: 15000 });
  await page.waitForTimeout(800);
}

export async function noHorizontalOverflow(page) {
  return page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 2);
}
