// Read-only probes of the web app. Every mutating request is intercepted and answered locally,
// so nothing reaches the server.
import { createRequire } from "module";
const require = createRequire("/Users/ravi/DevSpace/inspex/web/package.json");
const { chromium } = require("playwright");

const BASE = "http://localhost:5173";
const out = (...a) => console.log(...a);

async function login(page, user) {
  await page.goto(`${BASE}/login`);
  await page.getByLabel("Username").fill(user);
  await page.locator("#pw").fill("Vayu-local-1");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
}

const browser = await chromium.launch();

// 1. Expert: a submitted lead with a file waiting in IndexedDB. Does the page resume it?
{
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  const calls = [];
  await page.route("**/api/v1/media/**", (r) => { calls.push(r.request().method() + " " + r.request().url()); r.fulfill({ status: 503, body: "{}", contentType: "application/json" }); });
  await login(page, "expert");
  const sub = "061761cc-3a36-4b24-98d1-a278da92ac06";   // FIN-12, submitted
  await page.goto(`${BASE}/jobs`);
  await page.evaluate(async (bookingId) => {
    const db = await new Promise((res, rej) => { const r = indexedDB.open("vayu-uploads", 1); r.onupgradeneeded = () => r.result.createObjectStore("jobs", { keyPath: "clientUuid" }); r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error); });
    await new Promise((res) => { const t = db.transaction("jobs", "readwrite"); t.objectStore("jobs").put({ clientUuid: "00000000-0000-4000-8000-00000000review", bookingId, fieldKey: "x", kind: "photo", contentType: "image/jpeg", name: "p.jpg", sha256: "0".repeat(64), assetId: "00000000-0000-4000-8000-000000000001", source: "camera", blob: new Blob(["x"], { type: "image/jpeg" }) }); t.oncomplete = res; });
  }, sub);
  await page.goto(`${BASE}/jobs/${sub}`);
  await page.waitForTimeout(4000);
  const text = await page.locator("main").innerText();
  const left = await page.evaluate(async () => { const db = await new Promise((res) => { const r = indexedDB.open("vayu-uploads", 1); r.onsuccess = () => res(r.result); }); return await new Promise((res) => { const q = db.transaction("jobs").objectStore("jobs").getAll(); q.onsuccess = () => res(q.result.length); }); });
  out("[1] submitted lead page shows:", JSON.stringify(text.slice(0, 200)));
  out("[1] media calls after reload:", calls.length, "| jobs still in IndexedDB:", left);
  // sign out: what stays in the browser?
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await page.waitForTimeout(800);
  const ls = await page.evaluate(() => Object.keys(localStorage));
  out("[1b] localStorage keys after sign-out:", JSON.stringify(ls));
  await page.evaluate(async () => { const db = await new Promise((res) => { const r = indexedDB.open("vayu-uploads", 1); r.onsuccess = () => res(r.result); }); await new Promise((res) => { const t = db.transaction("jobs", "readwrite"); t.objectStore("jobs").clear(); t.oncomplete = res; }); });
  await ctx.close();
}

// 2. Ops: double-click the Reschedule button in the dialog. How many requests leave?
{
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  let n = 0;
  await page.route("**/api/v1/bookings/*/reschedule", async (r) => { n++; await new Promise((x) => setTimeout(x, 600)); r.fulfill({ status: 200, contentType: "application/json", body: "{}" }); });
  await login(page, "ops");
  const id = "9132410c-0d5a-4ada-994a-5b5492fd34f4";      // DEMO-2, assigned
  await page.goto(`${BASE}/booking/${id}`);
  await page.getByRole("button", { name: "Reschedule" }).first().click();
  const dlg = page.getByRole("dialog");
  await dlg.getByLabel("Reason").selectOption({ index: 1 });
  await dlg.getByRole("button", { name: "Reschedule" }).dblclick();
  await page.waitForTimeout(1500);
  out("[2] reschedule requests sent by one double-click:", n);

  // 3. Bookings filter: requests per typed search
  const seen = [];
  page.on("request", (r) => { if (r.url().includes("/api/v1/bookings?")) seen.push(r.url()); });
  await page.goto(`${BASE}/bookings?view=all`);
  await page.waitForTimeout(1500);
  seen.length = 0;
  await page.getByLabel("Filter bookings").pressSequentially("Sharma", { delay: 120 });
  await page.waitForTimeout(2000);
  out("[3] /bookings requests while typing 6 letters:", seen.length, "| example:", seen[seen.length - 1]);
  out("[3b] page URL after global search Enter:");
  await page.getByLabel("Search bookings").fill("98765");
  await page.getByLabel("Search bookings").press("Enter");
  await page.waitForTimeout(800);
  out("     ", page.url());

  // 4. A crafted /zip/ link: which API URL does the browser call?
  const zipCalls = [];
  page.on("request", (r) => { if (r.url().includes("/api/")) zipCalls.push(r.url()); });
  await page.goto(`${BASE}/zip/..%2Fauth%2Fme`);
  await page.waitForTimeout(1500);
  out("[4] API calls from /zip/..%2Fauth%2Fme:", JSON.stringify(zipCalls.filter((u) => !u.includes("auth/me?") || true).slice(-3)));
  await ctx.close();
}
await browser.close();
