import { API_ROOT } from "./ports";
import { expect, test } from "@playwright/test";
import { apiAs, json, signIn } from "./api";

test.describe("admin screens", () => {
  test("users: create, reset password, deactivate", async ({ page }) => {
    await signIn(page, "admin");
    await page.goto("/users");
    await page.getByRole("button", { name: "New user" }).click();
    const d = page.getByRole("dialog");
    await d.getByLabel("Name", { exact: true }).fill("Nina New");
    await d.getByLabel("Username").fill("nina");
    await d.getByLabel("First password").fill("First-pass-1");
    await d.getByLabel("Role").selectOption("expert");
    await d.getByRole("button", { name: "Save" }).click();
    const row = page.locator("tr", { hasText: "nina" });
    await expect(row).toContainText("Must change password");
    await row.getByRole("button", { name: "Actions for nina" }).click();
    await page.getByRole("menuitem", { name: "Reset password" }).click();
    await page.getByRole("dialog").getByLabel("Temporary password").fill("Temp-pass-22");
    await page.getByRole("dialog").getByRole("button", { name: "Reset" }).click();
    await expect(page.getByRole("status")).toContainText("Password reset");
    await row.getByRole("button", { name: "Actions for nina" }).click();
    await page.getByRole("menuitem", { name: "Deactivate…" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Deactivate" }).click();
    await expect(row).toHaveCount(0); // deactivated people are hidden by default
    await page.getByLabel("Show deactivated").check();
    await expect(row).toContainText("Deactivated");
  });

  test("master lists: add an item and archive it", async ({ page }) => {
    await signIn(page, "admin");
    await page.goto("/lists");
    await page.getByRole("button", { name: "City", exact: true }).click();
    const d = page.getByRole("region", { name: "City" });
    await d.getByLabel("Label", { exact: true }).fill("Mumbai");
    await d.getByLabel("New key").fill("mumbai");
    await d.getByRole("button", { name: "Add item" }).click();
    const row = d.locator("tr", { hasText: "mumbai" });
    await expect(row).toBeVisible();
    await row.getByRole("button", { name: "Archive" }).click();
    await expect(row).toContainText("Archived");
  });

  test("roles: Ops gets a permission and it is saved", async ({ page }) => {
    await signIn(page, "admin");
    await page.goto("/roles");
    const exportOps = page.getByRole("radiogroup", { name: "Export dashboard data to CSV (Ops)" });
    await expect(page.getByRole("radiogroup", { name: "View dashboards (Ops)" })).toBeVisible();
    await exportOps.getByRole("radio", { name: "Off" }).click();
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByRole("status")).toContainText("Permissions saved");
    const roles = await json(await (await apiAs("admin")).get("roles"));
    expect(roles.find((r: { role: string }) => r.role === "ops").permissions["dashboards.export"]).toBeUndefined();
    // put it back so other tests keep their rights
    await exportOps.getByRole("radio", { name: "All" }).click();
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByRole("status")).toContainText("Permissions saved");
  });

  test("rating config: change the Critical deduction and save", async ({ page }) => {
    await signIn(page, "admin");
    await page.goto("/forms");
    await page.getByRole("link", { name: "PDI" }).click();
    await page.getByRole("button", { name: "Start a new draft" }).click();
    await page.getByRole("tab", { name: "Ratings" }).click();
    await page.getByLabel("Critical").fill("2");
    await page.getByRole("button", { name: "Save ratings" }).click();
    const admin = await apiAs("admin");
    const forms = await json(await admin.get("forms"));
    const pdi = (forms.results ?? forms).find((f: { key: string }) => f.key === "pdi");
    const v = await json(await admin.get(`form-versions/${pdi.draft_version.id}`));
    await expect
      .poll(async () => (await json(await admin.get(`form-versions/${pdi.draft_version.id}`))).rating_config?.deductions?.critical)
      .toBe(2);
    expect(v.rating_config.categories[0].key).toBe("exterior");
  });

  test("publish is blocked while the form has a problem, and the dialog says what", async ({ page }) => {
    await signIn(page, "admin");
    const admin = await apiAs("admin");
    const forms = await json(await admin.get("forms"));
    let pdi = (forms.results ?? forms).find((f: { key: string }) => f.key === "pdi");
    if (!pdi.draft_version) {
      // do not depend on an earlier test having started a draft
      await json(await admin.post(`forms/${pdi.id}/drafts`, { data: {} }));
      pdi = await json(await admin.get(`forms/${pdi.id}`));
    }
    // a rating field pointing at a category that does not exist
    const v = await json(await admin.get(`form-versions/${pdi.draft_version.id}`));
    const fld = v.pages[0].sections[0].fields.find((f: { key: string }) => f.key === "engine_rating");
    await json(await admin.patch(`fields/${fld.id}`, { data: { config: { category: "nope" } } }));
    await page.goto(`/forms/${pdi.id}`);
    await page.getByRole("button", { name: /Check & publish/ }).click();
    await expect(page.getByText("Fix these first")).toBeVisible();
    await expect(page.getByRole("alert").first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Publish now" })).toHaveCount(0);
  });

  test("API keys: shown once, works, then revoked", async ({ page }) => {
    await signIn(page, "admin");
    await page.goto("/api-keys");
    await page.getByRole("button", { name: "New key" }).click();
    const d = page.getByRole("dialog");
    await d.getByLabel("Name").fill("ERP");
    await d.getByLabel("Fields of booking").fill("*");
    await d.getByRole("button", { name: "Save" }).click();
    const key = (await page.getByTestId("api-key").textContent())!.trim();
    expect(key).toMatch(/^vk_[0-9a-f]{8}_/);
    await page.getByRole("dialog").getByRole("button", { name: "Close" }).click();
    await expect(page.locator("tr", { hasText: "ERP" })).toContainText(`vk_${key.split("_")[1]}_…`);
    expect(await page.content()).not.toContain(key); // never shown again
    const ok = await page.request.get(`${API_ROOT}/api/v1/ext/bookings`, { headers: { Authorization: `Api-Key ${key}` } });
    expect(ok.status()).toBe(200);
    page.once("dialog", (x) => x.accept());
    await page.locator("tr", { hasText: "ERP" }).getByRole("button", { name: "Actions for ERP" }).click();
    await page.getByRole("menuitem", { name: "Revoke…" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Revoke key" }).click(); // our own dialog, not the browser's
    await expect(page.locator("tr", { hasText: "ERP" })).toContainText("Revoked");
    const gone = await page.request.get(`${API_ROOT}/api/v1/ext/bookings`, { headers: { Authorization: `Api-Key ${key}` } });
    expect(gone.status()).toBe(401);
  });

  test("forms: export a published form and import it back as a draft", async ({ page }) => {
    await signIn(page, "admin");
    const admin = await apiAs("admin");
    const forms = await json(await admin.get("forms"));
    const pdi = (forms.results ?? forms).find((f: { key: string }) => f.key === "pdi");
    const exported = await admin.get(`promote/export?version=${pdi.published_version.id}`);
    const bundle = await exported.json();
    expect(bundle.form.key).toBe("pdi");
    const path = test.info().outputPath("pdi.json");
    await (await import("node:fs/promises")).writeFile(path, JSON.stringify(bundle));
    await page.goto("/forms");
    await page.getByLabel("Form file to import").setInputFiles(path);
    await expect(page.getByRole("dialog")).toContainText("Import");
    await page.getByRole("button", { name: "Import as a draft" }).click();
    await expect(
      page
        .getByRole("alert")
        .or(page.getByRole("dialog", { name: "Imported as a draft" }))
        .first(),
    ).toBeVisible();
  });

  test("audit log shows what was done", async ({ page }) => {
    await signIn(page, "admin");
    await page.goto("/audit");
    await expect(page.locator("tr", { hasText: "user.create" }).first()).toBeVisible();
    await page.getByLabel("Area").selectOption("api_key");
    await expect(page.locator("tr", { hasText: "api_key.create" }).first()).toBeVisible();
  });

  test("an expert cannot open admin pages and an ops user sees no Users link", async ({ page }) => {
    await signIn(page, "expert");
    await page.goto("/users");
    await expect(page).toHaveURL(/\/jobs$/);
    await page.getByRole("button", { name: "Account menu" }).click();
    await page.getByRole("menuitem", { name: "Sign out" }).click();
    await signIn(page, "ops");
    await expect(page.getByRole("link", { name: "Users" })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Today", exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Library" })).toHaveCount(0);
  });
});
