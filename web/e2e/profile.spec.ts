import { expect, request, test, type Page } from "@playwright/test";
import { apiAs, JPEG, json, PASSWORD, signIn } from "./api";

const mePicture = async (username: string) => {
  const c = await apiAs(username);
  const me = await json(await c.get("auth/me"));
  return { c, me };
};

async function assignedTo(expert: string, bookingId: string) {
  const ops = await apiAs("ops");
  const { me } = await mePicture(expert);
  const b = await json(await ops.post("bookings", { data: { answers: {
    booking_id: bookingId, customer_name: "Profile Test", customer_phone: "9876500044", address: "5 Face Rd", city: "delhi",
    inspection_date: "2026-12-10", inspection_time: "09:00", inspection_type: "pdi", car_make_model: "maruti_victoris" } } }));
  await json(await ops.post(`bookings/${b.id}/assign`, { data: { expert: me.id } }));
  return b.id as string;
}

/** Brightness contrast ratio of the text colour against the colour actually behind it. */
async function contrast(page: Page, selector: string): Promise<number> {
  return page.locator(selector).first().evaluate((el) => {
    const parse = (c: string) => (c.match(/[\d.]+/g) ?? []).map(Number);
    const lum = ([r, g, b]: number[]) => {
      const f = (v: number) => { const x = v / 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; };
      return 0.2126 * f(r!) + 0.7152 * f(g!) + 0.0722 * f(b!);
    };
    let bg: number[] = [255, 255, 255];
    for (let n: Element | null = el; n; n = n.parentElement) {
      const c = parse(getComputedStyle(n).backgroundColor);
      if (c.length >= 3 && (c[3] === undefined || c[3] > 0)) { bg = c; break; }
    }
    const fg = parse(getComputedStyle(el).color);
    const [a, b] = [lum(fg), lum(bg)];
    return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
  });
}

test("a picture: uploaded, square, in the sidebar, seen by Ops next to the expert, hidden from other experts", async ({ page, browser }) => {
  const id = await assignedTo("expert", "PIC-1");
  await signIn(page, "expert");
  await page.getByRole("link", { name: /Your profile/ }).click();
  await expect(page.getByRole("heading", { name: /Your profile/ })).toBeVisible();
  await page.getByLabel("Upload a picture", { exact: false }).first().setInputFiles({ name: "me.jpg", mimeType: "image/jpeg", buffer: JPEG });
  await expect(page.getByText("Picture saved.")).toBeVisible();
  const big = page.getByRole("region", { name: "Picture" }).locator("img.avatar");
  await expect(big).toBeVisible();
  expect(await big.evaluate((i: HTMLImageElement) => [i.naturalWidth, i.naturalHeight])).toEqual([256, 256]);   // cropped square
  await expect(page.locator(".who-name img.avatar")).toBeVisible();                                          // shown in the sidebar too

  const ops = await browser.newContext({ baseURL: "http://localhost:5173" });
  const opsPage = await ops.newPage();
  await signIn(opsPage, "ops");
  await opsPage.goto("/board");
  await expect(opsPage.locator("tr", { hasText: "PIC-1" }).locator("img.avatar")).toBeVisible();
  await opsPage.goto("/bookings");
  await opsPage.getByLabel("Search").fill("PIC-1");
  await expect(opsPage.locator("tr", { hasText: "PIC-1" }).locator("img.avatar")).toBeVisible();
  await ops.close();

  const { me } = await mePicture("expert");
  const other = await apiAs("expert2");
  expect((await other.get(`users/${me.id}/picture`)).status()).toBe(404);          // not theirs to see
  expect((await (await apiAs("ops")).get(`users/${me.id}/picture`)).status()).toBe(200);
  expect(id).toBeTruthy();
});

test("theme: dark at once, kept after a reload without a flash, Light when signed out, back again from the server", async ({ page, browser }) => {
  await page.addInitScript(() => { document.addEventListener("DOMContentLoaded", () => { (window as unknown as { __first: string }).__first = document.documentElement.dataset.theme ?? ""; }); });
  await signIn(page, "expert2");
  await page.goto("/profile");
  await page.getByRole("radio", { name: /Dark/ }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  expect(await contrast(page, ".main h1")).toBeGreaterThan(4.5);
  await expect(page.getByRole("radio", { name: /Dark/ })).toBeChecked();
  await page.reload();
  expect(await page.evaluate(() => (window as unknown as { __first: string }).__first)).toBe("dark");   // painted dark from the first moment
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { name: "Vayu" })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  const fresh = await browser.newContext({ baseURL: "http://localhost:5173" });          // nothing remembered in this browser
  const p2 = await fresh.newPage();
  await signIn(p2, "expert2");
  await expect(p2.locator("html")).toHaveAttribute("data-theme", "dark");               // it came from the server
  await fresh.close();
  await (await apiAs("expert2")).patch("auth/me/profile", { data: { theme: "light" } });
});

test("theme: 'match my device' follows the device's light or dark setting", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await signIn(page, "expert2");
  await page.goto("/profile");
  await page.getByRole("radio", { name: /Match my device/ }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await (await apiAs("expert2")).patch("auth/me/profile", { data: { theme: "light" } });
});

test("dark theme: the main screens are readable (text contrast of at least 4.5)", async ({ page }) => {
  await signIn(page, "admin");
  await (await apiAs("admin")).patch("auth/me/profile", { data: { theme: "dark" } });
  await page.goto("/forms");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  for (const sel of [".main h1", ".main h2", "table td", "table th", ".muted", ".main a"]) expect.soft(await contrast(page, sel), sel).toBeGreaterThan(4.5);
  await page.getByRole("button", { name: "New custom form" }).click();
  for (const sel of [".modal h2, .modal h1, .modal h3", ".modal input", ".modal button.primary"]) expect.soft(await contrast(page, sel), sel).toBeGreaterThan(4.5);
  await page.keyboard.press("Escape");
  await page.goto("/profile");
  for (const sel of [".card h2", ".details dd", ".details dt"]) expect.soft(await contrast(page, sel), sel).toBeGreaterThan(4.5);
  await (await apiAs("admin")).patch("auth/me/profile", { data: { theme: "light" } });
});

test("password: changed on the profile, the old one stops working, the new one works", async ({ page, browser }) => {
  const admin = await apiAs("admin");
  const users = await json(await admin.get("users"));
  const me = (users.results ?? users).find((u: { username: string }) => u.username === "expert2");
  await signIn(page, "expert2");
  await page.goto("/profile");
  const form = page.getByRole("region", { name: "Password" });
  await form.getByLabel("Current password").fill(PASSWORD);
  await form.getByLabel("New password", { exact: true }).fill("Brand-new-pass-7");
  await form.getByLabel("New password again").fill("Brand-new-pass-7");
  await form.getByRole("button", { name: "Change password" }).click();
  await expect(page.getByText(/Password changed/)).toBeVisible();
  const ctx = await browser.newContext({ baseURL: "http://localhost:5173" });
  const p = await ctx.newPage();
  await p.goto("/login");
  await p.getByLabel("Username").fill("expert2");
  await p.getByLabel("Password").fill(PASSWORD);
  await p.getByRole("button", { name: "Sign in" }).click();
  await expect(p.getByRole("alert")).toBeVisible();                                    // the old password is refused
  await p.getByLabel("Password").fill("Brand-new-pass-7");
  await p.getByRole("button", { name: "Sign in" }).click();
  await p.waitForURL((u) => !u.pathname.startsWith("/login"));
  await ctx.close();
  // put it back for later tests: reset, then choose the old password again
  await json(await admin.post(`users/${me.id}/reset-password`, { data: { password: "Temporary-pass-1" } }));
  const ctx2 = await request.newContext({ baseURL: "http://localhost:8000/api/v1/" });
  await json(await ctx2.post("auth/login", { data: { username: "expert2", password: "Temporary-pass-1", client: "web" } }));
  const csrf = (await ctx2.storageState()).cookies.find((c) => c.name === "csrftoken")?.value ?? "";
  await json(await ctx2.post("auth/change-password", { data: { old_password: "Temporary-pass-1", new_password: PASSWORD }, headers: { "X-CSRFToken": csrf } }));
  await ctx2.dispose();
  await apiAs("expert2");
});

test("details are not editable by the person, and the API refuses it", async ({ page }) => {
  await signIn(page, "ops");
  await page.goto("/profile");
  const details = page.getByRole("region", { name: "Details" });
  await expect(details.getByText("Priya Ops")).toBeVisible();
  await expect(details.getByRole("textbox")).toHaveCount(0);
  await expect(details.getByText(/ask an Admin/)).toBeVisible();
  const ops = await apiAs("ops");
  const r = await ops.patch("auth/me/profile", { data: { name: "Hacked", phone: "9876543210" } });
  expect(r.status()).toBe(400);
  expect((await r.json()).code).toBe("FIELD_NOT_EDITABLE");
  const me = await json(await ops.get("auth/me"));
  expect(me.name).toBe("Priya Ops");
});

test("an Admin edits a phone and removes a picture; the expert falls back to initials; it is all in the audit log", async ({ page, browser }) => {
  const { me } = await mePicture("expert");
  const exp = await apiAs("expert");
  await exp.put("auth/me/picture", { multipart: { file: { name: "a.jpg", mimeType: "image/jpeg", buffer: JPEG } } });
  await signIn(page, "admin");
  await page.goto("/users");
  const row = page.locator("tr", { hasText: "Ravi Expert" });
  await expect(row.locator("img.avatar")).toBeVisible();
  await row.getByRole("button", { name: "Edit" }).click();
  await page.getByLabel("Phone").fill("98765 43210");
  await page.getByRole("button", { name: "Remove picture" }).click();
  await expect(page.getByText(/initials show instead/)).toBeVisible();
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Saved.")).toBeVisible();

  const ctx = await browser.newContext({ baseURL: "http://localhost:5173" });
  const p = await ctx.newPage();
  await signIn(p, "expert");
  await p.goto("/profile");
  await expect(p.getByRole("region", { name: "Details" }).getByText("+919876543210")).toBeVisible();
  await expect(p.getByRole("region", { name: "Picture" }).locator("img.avatar")).toHaveCount(0);        // initials now
  await expect(p.getByRole("region", { name: "Picture" }).getByRole("img", { name: /Ravi Expert/ })).toBeVisible();
  await ctx.close();

  const log = await json(await (await apiAs("admin")).get("audit-logs?page_size=100"));
  const actions = (log.results ?? log).map((r: { action: string }) => r.action);
  expect(actions).toEqual(expect.arrayContaining(["user.picture_removed_by_admin", "user.picture_set", "user.update"]));
  expect(me.id).toBeTruthy();
});

test("users.manage is Admin only: the Roles screen says so and the API refuses to grant it", async ({ page }) => {
  await signIn(page, "admin");
  await page.goto("/roles");
  await page.getByRole("tab", { name: /Ops/ }).click().catch(() => {});
  const row = page.locator("tr", { hasText: "Create, edit, deactivate users" });
  await expect(row.getByText("Admin only")).toBeVisible();
  const admin = await apiAs("admin");
  const r = await admin.put("roles/ops/permissions", { data: { permissions: { "users.manage": "all" } } });
  expect(r.status()).toBe(400);
  expect((await r.json()).code).toBe("NOT_GRANTABLE");
});
