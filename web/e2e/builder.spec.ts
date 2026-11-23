import { expect, test, type Page } from "@playwright/test";
import { apiAs, json, signIn } from "./api";

async function drag(page: Page, from: ReturnType<Page["locator"]>, to: ReturnType<Page["locator"]>) {
  const a = (await from.boundingBox())!;
  const b = (await to.boundingBox())!;
  await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2);
  await page.mouse.down();
  await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2 + 10, { steps: 4 });
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2 - 4, { steps: 12 });
  await page.mouse.up();
}

async function pdi() {
  const admin = await apiAs("admin");
  const forms = await json(await admin.get("forms"));
  return { admin, form: (forms.results ?? forms).find((f: { key: string }) => f.key === "pdi") };
}

test.describe("form builder", () => {
  test("drag a field to a new place; the order is saved", async ({ page }) => {
    const { admin, form } = await pdi();
    if (!form.draft_version) await json(await admin.post(`forms/${form.id}/drafts`, { data: {} }));
    await signIn(page, "admin");
    await page.goto(`/forms/${form.id}`);
    const rows = page.locator(".field-row");
    await expect(rows.first()).toBeVisible();
    const before = await rows.allInnerTexts();
    const grip = page.locator(".field-row", { hasText: "Odometer" }).locator(".grip");
    await drag(page, grip, page.locator(".field-row", { hasText: "Chassis number" }).locator(".grip"));
    await expect.poll(async () => (await page.locator(".field-row").allInnerTexts()).join("|")).not.toBe(before.join("|"));
    const draftId = (await json(await admin.get(`forms/${form.id}`))).draft_version.id;
    const tree = await json(await admin.get(`form-versions/${draftId}`));
    const sections = tree.pages.flatMap((p: { sections: { fields: { key: string }[] }[] }) => p.sections);
    const sec = sections.find((x: { fields: { key: string }[] }) => x.fields.some((f) => f.key === "odometer"));
    const keys = sec.fields.map((f: { key: string }) => f.key);
    expect(keys, JSON.stringify(keys)).toContain("chassis_no");
    expect(keys.indexOf("odometer")).toBeLessThan(keys.indexOf("chassis_no"));      // moved above it, on the server
    await page.reload();
    expect((await page.locator(".field-row").allInnerTexts()).join("|")).not.toBe(before.join("|"));   // and it stays
  });

  test("discard draft returns to the live version and is refused for a never-published form", async ({ page }) => {
    const { admin, form } = await pdi();
    if (!form.draft_version) await json(await admin.post(`forms/${form.id}/drafts`, { data: {} }));
    await signIn(page, "admin");
    await page.goto(`/forms/${form.id}`);
    await page.getByRole("button", { name: "Discard draft" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Discard draft" }).click();
    await expect(page.getByText("Start a new draft")).toBeVisible();
    expect((await json(await admin.get(`forms/${form.id}`))).draft_version).toBeNull();
    // a brand-new form has nothing to go back to
    await page.goto("/forms");
    await page.getByRole("button", { name: "New form" }).click();
    await page.getByLabel("Name", { exact: true }).fill("Scratch");
    await page.getByLabel("Inspection type").selectOption("ev");
    await page.getByRole("button", { name: "Create" }).click();
    await page.getByRole("button", { name: "Discard draft" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Discard draft" }).click();
    await expect(page.getByRole("status").filter({ hasText: /never been published/ })).toBeVisible();
  });

  test("the library is used from the builder: save a field, then add it to a section", async ({ page }) => {
    const { admin, form } = await pdi();
    if (!form.draft_version) await json(await admin.post(`forms/${form.id}/drafts`, { data: {} }));
    await signIn(page, "admin");
    await page.goto("/library");
    await expect(page.getByRole("heading", { name: "Library" })).toBeVisible();
    await page.goto(`/forms/${form.id}`);
    await page.getByRole("button", { name: /Odometer/ }).first().click();
    await page.getByLabel("Library item name").fill("Odometer reading");
    await page.getByRole("button", { name: "Save to library" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Saved to the library" })).toBeVisible();
    await page.goto("/library");
    await expect(page.getByRole("cell", { name: "Odometer reading" })).toBeVisible();
  });

  test("access: presets and cells change what the matrix shows", async ({ page }) => {
    const { admin, form } = await pdi();
    if (!form.draft_version) await json(await admin.post(`forms/${form.id}/drafts`, { data: {} }));
    await signIn(page, "admin");
    await page.goto(`/forms/${form.id}`);
    await page.getByRole("button", { name: /Driver front door/ }).first().click();
    await page.getByRole("tab", { name: "Access" }).click();
    await expect(page.getByRole("button", { name: "expert Working: Can edit" })).toBeVisible();      // the standard rule
    await page.getByRole("button", { name: "Ops only" }).click();
    await expect(page.getByRole("button", { name: "expert Working: Hidden" })).toBeVisible();
    await page.getByRole("button", { name: "Read-only for experts" }).click();
    await expect(page.getByRole("button", { name: "expert Working: Can see" })).toBeVisible();
    await page.getByRole("button", { name: "ops Submitted: Can edit" }).click();                 // cycles to the next level
    await page.getByRole("button", { name: "Reset to inherited" }).click();
    await expect(page.getByRole("button", { name: "expert Working: Can edit" })).toBeVisible();
  });

  test("a photo field can be camera-only, and the preview honours it", async ({ page }) => {
    const { admin, form } = await pdi();
    if (!form.draft_version) await json(await admin.post(`forms/${form.id}/drafts`, { data: {} }));
    await signIn(page, "admin");
    await page.goto(`/forms/${form.id}`);
    await page.getByRole("button", { name: /Door photo/ }).first().click();
    await page.getByLabel("How files are added").selectOption("camera");
    await page.getByRole("button", { name: "Save field" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Saved" }).first()).toBeVisible();
    await page.getByRole("button", { name: "Preview" }).click();
    const preview = page.getByRole("dialog", { name: "Preview" });
    await preview.getByLabel("Driver front door").getByRole("radio", { name: "Dent" }).click();
    await expect(preview.getByRole("button", { name: /Open camera/ })).toBeVisible();
    await expect(preview.getByRole("button", { name: /Attach a photo/ })).toHaveCount(0);
  });
});

test.describe("layout", () => {
  test("the menu collapses to icons and remembers it", async ({ page }) => {
    await signIn(page, "admin");
    await page.goto("/forms");
    await expect(page.getByRole("link", { name: "Forms" }).getByText("Forms")).toBeVisible();
    await page.getByRole("button", { name: "Collapse the menu" }).click();
    await expect(page.getByRole("link", { name: "Forms" }).locator(".nav-label")).toBeHidden();
    await page.reload();
    await expect(page.getByRole("button", { name: "Expand the menu" })).toBeVisible();      // remembered
    await page.getByRole("button", { name: "Expand the menu" }).click();
  });

  test("the little i explains things", async ({ page }) => {
    await signIn(page, "admin");
    await page.goto("/roles");
    await page.getByRole("button", { name: "More info" }).first().click();
    await expect(page.getByRole("tooltip")).toContainText("cycle");
    await page.keyboard.press("Escape");
    await expect(page.getByRole("tooltip")).toHaveCount(0);
  });
});
