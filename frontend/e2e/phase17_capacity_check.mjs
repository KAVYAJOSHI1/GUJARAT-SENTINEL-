// Phase 17 -- quick targeted check that the new CapacityPanel actually
// renders real content on /system (not just "the page didn't crash",
// which run-all.mjs's generic route sweep already covers).
import { BASE, login, newBrowser, ok, summary } from "./lib.mjs";

const { browser, page, consoleErrors } = await newBrowser();
try {
  await login(page);
  await page.goto(BASE + "/system", { waitUntil: "networkidle" });
  await page.waitForTimeout(1200);
  const text = await page.locator("body").innerText();
  ok("1. System Capacity panel title present", /System Capacity/i.test(text));
  ok("2. shows a degradation state badge", /HEALTHY|DEGRADED|OVERLOADED/.test(text));
  ok("3. shows the 80,000 scaling target", /80,000|80000/.test(text));
  ok("4. shows required-workers figure", /Required workers/i.test(text));
  ok("5. no console errors on /system", consoleErrors.length === 0, JSON.stringify(consoleErrors.slice(0, 3)));
} finally {
  await browser.close();
}
summary();
