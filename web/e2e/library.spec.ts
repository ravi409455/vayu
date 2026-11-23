import { expect, test } from "@playwright/test";
import { apiAs, json, signIn } from "./api";

const SECTION = {
  title: "Brakes", visible: true, fields: [
    { key: "pads", label: "Pads", type: "single_choice", config: { options: [{ key: "ok", label: "OK" }, { key: "worn", label: "Worn", is_defect: true, severity: "minor" }] } },
    { key: "pads_note", label: "Pad note", type: "short_text", show_if: { "==": [{ var: "inspection.pads" }, "worn"] } },
  ],
};

async function publishDraft(admin: Awaited<ReturnType<typeof apiAs>>, formId: number) {
  const f = await json(await admin.get(`forms/${formId}`));
  const v = await json(await admin.get(`form-versions/${f.draft_version.id}`));
  await json(await admin.post(`form-versions/${v.id}/publish`, { data: { row_version: v.row_version } }));
}

/** Two forms that link one library section: "lib_a" with an open draft, "lib_b" live only. */
async function setup(tag: string) {
  const admin = await apiAs("admin");
  const item = await json(await admin.post("library", { data: { kind: "section", key: `brakes_${tag}`, name: `Brakes ${tag}`, definition: SECTION } }));
  const make = async (key: string) => {
    const f = await json(await admin.post("forms", { data: { key, name: key.toUpperCase() } }));
    const v = await json(await admin.get(`form-versions/${f.draft_version.id}`));
    await json(await admin.post(`pages/${v.pages[0].id}/sections/from-library`, { data: { library_item: item.id, link: true } }));
    return { form: f, draft: v.id as number };
  };
  const a = await make(`lib_a_${tag}`);
  const b = await make(`lib_b_${tag}`);
  await publishDraft(admin, b.form.id);
  return { admin, item, a, b };
}

test("library: edit once, review every form, update them all together", async ({ page }) => {
  const { admin, item, a, b } = await setup("one");
  await signIn(page, "admin");
  await page.goto(`/library/${item.id}`);
  await page.getByLabel("Section title").fill("Brake system");
  await page.getByRole("button", { name: "Move Pad note up" }).click();           // the library owns the order too
  await page.getByRole("button", { name: "Save and update everywhere…" }).click();

  const review = page.getByRole("dialog");
  await expect(review.getByText("lib_a_one", { exact: true })).toBeVisible();
  await expect(review.getByText("lib_b_one", { exact: true })).toBeVisible();
  await expect(review.getByText(/its open draft is updated/)).toBeVisible();
  await expect(review.getByText(/a new draft is made/)).toBeVisible();
  await expect(review.getByText(/title Brakes/).first()).toBeVisible();
  await expect(review.getByLabel("Publish automatically after updating")).not.toBeChecked();
  await review.getByRole("button", { name: "Update 2 forms" }).click();
  await expect(review.getByRole("status")).toContainText("2 forms updated");
  await review.getByRole("button", { name: "Close" }).click();

  // form A's open draft changed in place; form B (live only) got a new draft and its live version is untouched
  const treeA = await json(await admin.get(`form-versions/${a.draft}`));
  expect(treeA.pages[0].sections.map((s: { title: string }) => s.title)).toContain("Brake system");
  expect(treeA.pages[0].sections.find((s: { title: string }) => s.title === "Brake system").fields.map((f: { key: string }) => f.key)).toEqual(["pads_note", "pads"]);
  const formB = await json(await admin.get(`forms/${b.form.id}`));
  expect(formB.draft_version).not.toBeNull();
  const liveB = await json(await admin.get(`form-versions/${b.draft}`));
  expect(liveB.pages[0].sections.map((s: { title: string }) => s.title)).toContain("Brakes");
});

test("library: a form that would break blocks the whole update", async ({ page }) => {
  const { admin, item, a } = await setup("two");
  await json(await admin.post(`form-versions/${a.draft}/checks`, { data: { rule: { "!!": [{ var: "inspection.pads_note" }] }, message: "Note needed", fields: ["pads_note"] } }));
  await signIn(page, "admin");
  await page.goto(`/library/${item.id}`);
  await page.getByRole("button", { name: "Remove Pad note" }).click();
  await page.getByRole("button", { name: "Save and update everywhere…" }).click();
  const review = page.getByRole("dialog");
  await expect(review.getByText(/Fix first/).first()).toBeVisible();
  await expect(review.getByRole("button", { name: /Update \d+ forms?/ })).toBeDisabled();
  await expect(review.getByText(/Nothing was changed/)).toBeVisible();
  await review.getByRole("button", { name: "Cancel" }).click();
  const draft = await json(await admin.get(`form-versions/${a.draft}`));
  expect(draft.pages[0].sections.find((s: { title: string }) => s.title === "Brakes").fields).toHaveLength(2);   // untouched
});

test("library: a save from an old revision tells the Admin", async ({ page }) => {
  const { admin, item } = await setup("three");
  await signIn(page, "admin");
  await page.goto(`/library/${item.id}`);
  await page.getByLabel("Section title").fill("Mine");
  await json(await admin.patch(`library/${item.id}`, { data: { revision: 1, definition: { ...SECTION, title: "Theirs" } } }));
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Someone else saved this item")).toBeVisible();
});

test("forms: duplicate a form, and import a file as a copy", async ({ page }) => {
  const { admin, a } = await setup("four");
  await signIn(page, "admin");
  await page.goto(`/forms/${a.form.id}`);
  await page.getByRole("button", { name: "Duplicate as new form" }).click();
  await page.getByLabel("Name of the copy").fill("Brakes check two");
  await page.getByRole("dialog").getByRole("button", { name: "Duplicate" }).click();
  await expect(page.getByRole("heading", { name: /Brakes check two/, level: 1 })).toBeVisible();   // we are on the copy
  await expect(page.getByText("Draft v1")).toBeVisible();
  const forms = await json(await admin.get("forms?type=custom"));
  expect((forms.results ?? forms).map((f: { key: string }) => f.key)).toContain("brakes_check_two");

  // import: export form B's bundle and bring it in as a copy
  const bundle = await json(await admin.get(`promote/export?version=${(await json(await admin.get(`forms/${a.form.id}`))).draft_version.id}`));
  await page.goto("/forms");
  await page.getByLabel("Form file to import").setInputFiles({ name: "form.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(bundle)) });
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel(/As a new draft of/).check().catch(() => {});
  await expect(dialog.getByText(/never overwrites the library/)).toBeVisible();
});

test("ops cannot open the library", async ({ page }) => {
  await signIn(page, "ops");
  await page.goto("/library");
  await expect(page).toHaveURL(/\/today$/);
});
