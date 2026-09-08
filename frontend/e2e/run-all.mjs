// Phase 16 — the full 20-step browser acceptance run. Headless Chromium
// against the running dev server. Verifies real DOM rendering, navigation,
// global search, the investigation flow, and zero console errors.
import { BASE, login, newBrowser, noHorizontalOverflow, ok, summary } from "./lib.mjs";

const ROUTES = [
  "/", "/command-center", "/live-monitoring", "/alerts", "/search", "/workspace",
  "/investigation", "/incidents", "/cases", "/graph", "/traffic", "/anomalies",
  "/anpr-intelligence", "/camera-intelligence", "/copilot", "/cameras",
  "/cameras/manage", "/my-work", "/reports", "/watchlists", "/system", "/admin",
  "/dashboard", "/map",
];

const { browser, page, consoleErrors } = await newBrowser();
try {
  // 1. login
  await login(page);
  ok("1. login → app shell", !/sign in/i.test(await page.locator("body").innerText()));

  // 2. command center loads
  await page.goto(BASE + "/command-center", { waitUntil: "networkidle" });
  await page.waitForTimeout(1000);
  const ccText = await page.locator("body").innerText();
  ok("2. Command Center loads", /COMMAND CENTER/i.test(ccText) && /Active Alerts/i.test(ccText));
  ok("2b. Command Center has KPIs", /Vehicles Today/i.test(ccText) && /Open Incidents/i.test(ccText));
  ok("2c. no horizontal overflow (command center)", await noHorizontalOverflow(page));

  // 3. navigation — every route renders without a crash / console error
  let routeErrors = 0;
  for (const r of ROUTES) {
    const before = consoleErrors.length;
    await page.goto(BASE + r, { waitUntil: "networkidle", timeout: 20000 }).catch(() => {});
    await page.waitForTimeout(400);
    const bodyLen = (await page.locator("body").innerText().catch(() => "")).length;
    const newErrs = consoleErrors.slice(before);
    if (bodyLen < 20 || newErrs.length) { routeErrors++; console.log(`     ${r}: len=${bodyLen} errs=${JSON.stringify(newErrs.slice(0, 2))}`); }
  }
  ok(`3. all ${ROUTES.length} routes render clean`, routeErrors === 0, routeErrors + " problem route(s)");

  // 4. global command palette (Ctrl+K)
  await page.goto(BASE + "/command-center", { waitUntil: "networkidle" });
  await page.waitForTimeout(500);
  await page.keyboard.press("Control+KeyK");
  await page.waitForTimeout(500);
  const palInput = page.locator('input[placeholder*="ask a question"]');
  ok("4. Ctrl+K opens command palette", await palInput.count() > 0);

  // 5. search vehicle GJ18TC0450 via palette
  await palInput.fill("GJ18TC0450");
  await page.waitForTimeout(1100);
  const palText = await page.locator("body").innerText();
  ok("5. palette finds GJ18TC0450", /GJ18TC0450/.test(palText));
  await page.keyboard.press("Enter");
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(1200);

  // 6. vehicle profile / workspace
  const wsText = await page.locator("body").innerText();
  ok("6. workspace opens for the plate", /GJ18TC0450/.test(wsText) && /(Investigation Workspace|VEHICLE)/i.test(wsText));
  ok("6b. workspace shows sightings + cameras", /sighting/i.test(wsText) && /camera/i.test(wsText));

  // 7. journey timeline present
  ok("7. journey timeline present", /(JOURNEY|CAM-0)/i.test(wsText));

  // 8-9. select a journey event → evidence / detail changes
  const camChip = page.locator("text=/CAM-0[124]/").first();
  if (await camChip.count()) {
    await camChip.click().catch(() => {});
    await page.waitForTimeout(600);
  }
  ok("8-9. journey event interaction did not crash", (await page.locator("body").innerText()).length > 100);

  // 10. map interaction — a leaflet container rendered
  ok("10. GIS map rendered in workspace", await page.locator(".leaflet-container").count() > 0);

  // 11-13. open alert → incident → case
  await page.goto(BASE + "/alerts", { waitUntil: "networkidle" });
  await page.waitForTimeout(700);
  ok("11. alerts page lists alerts", /(alert|GJ18TC0450|watchlist)/i.test(await page.locator("body").innerText()));
  await page.goto(BASE + "/incidents", { waitUntil: "networkidle" });
  await page.waitForTimeout(600);
  ok("12. incidents page", /INC-/i.test(await page.locator("body").innerText()));
  await page.goto(BASE + "/cases", { waitUntil: "networkidle" });
  await page.waitForTimeout(600);
  ok("13. cases page", /CASE-/i.test(await page.locator("body").innerText()));

  // 14. AI investigation (copilot deep)
  await page.goto(BASE + "/copilot?q=" + encodeURIComponent("Investigate GJ18TC0450"), { waitUntil: "networkidle" });
  await page.waitForTimeout(3500);
  const cop = await page.locator("body").innerText();
  ok("14. AI investigation renders a grounded answer", /GJ18TC0450/.test(cop) && /(sighting|camera|READ-ONLY|not available)/i.test(cop));

  // 15. investigation graph
  await page.goto(BASE + "/graph?plate=GJ18TC0450", { waitUntil: "networkidle" });
  await page.waitForTimeout(2000);
  ok("15. investigation graph renders nodes", await page.locator("svg").count() > 0 && /(detection|camera|vehicle)/i.test(await page.locator("body").innerText()));

  // 16. report page
  await page.goto(BASE + "/reports", { waitUntil: "networkidle" });
  await page.waitForTimeout(700);
  ok("16. reports page has CSV/PDF export", /(CSV|PDF|Report)/i.test(await page.locator("body").innerText()));

  // 17-20. intelligence dashboards
  for (const [n, r, needle] of [
    ["17. camera intelligence", "/camera-intelligence", /Reliability|Video quality|Health/i],
    ["18. ANPR dashboard", "/anpr-intelligence", /ANPR|success rate|failure/i],
    ["19. traffic dashboard", "/traffic", /Traffic|Congestion|Peak/i],
    ["20. system health", "/system", /Observability|Pipeline|System/i],
  ]) {
    await page.goto(BASE + r, { waitUntil: "networkidle" });
    await page.waitForTimeout(900);
    ok(n, needle.test(await page.locator("body").innerText()));
  }

  // console errors gate — real app errors only
  const realErrors = consoleErrors.filter((e) =>
    !/favicon|ResizeObserver|X-Evidence-Status|EVIDENCE IMAGE NOT AVAILABLE/.test(e));
  ok("CONSOLE: zero real errors across the whole run", realErrors.length === 0, realErrors.slice(0, 6).join(" | "));
} catch (e) {
  ok("run completed without an exception", false, String(e).slice(0, 300));
} finally {
  await browser.close();
  summary();
}
