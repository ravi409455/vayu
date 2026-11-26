import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { apiAs, signIn, submittedJob, waitForReport, type Pdi } from "./api";

// Accessibility and layout: no axe violations, and staff pages fit a 768 px tablet with no sideways
// scroll (customer pages a 375 px phone). Batch 4: F-175, F-178, F-185, F-186, F-187, R-14, H-19.

async function axe(page: Page) {
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"]).analyze();
  return r.violations.map(
    (v) =>
      `${v.id}: ${v.nodes
        .slice(0, 3)
        .map((n) => n.target.join(" "))
        .join(" | ")}`,
  );
}
const overflow = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);

let bookingId = "";
let verifyPath = "";
test.beforeAll(async () => {
  bookingId = await submittedJob({ bookingId: `AX-${Date.now() % 1_000_000}`, photo: true, door: "dent" });
  verifyPath = new URL((await waitForReport(bookingId)).verify_url).pathname;
});

const STAFF: [string, string[]][] = [
  ["ops", ["/today", "/bookings", "/problems", "/dashboards", "/profile", "/settings"]],
  ["admin", ["/users", "/roles", "/forms", "/lists", "/library", "/pdf", "/integrations", "/api-keys", "/audit"]],
  ["expert", ["/jobs", "/app"]],
];

for (const [who, paths] of STAFF) {
  test(`${who} pages: no axe violations, fit 768 px`, async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1000 });
    await signIn(page, who);
    const found: string[] = [];
    const seed = JSON.parse(readFileSync("e2e/.seed.json", "utf8")) as Pdi;
    const more =
      {
        ops: [`/booking/${bookingId}`, "/booking/new"],
        admin: [`/forms/${seed.formId}`, "/integrations/new"],
        expert: [`/jobs/${bookingId}`],
      }[who] ?? [];
    for (const p of [...paths, ...more]) {
      await page.goto(p);
      await page.locator("main h1").first().waitFor();
      await page.waitForLoadState("networkidle");
      const wide = await overflow(page);
      if (wide > 0) found.push(`${p}: ${wide}px too wide`);
      for (const v of await axe(page)) found.push(`${p}: ${v}`);
    }
    expect(found).toEqual([]);
  });
}

test("dark mode: no contrast problems (F-178)", async ({ page }) => {
  // the person's saved look is Dark (set on the server: Firefox leaves a rewritten request open,
  // so a page never went quiet)
  const ops = await apiAs("ops");
  await ops.patch("auth/me/profile", { data: { theme: "dark" } });
  try {
    await signIn(page, "ops");
    const found: string[] = [];
    for (const p of ["/today", "/bookings", "/dashboards", `/booking/${bookingId}`]) {
      await page.goto(p);
      await page.locator("main h1").first().waitFor();
      await page.waitForLoadState("networkidle");
      expect(await page.evaluate(() => document.documentElement.dataset.theme)).toBe("dark");
      for (const v of await axe(page)) found.push(`${p}: ${v}`);
    }
    expect(found).toEqual([]);
  } finally {
    await ops.patch("auth/me/profile", { data: { theme: "light" } });
  }
});

test("customer pages: no axe violations, fit 375 px", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto(verifyPath);
  await expect(page.getByText("This is a genuine Car C.I.D. report.")).toBeVisible();
  expect(await overflow(page)).toBeLessThanOrEqual(0);
  expect(await axe(page)).toEqual([]);
  await expect(page).toHaveTitle("Car C.I.D.");
});

test("a dialog takes focus, keeps it, closes on Escape and gives it back (H-19)", async ({ page }) => {
  await signIn(page, "admin");
  await page.goto("/users");
  const opener = page.getByRole("button", { name: "New user" });
  // opened from the keyboard: Safari never focuses a clicked button, so a click leaves nothing to give back
  await opener.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "New user" });
  await expect(dialog).toBeVisible();
  for (let i = 0; i < 25; i++) await page.keyboard.press("Tab");
  expect(await page.evaluate(() => !!document.activeElement?.closest("dialog"))).toBe(true);
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(opener).toBeFocused();
});

test("skip link and page titles (F-185, R-24)", async ({ page, browserName }) => {
  await signIn(page, "ops");
  await page.goto("/bookings");
  await expect(page).toHaveTitle("Bookings · Vayu");
  await page.keyboard.press(browserName === "webkit" ? "Alt+Tab" : "Tab"); // Safari: Option+Tab reaches links
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("main#main")).toBeFocused();
});
