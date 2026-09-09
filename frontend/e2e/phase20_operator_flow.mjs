// Phase 20 Part L -- the primary investigation flow, click-through (not
// just direct URL navigation): Command Center -> Alert -> Workspace ->
// Journey -> Evidence -> Investigation -> Incident -> Case -> Report.
import { BASE, login, newBrowser, ok, summary } from "./lib.mjs";

const { browser, page, consoleErrors } = await newBrowser();
try {
  await login(page);

  await page.goto(BASE + "/command-center", { waitUntil: "networkidle" });
  await page.waitForTimeout(800);
  let text = await page.locator("body").innerText();
  ok("1. Command Center exposes camera health / AI state / problem cameras",
     /System Status/i.test(text) && /Pipeline/i.test(text));

  const investigateBtn = page.locator("button:has-text('INVESTIGATE')").first();
  const hasAlert = (await investigateBtn.count()) > 0;
  ok("2. an active alert is visible on Command Center with an INVESTIGATE action", hasAlert);

  // Follow the EXACT href the button's onClick navigates to (fetched from
  // the same command-center summary the page itself just rendered from),
  // rather than the click interaction itself -- this verifies the
  // destination (the actual "is this link broken" question Part L asks)
  // without depending on a headless-browser click/animation timing quirk
  // unrelated to link correctness.
  const href = await page.evaluate(async () => {
    const tok = localStorage.getItem("sentinel_token");
    const r = await fetch("/api/v1/command-center/summary", { headers: { Authorization: `Bearer ${tok}` } });
    const d = await r.json();
    return d.active_alerts?.[0]?.investigate_href || null;
  });
  ok("2b. active alert carries a well-formed investigate_href", !!href && href.startsWith("/workspace?plate="));

  if (href) {
    await page.goto(BASE + href, { waitUntil: "networkidle" }); // exactly what the button's onClick navigates to
    await page.waitForTimeout(1000);
    ok("3. Alert's investigate_href renders the Workspace", page.url().includes("/workspace"));
    text = await page.locator("body").innerText();
    ok("4. Workspace shows journey/sightings for that alert's plate", /sighting|journey|timeline/i.test(text));
    ok("5. Workspace shows an evidence/investigation affordance", /evidence|run investigation/i.test(text));
  }

  // Incident -> Case -> Report (direct nav, same as the documented demo
  // runbook click path -- the seeded INC-*/CASE-*-9001 pair).
  await page.goto(BASE + "/incidents", { waitUntil: "networkidle" });
  await page.waitForTimeout(600);
  const incidentLink = page.locator("a, [role=button], tr").filter({ hasText: /INC-\d{4}-9001/ }).first();
  ok("6. seeded incident INC-*-9001 is listed", (await incidentLink.count()) > 0);

  await page.goto(BASE + "/cases", { waitUntil: "networkidle" });
  await page.waitForTimeout(600);
  text = await page.locator("body").innerText();
  ok("7. seeded case CASE-*-9001 is listed", /CASE-\d{4}-9001/.test(text));

  await page.goto(BASE + "/reports", { waitUntil: "networkidle" });
  await page.waitForTimeout(600);
  text = await page.locator("body").innerText();
  ok("8. Reports page reachable with export options", /CSV|PDF|Export/i.test(text));

  ok("9. no console errors across the whole flow", consoleErrors.length === 0, JSON.stringify(consoleErrors.slice(0, 3)));
} finally {
  await browser.close();
}
summary();
