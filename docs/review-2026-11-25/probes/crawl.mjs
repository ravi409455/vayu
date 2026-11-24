// Read-only UX / a11y crawl of the local Vayu web app. Navigates, screenshots, tabs; never submits.
// Run from /Users/ravi/DevSpace/inspex/web: node <this file> [phase]
import { chromium } from "/Users/ravi/DevSpace/inspex/web/node_modules/playwright/index.mjs";
import fs from "node:fs";
import path from "node:path";

const OUT = path.join(path.dirname(new URL(import.meta.url).pathname), "webux");
const SHOTS = path.join(OUT, "shots");
fs.mkdirSync(SHOTS, { recursive: true });
const BASE = "http://localhost:5173";
const PW = "Vayu-local-1";
const AXE = "/Users/ravi/DevSpace/scissorpe/frontend/node_modules/axe-core/axe.min.js";
const TOKEN = "R5UE8w-q2tpG5p6LQtOeTPxkM6xYG1z8";
const phase = process.argv[2] ?? "all";
const results = { pages: [], states: [], keyboard: [], dialogs: [] };
const slug = (s) => s.replace(/[^a-z0-9]+/gi, "_").replace(/^_|_$/g, "") || "root";

const browser = await chromium.launch();

async function login(role) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const p = await ctx.newPage();
  await p.goto(`${BASE}/login`);
  await p.getByLabel("Username").fill(role);
  await p.locator("#pw").fill(PW);
  await p.getByRole("button", { name: "Sign in" }).click();
  await p.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 15000 });
  const state = await ctx.storageState();
  const get = (u) => p.evaluate(async (u) => (await fetch(`/api/v1/${u}`, { headers: { Accept: "application/json" } })).json(), u);
  return { state, get, close: () => ctx.close() };
}

async function newPage(state, { width, dark, me }) {
  const ctx = await browser.newContext({ storageState: state, viewport: { width, height: width < 500 ? 812 : 900 },
    colorScheme: dark ? "dark" : "light", isMobile: width < 500, hasTouch: width < 500 });
  const page = await ctx.newPage();
  const errors = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text().slice(0, 200)); });
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message.slice(0, 200)));
  if (me !== false) await page.route("**/api/v1/auth/me", async (r) => {
    const resp = await r.fetch(); let j = null; try { j = await resp.json(); } catch { /* */ }
    if (j && typeof j === "object" && j.username) j.theme = dark ? "dark" : "light";
    await r.fulfill({ response: resp, json: j });
  });
  return { ctx, page, errors };
}

async function settle(page, ms = 1200) {
  await page.waitForLoadState("networkidle", { timeout: 6000 }).catch(() => {});
  await page.waitForTimeout(ms);
}

async function axe(page) {
  await page.addScriptTag({ path: AXE });
  return page.evaluate(async () => {
    const r = await window.axe.run(document, { resultTypes: ["violations"] });
    return r.violations.map((v) => ({ id: v.id, impact: v.impact, help: v.help, n: v.nodes.length,
      nodes: v.nodes.slice(0, 6).map((n) => ({ t: n.target.join(" "), html: n.html.slice(0, 140), why: (n.failureSummary || "").slice(0, 220) })) }));
  });
}

async function phoneChecks(page) {
  return page.evaluate(() => {
    const W = document.documentElement.clientWidth;
    const scrollW = document.documentElement.scrollWidth;
    const clipped = (el) => { for (let a = el.parentElement; a; a = a.parentElement) { const o = getComputedStyle(a).overflowX; if (o !== "visible") return a !== document.body && a !== document.documentElement; } return false; };
    const desc = (el) => `${el.tagName.toLowerCase()}${el.id ? "#" + el.id : ""}${el.className && typeof el.className === "string" ? "." + el.className.trim().split(/\s+/).slice(0, 2).join(".") : ""} "${(el.getAttribute("aria-label") || el.textContent || "").trim().slice(0, 40)}"`;
    const over = [];
    for (const el of document.querySelectorAll("body *")) {
      const r = el.getBoundingClientRect();
      if (r.width && r.right > W + 1 && !clipped(el)) over.push(desc(el) + ` right=${Math.round(r.right)}`);
    }
    const small = [];
    for (const el of document.querySelectorAll("a[href], button, input:not([type=hidden]), select, textarea, [role=button], [role=tab], [role=option], summary")) {
      const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
      if (!r.width || !r.height || cs.visibility === "hidden") continue;
      if (r.width < 24 || r.height < 24) small.push(`${desc(el)} ${Math.round(r.width)}x${Math.round(r.height)}`);
    }
    const under44 = [...document.querySelectorAll("a[href], button, input, select, [role=tab]")].filter((el) => { const r = el.getBoundingClientRect(); return r.width && r.height && r.height < 44; }).length;
    return { W, scrollW, hscroll: scrollW > W + 1, over: over.slice(0, 12), small: small.slice(0, 25), smallCount: small.length, under44 };
  });
}

async function structure(page) {
  return page.evaluate(() => ({
    title: document.title,
    h: [...document.querySelectorAll("h1,h2,h3,h4")].filter((e) => e.offsetParent).map((e) => e.tagName + ":" + e.textContent.trim().slice(0, 40)).slice(0, 15),
    main: document.querySelectorAll("main,[role=main]").length, nav: document.querySelectorAll("nav").length,
    unlabelled: [...document.querySelectorAll("input:not([type=hidden]),select,textarea")].filter((e) => e.offsetParent && !(e.labels?.length) && !e.getAttribute("aria-label") && !e.getAttribute("aria-labelledby")).map((e) => `${e.tagName}[${e.type || ""}] ph="${e.placeholder || ""}"`).slice(0, 10),
  }));
}

async function crawl(role, state, routes) {
  for (const route of routes) {
    for (const width of [1280, 375]) for (const dark of [false, true]) {
      const { ctx, page, errors } = await newPage(state, { width, dark });
      const name = `${role}_${slug(route)}_${width}_${dark ? "dark" : "light"}`;
      const rec = { role, route, width, dark, shot: `shots/${name}.png` };
      try {
        await page.goto(BASE + route); await settle(page);
        rec.url = new URL(page.url()).pathname;
        rec.theme = await page.evaluate(() => document.documentElement.dataset.theme);
        await page.screenshot({ path: path.join(OUT, rec.shot), fullPage: true });
        if (width === 1280 && !dark) rec.structure = await structure(page);
        if (width === 375) rec.phone = await phoneChecks(page);
        if (width === 1280 || !dark) rec.axe = await axe(page);
      } catch (e) { rec.fail = String(e).slice(0, 300); }
      rec.errors = errors;
      results.pages.push(rec);
      console.log(name, rec.fail ?? "", rec.phone?.hscroll ? "HSCROLL" : "", (rec.axe ?? []).map((v) => v.id).join(","));
      await ctx.close();
    }
  }
}

// error / empty / loading by intercepting the API (auth/me, settings and forms metadata pass through)
async function states(role, state, routes) {
  const pass = (u) => /\/api\/v1\/(auth\/me|settings|me\/)/.test(u);
  for (const route of routes) for (const kind of ["error", "empty", "loading"]) {
    const { ctx, page, errors } = await newPage(state, { width: 1280, dark: false });
    const name = `state_${role}_${slug(route)}_${kind}`;
    await page.route("**/api/v1/**", async (r) => {
      const u = r.request().url();
      if (pass(u) || r.request().method() !== "GET") return r.fallback();
      if (kind === "error") return r.fulfill({ status: 500, json: { detail: "Server error (forced by review)" } });
      if (kind === "loading") { await new Promise((res) => setTimeout(res, 9000)); return r.fallback().catch(() => {}); }
      const resp = await r.fetch(); let j; try { j = await resp.json(); } catch { return r.fulfill({ response: resp }); }
      if (Array.isArray(j)) j = []; else if (j && Array.isArray(j.results)) j = { ...j, count: 0, results: [], next: null, previous: null };
      return r.fulfill({ response: resp, json: j });
    });
    try {
      await page.goto(BASE + route);
      await page.waitForTimeout(kind === "loading" ? 1200 : 3500);
      await page.screenshot({ path: path.join(SHOTS, name + ".png"), fullPage: true });
      const text = await page.evaluate(() => document.querySelector("main")?.innerText.slice(0, 400) ?? document.body.innerText.slice(0, 400));
      results.states.push({ role, route, kind, shot: `shots/${name}.png`, text, errors });
      console.log(name, JSON.stringify(text.slice(0, 120)));
    } catch (e) { results.states.push({ role, route, kind, fail: String(e).slice(0, 200) }); }
    await page.unrouteAll({ behavior: "ignoreErrors" }).catch(() => {});
    await ctx.close();
  }
}

async function focusInfo(page) {
  return page.evaluate(() => {
    const el = document.activeElement;
    if (!el || el === document.body) return { tag: "body" };
    const cs = getComputedStyle(el);
    const outline = cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) > 0;
    const ring = cs.boxShadow !== "none";
    const r = el.getBoundingClientRect();
    return { tag: el.tagName.toLowerCase(), name: (el.getAttribute("aria-label") || el.textContent || el.getAttribute("placeholder") || "").trim().slice(0, 40),
      cls: typeof el.className === "string" ? el.className.slice(0, 40) : "", visible: outline || ring, outline: `${cs.outlineStyle} ${cs.outlineWidth}`, shadow: cs.boxShadow.slice(0, 40),
      onScreen: r.width > 0 && r.bottom > 0 && r.top < innerHeight, inDialog: !!el.closest("[role=dialog]") };
  });
}

async function keyboard(role, state, routes) {
  for (const route of routes) {
    const { ctx, page } = await newPage(state, { width: 1280, dark: false });
    await page.goto(BASE + route); await settle(page);
    const stops = [];
    for (let i = 0; i < 45; i++) { await page.keyboard.press("Tab"); stops.push(await focusInfo(page)); }
    await page.screenshot({ path: path.join(SHOTS, `kbd_${role}_${slug(route)}.png`) });
    const noRing = stops.filter((s) => s.tag !== "body" && !s.visible);
    results.keyboard.push({ role, route, first: stops.slice(0, 4).map((s) => `${s.tag}:${s.name}`), noRing: [...new Set(noRing.map((s) => `${s.tag}.${s.cls}:${s.name} (${s.outline})`))].slice(0, 15), offscreen: stops.filter((s) => s.tag !== "body" && !s.onScreen).length, shot: `shots/kbd_${role}_${slug(route)}.png` });
    console.log("kbd", role, route, "noRing", noRing.length);
    await ctx.close();
  }
}

// open a dialog with the keyboard, check focus moves in, stays in, Escape closes, focus returns
async function dialog(role, state, route, open, label) {
  const { ctx, page } = await newPage(state, { width: 1280, dark: false });
  const rec = { role, route, label };
  try {
    await page.goto(BASE + route); await settle(page);
    const trig = await open(page);
    await trig.focus(); await page.keyboard.press("Enter");
    await page.waitForSelector("[role=dialog]", { timeout: 5000 });
    await page.waitForTimeout(300);
    rec.afterOpen = await focusInfo(page);
    const seen = [];
    for (let i = 0; i < 20; i++) { await page.keyboard.press("Tab"); seen.push(await focusInfo(page)); }
    rec.leftDialog = seen.filter((s) => !s.inDialog).map((s) => `${s.tag}:${s.name}`).slice(0, 6);
    await page.screenshot({ path: path.join(SHOTS, `dlg_${role}_${slug(label)}.png`) });
    await page.keyboard.press("Escape"); await page.waitForTimeout(300);
    rec.openAfterEscape = await page.locator("[role=dialog][aria-modal=true]").count() > 0;
    if (rec.openAfterEscape) { await page.keyboard.press("Escape"); }
    // close with its own Cancel/Close/Back button by keyboard to test focus return
    if (await page.locator("[role=dialog][aria-modal=true]").count()) {
      await page.locator("[role=dialog] .actions button").first().click();
    }
    await page.waitForTimeout(300);
    rec.focusAfterClose = await focusInfo(page);
  } catch (e) { rec.fail = String(e).slice(0, 200); }
  results.dialogs.push(rec);
  console.log("dlg", JSON.stringify(rec).slice(0, 400));
  await ctx.close();
}

const admin = await login("admin");
const ops = await login("ops");
const expert = await login("expert");

const bk = await ops.get("bookings?page_size=100");
const list = bk.results ?? [];
const pick = (s) => list.find((b) => (b.stage ?? b.status) === s)?.id;
const bookingIds = { completed: pick("completed"), in_progress: pick("in_progress"), assigned: pick("assigned"), draft: pick("draft") };
const forms = await admin.get("forms"); const formId = (forms.results ?? forms)[0]?.id;
const lib = await admin.get("library"); const libId = (lib.results ?? lib)[0]?.id;
const integ = await admin.get("integrations"); const integId = (integ.results ?? integ)[0]?.id;
const mine = await expert.get("bookings?page_size=50"); const myList = mine.results ?? mine;
const leadIds = { assigned: myList.find((b) => b.stage === "assigned")?.id, in_progress: myList.find((b) => b.stage === "in_progress")?.id, completed: myList.find((b) => b.stage === "completed")?.id };
console.log({ bookingIds, formId, libId, integId, leadIds, expertCount: myList.length });

const opsRoutes = ["/today", "/bookings", "/problems", "/dashboards", "/settings", "/profile",
  `/booking/${bookingIds.completed}`, `/booking/${bookingIds.in_progress}`, `/booking/${bookingIds.assigned}`, "/booking/new"];
const adminRoutes = ["/today", "/bookings", "/problems", "/dashboards", "/forms", "/library", "/lists", "/pdf", "/users", "/roles",
  "/integrations", "/api-keys", "/promote", "/settings", "/audit", "/profile", `/booking/${bookingIds.completed}`,
  formId && `/forms/${formId}`, libId && `/library/${libId}`, integId && `/integrations/${integId}`, "/integrations/new"].filter(Boolean);
const expertRoutes = ["/jobs", "/profile", leadIds.assigned && `/jobs/${leadIds.assigned}`, leadIds.in_progress && `/jobs/${leadIds.in_progress}`, leadIds.completed && `/jobs/${leadIds.completed}`, "/today"].filter(Boolean);
const publicRoutes = ["/login", `/verify/${TOKEN}`, `/verify/${TOKEN}/photos`, `/verify/${TOKEN}/videos`, "/verify/not-a-real-token", "/zip/not-a-real-token"];

if (phase === "all" || phase === "crawl") {
  await crawl("ops", ops.state, opsRoutes);
  await crawl("expert", expert.state, expertRoutes);
  await crawl("admin", admin.state, adminRoutes);
  const anon = { cookies: [], origins: [] };
  await crawl("public", anon, publicRoutes);
}
if (phase === "phone") {
  const all = [["ops", ops.state, opsRoutes], ["expert", expert.state, expertRoutes], ["admin", admin.state, adminRoutes], ["public", { cookies: [], origins: [] }, publicRoutes]];
  for (const [role, st, rs] of all) for (const route of rs) {
    const ctx = await browser.newContext({ storageState: st, viewport: { width: 375, height: 812 } });
    const page = await ctx.newPage();
    await page.goto(BASE + route); await settle(page);
    const ph = await phoneChecks(page);
    results.pages.push({ role, route, phone: ph });
    console.log("phone", role, route, ph.scrollW, ph.hscroll ? "HSCROLL " + ph.over.slice(0, 3).join(" | ") : "");
    await ctx.close();
  }
}
if (phase === "all" || phase === "states") {
  await states("ops", ops.state, ["/today", "/bookings", "/problems", "/dashboards", `/booking/${bookingIds.completed}`]);
  await states("expert", expert.state, ["/jobs", leadIds.assigned && `/jobs/${leadIds.assigned}`].filter(Boolean));
  await states("admin", admin.state, ["/forms", "/users", "/library", "/audit", "/api-keys", "/integrations", "/lists", "/pdf"]);
  await states("public", { cookies: [], origins: [] }, [`/verify/${TOKEN}`]);
}
if (phase === "all" || phase === "kbd") {
  await keyboard("ops", ops.state, ["/today", "/bookings", `/booking/${bookingIds.completed}`, "/booking/new", "/dashboards"]);
  await keyboard("expert", expert.state, ["/jobs", leadIds.assigned && `/jobs/${leadIds.assigned}`].filter(Boolean));
  await keyboard("admin", admin.state, ["/users", "/forms", formId && `/forms/${formId}`, "/pdf", "/roles"].filter(Boolean));
  await keyboard("public", { cookies: [], origins: [] }, ["/login", `/verify/${TOKEN}`]);
  await dialog("admin", admin.state, "/users", (p) => p.getByRole("button", { name: "New user" }), "New user");
  await dialog("admin", admin.state, "/forms", (p) => p.getByRole("button", { name: "New custom form" }), "New custom form");
  await dialog("ops", ops.state, "/bookings", (p) => p.getByRole("button", { name: "Assign expert" }).first(), "Assign expert");
}

fs.writeFileSync(path.join(OUT, `results-${phase}.json`), JSON.stringify({ bookingIds, leadIds, ...results }, null, 1));
await Promise.all([admin.close(), ops.close(), expert.close()]);
await browser.close();
