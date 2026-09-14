import { chromium } from "playwright-core";
import fs from "fs";

const BASE = "http://localhost:3000";
const USER = process.env.ADMIN_USERNAME;
const PASS = process.env.ADMIN_PASSWORD;
const OUT = "/tmp/claude-1000/-home-lenovo-Desktop-GUJARAT-SENTINEL/1a9d0b78-8313-4fb7-8bef-3eed1ffbfe8e/scratchpad/crawl";
fs.mkdirSync(OUT, { recursive: true });

const INC = "47917f40-b899-49ac-bd31-0c7634e2a091";
const CASE = "a191f4a6-1536-4cf7-8a54-399c1c8017ef";

const ROUTES = [
  ["home", "/"],
  ["command-center", "/command-center"],
  ["dashboard", "/dashboard"],
  ["live-monitoring", "/live-monitoring"],
  ["cameras", "/cameras"],
  ["cameras-manage", "/cameras/manage"],
  ["alerts", "/alerts"],
  ["incidents", "/incidents"],
  ["incident-detail", `/incidents/${INC}`],
  ["cases", "/cases"],
  ["case-detail", `/cases/${CASE}`],
  ["search", "/search"],
  ["watchlists", "/watchlists"],
  ["my-work", "/my-work"],
  ["reports", "/reports"],
  ["copilot", "/copilot"],
  ["anomalies", "/anomalies"],
  ["traffic", "/traffic"],
  ["camera-intelligence", "/camera-intelligence"],
  ["anpr-intelligence", "/anpr-intelligence"],
  ["graph", "/graph"],
  ["workspace", "/workspace"],
  ["system", "/system"],
  ["admin", "/admin"],
  ["investigation", "/investigation"],
  ["map", "/map"],
];

const browser = await chromium.launch({
  headless: true,
  executablePath: "/home/lenovo/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome",
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
const allErrors = {};

await page.goto(BASE + "/", { waitUntil: "domcontentloaded", timeout: 20000 });
await page.waitForTimeout(800);
await page.getByRole("button", { name: /^sign in$/i }).first().click();
await page.waitForTimeout(800);
const inputs = page.locator("input");
await inputs.first().waitFor({ timeout: 10000 });
await inputs.nth(0).fill(USER);
await inputs.nth(1).fill(PASS);
await page.getByRole("button", { name: "Enter Command Center", exact: true }).click();
await page.waitForTimeout(2000);

for (const [name, route] of ROUTES) {
  const errors = [];
  const onConsole = (m) => { if (m.type() === "error") errors.push(m.text()); };
  const onErr = (e) => errors.push("pageerror: " + e.message);
  page.on("console", onConsole);
  page.on("pageerror", onErr);

  await page.goto(BASE + route, { waitUntil: "domcontentloaded", timeout: 20000 }).catch((e) => errors.push("goto: " + e.message));
  await page.waitForTimeout(2500);
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true }).catch(() => {});
  const text = await page.locator("body").innerText().catch(() => "");
  fs.writeFileSync(`${OUT}/${name}.txt`, text);

  page.off("console", onConsole);
  page.off("pageerror", onErr);
  allErrors[name] = errors;
}

fs.writeFileSync(`${OUT}/_errors.json`, JSON.stringify(allErrors, null, 2));
console.log("done");
await browser.close();
