// Frontend smoke test (Playwright/Chromium) against a running stack.
//   BASE_URL=https://localhost:8443 ADMIN_EMAIL=... ADMIN_PASSWORD=... node tests/smoke.mjs
// Run without installing anything locally:  ./scripts/frontend-smoke.sh
import { chromium } from "playwright";

const BASE = process.env.BASE_URL || "https://localhost:8443";
const EMAIL = process.env.ADMIN_EMAIL;
const PASSWORD = process.env.ADMIN_PASSWORD;
if (!EMAIL || !PASSWORD) throw new Error("ADMIN_EMAIL / ADMIN_PASSWORD required");

const PAGES = [
  ["/", "داشبورد"],
  ["/jobs", "آگهی‌ها"],
  ["/companies", "شرکت‌ها"],
  ["/insights", "تحلیل بازار"],
  ["/alerts", "جست‌وجوها و هشدارها"],
  ["/sources", "منابع و پوشش داده"],
  ["/settings", "تنظیمات"],
];

let failures = 0;
const ok = (m) => console.log(`  ✓ ${m}`);
const fail = (m) => { failures++; console.log(`  ✗ ${m}`); };

const browser = await chromium.launch();
for (const [label, viewport] of [["desktop", { width: 1366, height: 900 }], ["mobile", { width: 390, height: 844 }]]) {
  console.log(`\n[${label}]`);
  const ctx = await browser.newContext({ ignoreHTTPSErrors: true, viewport, locale: "fa-IR" });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => m.type() === "error" && errors.push(`console: ${m.text()}`));

  await page.goto(`${BASE}/jobs`);
  await page.waitForURL(/\/login/);
  ok("unauthenticated -> /login");
  await page.fill("#email", EMAIL);
  await page.fill("#password", PASSWORD);
  await page.click("button[type=submit]");
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
  ok("login");
  errors.length = 0; // the 401s of the pre-login redirect are expected

  for (const [path, heading] of PAGES) {
    await page.goto(`${BASE}${path}`);
    try {
      await page.getByRole("heading", { level: 1, name: heading }).waitFor({ timeout: 15000 });
      await page.waitForLoadState("networkidle");
      const dir = await page.evaluate(() => document.documentElement.dir);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      const errBox = await page.locator("[data-error-box]").count();
      if (dir !== "rtl") fail(`${path}: dir=${dir}`);
      else if (overflow > 2) fail(`${path}: horizontal page scroll (${overflow}px)`);
      else if (errBox) fail(`${path}: error box shown: ${await page.locator("[data-error-box]").first().innerText()}`);
      else ok(`${path} renders "${heading}" (rtl, no page overflow)`);
    } catch (e) {
      fail(`${path}: ${e.message.split("\n")[0]}`);
    }
  }

  // a job detail page, if any job exists
  await page.goto(`${BASE}/jobs`);
  await page.waitForLoadState("networkidle");
  const first = page.locator("a[href^='/jobs/']:visible").first();
  if (await first.count()) {
    await first.click();
    await page.getByText("شرح آگهی").waitFor({ timeout: 15000 });
    ok(`job detail ${new URL(page.url()).pathname}`);
  } else ok("no jobs yet - job detail skipped");

  // dark mode toggle
  await page.goto(`${BASE}/`);
  await page.getByRole("heading", { level: 1 }).waitFor();
  const before = await page.evaluate(() => document.documentElement.classList.contains("dark"));
  await page.getByRole("button", { name: /حالت (تاریک|روشن)/ }).click();
  const after = await page.evaluate(() => document.documentElement.classList.contains("dark"));
  before !== after ? ok(`theme toggle (${before ? "dark" : "light"} -> ${after ? "dark" : "light"})`) : fail("theme toggle had no effect");

  const real = errors.filter((e) => !/favicon|telegram-web-app/i.test(e));
  real.length ? fail(`JS errors: ${real.slice(0, 5).join(" | ")}`) : ok("no JS errors in console");
  await ctx.close();
}
await browser.close();
console.log(failures ? `\nFAILED: ${failures}` : "\nALL SMOKE CHECKS PASSED");
process.exit(failures ? 1 : 0);
