import { expect, test } from "@playwright/test";
import { apiAs, JPEG, json, signIn, uploadFile } from "./api";

// J1: build a 2-page form with a condition, publish it, map it in a PDF template, preview the PDF.
test("J1: admin builds, publishes and maps a form, then previews its PDF", async ({ page }) => {
  await signIn(page, "admin");
  await page.goto("/forms");
  await page.getByRole("button", { name: "New custom form" }).click();
  await page.getByLabel("Name", { exact: true }).fill("Used car");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByText("Draft v1")).toBeVisible();

  // page 1: an accident question and a follow-up that only shows when it is "yes"
  const addField = async (label: string, type: string, nth = 0) => {
    await page.getByRole("button", { name: "Add field" }).nth(nth).click();
    await page.getByRole("button", { name: type, exact: true }).click();
    await page.getByRole("dialog").getByLabel("Label", { exact: true }).fill(label);
    await page.getByRole("dialog").getByRole("button", { name: "Add field" }).click();
    await expect(page.getByRole("button", { name: new RegExp(label) }).first()).toBeVisible();
  };
  await addField("Odometer", "Number");
  await addField("Accident history", "Yes / No");
  await addField("Accident details", "Short text");
  await page.getByRole("button", { name: /Accident details/ }).first().click();
  await page.getByRole("tab", { name: "Logic" }).click();
  await page.getByRole("button", { name: "+ Add condition" }).last().click();
  await page.getByLabel("Field", { exact: true }).last().selectOption({ label: "inspection: Accident history" });
  await page.getByLabel("Operator", { exact: true }).last().selectOption("==");
  await page.getByLabel("Value", { exact: true }).last().fill("true");
  await page.getByRole("button", { name: "Save field" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Saved" }).first()).toBeVisible();

  // the first page must be finished before moving on: odometer required
  await page.getByRole("button", { name: /Odometer/ }).first().click();
  await page.getByRole("tab", { name: "Settings" }).click();
  await page.getByRole("switch", { name: "Required", exact: true }).check();
  await page.getByRole("button", { name: "Save field" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Saved" }).first()).toBeVisible();
  await page.locator(".rail-item", { hasText: "Page 1" }).click();
  await page.getByRole("checkbox", { name: /Must be finished before moving on/ }).check();
  await page.getByRole("button", { name: "Save page" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Saved" }).first()).toBeVisible();

  // page 2
  await page.getByRole("button", { name: "Add page" }).click();
  await page.getByLabel("Page name").fill("Final");
  await page.getByRole("dialog").getByRole("button", { name: "Add", exact: true }).click();
  await page.locator(".rail-item", { hasText: "Final" }).click();
  await page.getByRole("button", { name: "Add section" }).click();
  await page.getByLabel("Section name").fill("Notes");
  await page.getByRole("dialog").getByRole("button", { name: "Add blank section" }).click();
  await page.getByRole("button", { name: "Add field" }).last().click();
  await page.getByRole("button", { name: "Long text", exact: true }).click();
  await page.getByRole("dialog").getByLabel("Label", { exact: true }).fill("Remarks");
  await page.getByRole("dialog").getByRole("button", { name: "Add field" }).click();
  await expect(page.getByRole("button", { name: /Remarks/ }).first()).toBeVisible();

  // preview: the gate holds an expert on page 1 until the odometer is filled
  await page.getByRole("button", { name: "Preview" }).click();
  const preview = page.getByRole("dialog", { name: "Preview" });
  await expect(preview.getByText("Page 1 of 2")).toBeVisible();
  await preview.getByRole("button", { name: "Next" }).click();
  await expect(preview.getByRole("alert")).toContainText("Finish this page first");
  await expect(preview.getByRole("alert")).toContainText("Odometer");
  await expect(preview.getByRole("alert")).toContainText("Chassis number");          // a required system field too
  await preview.getByLabel("Chassis number").fill("MA3TEST");
  await preview.getByLabel("Odometer").fill("1200");
  await preview.getByRole("radio", { name: "Yes" }).click();
  await expect(preview.getByLabel("Accident details")).toBeVisible();              // the rule showed it
  await preview.getByRole("button", { name: "Next" }).click();
  await expect(preview.getByText("Page 2 of 2")).toBeVisible();
  await preview.getByRole("button", { name: "Close preview" }).click();

  // publish
  await page.getByRole("button", { name: /Check & publish/ }).click();
  await expect(page.getByText("Ready to publish")).toBeVisible();
  await page.getByRole("button", { name: "Publish now" }).click();
  await expect(page.getByRole("dialog", { name: "Published" })).toBeVisible();
  await page.getByRole("dialog").getByRole("button", { name: "Close" }).click();
  await expect(page.getByText("Live v1").first()).toBeVisible();

  // PDF template: a page with a table showing Odometer under its own report label
  await page.goto("/pdf");
  await page.getByLabel("Create a template for").selectOption({ label: "Used car" });
  await page.getByRole("button", { name: "Add page" }).click();
  await page.getByRole("menuitem", { name: /Blank page/ }).click();
  await page.getByRole("button", { name: "+ Add to this page" }).click();
  await page.getByRole("menuitem", { name: /Table of checks/ }).click();
  await page.getByLabel("Title", { exact: true }).fill("Condition");
  await page.getByRole("radio", { name: /Checks I pick/ }).check();
  await page.getByRole("button", { name: "+ Add row" }).click();
  await page.getByLabel("Field", { exact: true }).selectOption({ label: "inspection: Odometer" });
  await page.getByLabel("Report label").fill("Kilometres driven");
  await expect(page.getByText("All changes saved")).toBeVisible({ timeout: 10_000 });
  await page.getByRole("button", { name: "Publish" }).click();
  await expect(page.getByText("Live v1")).toBeVisible();

  // a real booking of this type, submitted, so the preview has data
  const ops = await apiAs("ops");
  const admin = await apiAs("admin");
  const expert = await apiAs("expert");
  const users = await json(await admin.get("users"));
  const expertId = (users.results ?? users).find((u: { username: string }) => u.username === "expert").id;
  const b = await json(await ops.post("bookings", { data: { answers: {
    booking_id: "UC-1", customer_name: "Meera", customer_phone: "9876543210", address: "1 Ring Rd", city: "delhi",
    inspection_date: "2026-11-24", inspection_time: "10:00", inspection_type: "used_car", car_make_model: "tata_nexon" } } }));
  await json(await ops.post(`bookings/${b.id}/assign`, { data: { expert: expertId } }));
  const selfie = await uploadFile(expert, b.id, "selfie", "photo", "image/jpeg", JPEG);
  await json(await expert.post(`bookings/${b.id}/start`, { data: { client_uuid: crypto.randomUUID(), inspection_type: "used_car", start_answers: { selfie: [selfie] } } }));
  await json(await expert.post(`bookings/${b.id}/submit`, { data: { client_submission_uuid: crypto.randomUUID(), answers: { inspection: { chassis_no: "MA3ABCDEFG123456", odometer: 12345 }, start: { selfie: [selfie] }, end: { taking_payment: false } } } }));

  await page.reload();                                                        // the picker now finds the booking
  await page.getByRole("tab", { name: "Used car" }).click();
  const pdf = page.waitForResponse((r) => r.url().includes("/preview") && r.request().method() === "POST" && r.status() === 200);
  await page.getByLabel("Booking for the preview").selectOption(b.id);         // picked by Booking ID, not a typed internal id
  const res = await pdf;
  const body = await res.json();
  expect(Buffer.from(body.pdf, "base64").subarray(0, 4).toString()).toBe("%PDF");
  expect(body.pages[0].parts.length).toBeGreaterThan(0);                       // where each part sits, for clicking
  await expect(page.locator("canvas[aria-label=\"Page 1\"]")).toBeVisible();
  await page.getByRole("button", { name: "Select Condition" }).click();       // click the table in the PDF
  await expect(page.getByLabel("Title", { exact: true })).toHaveValue("Condition");

  // sharing: the table becomes a shared part, the look a shared theme
  await page.getByRole("button", { name: "Start a new draft" }).click();
  await page.getByRole("button", { name: "Condition", exact: true }).click();
  await page.getByText("Share with other reports").click();
  await page.getByLabel("Save this part as a shared part: name").fill("Condition block");
  await page.getByRole("button", { name: "Share", exact: true }).click();
  await expect(page.getByText(/^Shared\./)).toBeVisible();
  await expect(page.getByTitle("Shared with other reports")).toBeVisible();
  await page.getByRole("button", { name: "Report settings" }).click();
  await page.getByRole("tab", { name: "Theme" }).click();
  await page.getByLabel("Save this report's look as a shared theme: name").fill("House look");
  await page.getByRole("button", { name: "Share", exact: true }).click();
  await expect(page.getByText(/uses the shared theme/)).toContainText("House look");
  await page.getByRole("tab", { name: "Header and footer" }).click();
  await expect(page.getByText(/These come from the shared theme “House look”/)).toBeVisible();
  await page.getByRole("button", { name: "Done" }).click();
  await expect(page.getByText("All changes saved")).toBeVisible({ timeout: 10_000 });

  // backup and restore: export the file, then import it back over the draft
  await page.getByRole("button", { name: "More template actions" }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("menuitem", { name: "Export (backup file)" }).click();
  const file = JSON.parse(await (await (await download).createReadStream()).toArray().then((c) => Buffer.concat(c).toString()));
  expect(file.kind).toBe("vayu-report-template");
  expect(file.shared.map((i: { name: string }) => i.name).sort()).toEqual(["Condition block", "House look"]);
  await page.getByLabel("Template file").setInputFiles({ name: "backup.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(file)) });
  await page.getByRole("button", { name: "Import", exact: true }).click();
  await expect(page.getByText(/Imported into draft v2/)).toBeVisible();
});
