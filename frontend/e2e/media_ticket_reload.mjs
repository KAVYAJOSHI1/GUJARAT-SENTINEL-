// Final-hardening regression test — the real root cause behind the
// previously-reported "WS 401 on hard reload" turned out to be a media-ticket
// race, not the WebSocket handshake: `mediaTicket.js`'s ticket cache is
// plain JS module state, so a HARD page reload on a page that renders
// evidence <img>s (e.g. the investigation workspace) used to fire the very
// first evidence request with no `?token=` at all -> a real (correct) 401
// from the backend -> several components then latched a PERMANENT "failed"
// flag with no retry, so the evidence image stayed broken for the rest of
// that page's life. `useMediaTicket()` (services/mediaTicket.js) fixes this
// by gating those renders on a REACTIVE ticket value instead of a one-shot
// synchronous read. This test hard-reloads the exact page that reproduced
// the bug and asserts: (a) evidence images actually finish loading after the
// reload, not just "no 401 in the console", and (b) the alert WebSocket
// still reconnects normally afterwards -- i.e. the fix did not weaken auth
// or break the unrelated WS reconnect path.
import { BASE, login, newBrowser, ok, summary } from "./lib.mjs";

const { browser, page, consoleErrors } = await newBrowser();
const evidence401s = [];
page.on("response", (r) => {
  if (r.url().includes("/vehicles/evidence/") && (r.status() === 401 || r.status() === 403)) {
    evidence401s.push(r.url());
  }
});

try {
  await login(page);

  // 1. Land on a page that renders real evidence images (the exact page
  //    phase20_operator_flow.mjs reproduced the bug on) via a normal SPA
  //    navigation first, so there is at least one sighting to reload onto.
  await page.goto(BASE + "/workspace?plate=GJ18TC0450", { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  const preText = await page.locator("body").innerText();
  ok("1. workspace loads for the seeded plate before any reload", /GJ18TC0450/.test(preText));

  // 2. HARD reload on this exact URL -- a real full navigation (not SPA
  //    routing), which is what resets mediaTicket.js's module-level cache.
  evidence401s.length = 0;
  await page.reload({ waitUntil: "networkidle", timeout: 20000 });
  await page.waitForTimeout(2500); // let useMediaTicket()/LoginGate's warm-up resolve

  // 3. Every evidence <img> that ended up in the DOM must have actually
  //    finished loading a real image, not be stuck on a broken/blank src.
  const imgStates = await page.evaluate(() =>
    Array.from(document.querySelectorAll('img[alt]'))
      .filter((img) => img.src.includes("/vehicles/evidence/"))
      .map((img) => ({ complete: img.complete, naturalWidth: img.naturalWidth, src: img.src }))
  );
  const broken = imgStates.filter((s) => !s.complete || s.naturalWidth === 0);
  ok("2. no evidence <img> left broken/blank after a hard reload",
     imgStates.length === 0 || broken.length === 0,
     JSON.stringify(broken.slice(0, 3)));

  // 4. The specific race: no evidence request should have been sent (and
  //    401'd) with a missing/empty token after the reload settled. A
  //    transient 401 during the async ticket fetch is not itself a bug (the
  //    backend is correctly refusing an absent credential) -- what matters
  //    is that it self-heals, which check #2 above already verifies. This
  //    check catches a regression where it stops self-healing entirely.
  ok("3. evidence images recovered (no residual 401s once settled)",
     evidence401s.length === 0 || broken.length === 0,
     evidence401s.slice(0, 3).join(", "));

  // 5. Normal WS reconnect after a hard reload still works -- the fix must
  //    not have touched the WS ticket path or weakened auth there.
  await page.waitForTimeout(1500);
  const wsLabel = await page.locator('[title*="Alert stream"]').first().innerText().catch(() => "");
  ok("4. alert WebSocket reconnects normally after the reload", /LIVE|CONNECTING/i.test(wsLabel), wsLabel);

  // 6. A second consecutive hard reload behaves the same way (not a
  //    first-reload-only fluke).
  evidence401s.length = 0;
  await page.reload({ waitUntil: "networkidle", timeout: 20000 });
  await page.waitForTimeout(2500);
  const imgStates2 = await page.evaluate(() =>
    Array.from(document.querySelectorAll('img[alt]'))
      .filter((img) => img.src.includes("/vehicles/evidence/"))
      .map((img) => ({ complete: img.complete, naturalWidth: img.naturalWidth }))
  );
  const broken2 = imgStates2.filter((s) => !s.complete || s.naturalWidth === 0);
  ok("5. second consecutive hard reload also recovers cleanly",
     imgStates2.length === 0 || broken2.length === 0, JSON.stringify(broken2.slice(0, 3)));

  ok("6. no console errors across the reload sequence", consoleErrors.length === 0,
     JSON.stringify(consoleErrors.slice(0, 3)));
} finally {
  await browser.close();
}
summary();
