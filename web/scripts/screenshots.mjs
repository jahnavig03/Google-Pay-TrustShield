/**
 * Click through every demo flow, check each page for sideways overflow at phone / tablet /
 * laptop / desktop widths, and save deck screenshots to docs/screenshots/.
 *
 *   BASE_URL=http://localhost:5173 npm run screenshots
 *
 * Needs the gateway + web app running, and Google Chrome installed (uses playwright-core with
 * the system Chrome, so nothing is downloaded). Synthetic data only.
 */
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { chromium } from "playwright-core";

const BASE = process.env.BASE_URL ?? "http://localhost:5173";
const CODE = process.env.ANALYST_CODE ?? "trustshield-demo";
const OUT = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "docs", "screenshots");

const VIEWPORTS = {
  phone: { width: 390, height: 844 },
  tablet: { width: 768, height: 1024 },
  laptop: { width: 1366, height: 768 },
  desktop: { width: 1920, height: 1080 },
};

async function newPage(browser, viewport, theme = "light", scale = 2) {
  const context = await browser.newContext({ viewport, deviceScaleFactor: scale });
  await context.addInitScript((t) => localStorage.setItem("trustshield.theme", t), theme);
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  // Don't wait for every web font to finish loading; settle() waits (bounded) instead.
  const goto = page.goto.bind(page);
  page.goto = (url, opts) => goto(url, { waitUntil: "domcontentloaded", ...opts });
  return page;
}

async function overflow(page) {
  // True sideways scroll: content width beyond the visible area (scrollbar excluded).
  return page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
}

const flows = {
  landing: async (p) => p.goto(`${BASE}/`),
  customer: async (p) => p.goto(`${BASE}/customer`),
  pay_demo1: async (p) => {
    await p.goto(`${BASE}/customer/pay`);
    await p.getByRole("button", { name: "Pay", exact: true }).click();
    await p.getByRole("article", { name: "Payment check result" }).waitFor();
  },
  pay_qr_swapped: async (p) => {
    await p.goto(`${BASE}/customer/pay`);
    await p.getByRole("button", { name: "Scan QR" }).click();
    await p.getByRole("tab", { name: /Sample QRs/ }).click();
    await p.getByRole("button", { name: /swapped sticker/ }).click();
    await p.getByRole("status", { name: "From QR code" }).waitFor();
    await p.getByRole("button", { name: "Pay", exact: true }).click();
    await p.getByRole("article", { name: "Payment check result" }).waitFor();
  },
  pay_qr_scanner: async (p) => {
    await p.goto(`${BASE}/customer/pay`);
    await p.getByRole("button", { name: "Scan QR" }).click();
    await p.getByRole("tab", { name: /Sample QRs/ }).click();
    await p.locator(".sample img").last().waitFor();
    await p.waitForFunction(() =>
      [...document.querySelectorAll(".sample img")].every((i) => i.complete && i.naturalWidth),
    );
  },
  pay_qr_link: async (p) => {
    await p.goto(`${BASE}/customer/pay`);
    await p.getByRole("button", { name: "Scan QR" }).click();
    await p.getByRole("tab", { name: /Sample QRs/ }).click();
    await p.getByRole("button", { name: /KYC update/ }).click();
    await p.getByRole("article", { name: "QR check result" }).waitFor();
  },
  merchant_demo3: async (p) => {
    await p.goto(`${BASE}/customer/merchant`);
    await p.getByRole("button", { name: /Demo 3/ }).click();
    await p.getByRole("button", { name: "Check payment" }).click();
    await p.getByRole("article", { name: "Verification result" }).waitFor();
  },
  analyst_login: async (p) => p.goto(`${BASE}/analyst/login`),
  analyst_case: async (p) => {
    await p.goto(`${BASE}/analyst/login`);
    await p.getByLabel("Access code").fill(CODE);
    await p.getByRole("button", { name: "Sign in" }).click();
    await p.getByRole("heading", { name: "Case queue" }).waitFor();
    await p.locator(".case-row").first().click();
    await p.locator("article.case-detail").waitFor();
  },
};

async function settle(page) {
  await page.evaluate(() =>
    Promise.race([document.fonts.ready, new Promise((r) => setTimeout(r, 4000))]),
  );
  await page.waitForTimeout(400);
}

const browser = await chromium.launch({ channel: "chrome", headless: true });
await mkdir(OUT, { recursive: true });
const problems = [];

// 1) Responsive audit: every flow at every size, no sideways scrolling allowed.
//    SKIP_AUDIT=1 skips it (e.g. for clean deck shots from a fresh gateway).
for (const [size, viewport] of Object.entries(process.env.SKIP_AUDIT ? {} : VIEWPORTS)) {
  for (const [name, run] of Object.entries(flows)) {
    const page = await newPage(browser, viewport, "light", 1);
    await run(page);
    await settle(page);
    const extra = await overflow(page);
    const line = `${size.padEnd(8)} ${name.padEnd(16)} overflow ${extra}px`;
    console.log(extra > 0 ? `FAIL ${line}` : `ok   ${line}`);
    if (extra > 0) problems.push(line);
    await page.context().close();
  }
}

// 2) Deck screenshots (2x).
const shots = [
  ["01-landing", "desktop", "light", flows.landing],
  ["02-customer-choice", "desktop", "light", flows.customer],
  ["03-payment-demo1-hold", "desktop", "light", flows.pay_demo1],
  ["04-qr-scanner", "desktop", "light", flows.pay_qr_scanner],
  ["05-qr-swapped-sticker-hold", "desktop", "light", flows.pay_qr_swapped],
  ["06-qr-link-not-a-payment", "desktop", "light", flows.pay_qr_link],
  ["07-merchant-demo3-suspicious", "desktop", "light", flows.merchant_demo3],
  ["08-analyst-sign-in", "desktop", "light", flows.analyst_login],
  ["09-analyst-case", "desktop", "light", flows.analyst_case],
  ["10-analyst-case-dark", "desktop", "dark", flows.analyst_case],
  ["11-payment-demo1-dark", "desktop", "dark", flows.pay_demo1],
  ["12-phone-landing", "phone", "light", flows.landing],
  ["13-phone-qr-swapped", "phone", "light", flows.pay_qr_swapped],
  ["14-phone-analyst-case", "phone", "dark", flows.analyst_case],
];
for (const [file, size, theme, run] of shots) {
  const page = await newPage(browser, VIEWPORTS[size === "desktop" ? "laptop" : size], theme);
  await run(page);
  await settle(page);
  if (size === "phone") {
    // Fixed header / bottom bar make full-page phone captures misleading: show the screen,
    // scrolled to the result if there is one.
    const result = page.locator("article.sheet, article.verdict, article.case-detail").first();
    if (await result.count()) await result.scrollIntoViewIfNeeded();
    await page.waitForTimeout(300);
  }
  await page.screenshot({ path: join(OUT, `${file}.png`) });
  console.log(`saved ${file}.png`);
  await page.context().close();
}

await browser.close();
if (problems.length) {
  console.error(`\n${problems.length} page(s) scroll sideways:\n${problems.join("\n")}`);
  process.exit(1);
}
console.log("\nAll pages fit their screen width.");
