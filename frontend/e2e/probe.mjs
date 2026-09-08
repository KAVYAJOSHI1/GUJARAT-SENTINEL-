import { BASE, login, newBrowser } from "./lib.mjs";

const ROUTES = [
  "/", "/command-center", "/live-monitoring", "/alerts", "/search", "/workspace",
  "/investigation", "/incidents", "/cases", "/graph", "/traffic", "/anomalies",
  "/anpr-intelligence", "/camera-intelligence", "/copilot", "/cameras",
  "/cameras/manage", "/my-work", "/reports", "/watchlists", "/system", "/admin",
  "/dashboard", "/map",
];

const { browser, page } = await newBrowser();
page.on("response", (r) => { if (r.status() >= 400) console.log("  RESP " + r.status() + " " + r.request().method() + " " + r.url()); });
page.on("console", (m) => { if (m.type() === "error") console.log("  CONS " + m.text().slice(0, 160)); });
try {
  await login(page);
  for (const r of ROUTES) {
    console.log(`\n=== ${r} ===`);
    await page.goto(BASE + r, { waitUntil: "networkidle", timeout: 20000 }).catch(() => {});
    await page.waitForTimeout(400);
  }
  console.log("\n=== palette + workspace ===");
  await page.goto(BASE + "/command-center", { waitUntil: "networkidle" });
  await page.waitForTimeout(500);
  await page.keyboard.press("Control+KeyK");
  await page.waitForTimeout(500);
  await page.locator('input[placeholder*="ask a question"]').fill("GJ18TC0450");
  await page.waitForTimeout(1100);
  await page.keyboard.press("Enter");
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(2000);
  console.log("\n=== copilot ===");
  await page.goto(BASE + "/copilot?q=" + encodeURIComponent("Investigate GJ18TC0450"), { waitUntil: "networkidle" });
  await page.waitForTimeout(3500);
} finally {
  await browser.close();
}
