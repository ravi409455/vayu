import { expect, test } from "@playwright/test";
import { apiAs, json, signIn } from "./api";

// J1: build a 2-page form with a condition, publish it, map it in a PDF template, preview the PDF.
test("J1: admin builds, publishes and maps a form, then previews its PDF", async ({ page }) => {
  await signIn(page, "admin");
  await page.goto("/forms");
  await page.getByRole("button", { name: "New form" }).click();
  await page.getByLabel("Name", { exact: true }).fill("Used car");
  await page.getByLabel("Inspection type").selectOption("used_car");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByText("Editing draft v1")).toBeVisible();

  // page 1: an accident question and a follow-up that only shows when it is "yes"
  const addField = async (label: string, type: string) => {
    await page.getByRole("button", { name: "+ Add field" }).first().click();
    await page.getByRole("dialog").getByLabel("Label", { exact: true }).fill(label);
    await page.getByRole("dialog").getByLabel("Type").selectOption(type);
    await page.getByRole("dialog").getByRole("button", { name: "Add", exact: true }).click();
    await expect(page.locator(".tree-item", { hasText: label })).toBeVisible();
  };
  await addField("Odometer", "number");
  await addField("Accident history", "yes_no");
  await addField("Accident details", "short_text");
  await page.locator(".tree-item", { hasText: "Accident details" }).click();
  await page.getByRole("button", { name: "+ Add condition" }).last().click();
  await page.getByLabel("Field", { exact: true }).last().selectOption({ label: "inspection: Accident history" });
  await page.getByLabel("Operator", { exact: true }).last().selectOption("==");
  await page.getByLabel("Value", { exact: true }).last().fill("true");
  await page.getByRole("button", { name: "Save field" }).click();
  await expect(page.getByRole("status")).toContainText("Saved");

  // page 2
  await page.getByRole("button", { name: "+ Add page" }).click();
  await page.getByLabel("Page name").fill("Final");
  await page.getByRole("dialog").getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.locator(".tree-item", { hasText: "Final" })).toBeVisible();
  await page.getByRole("button", { name: "+ Add section" }).last().click();
  await page.getByLabel("Section name").fill("Notes");
  await page.getByRole("dialog").getByRole("button", { name: "Add", exact: true }).click();
  await page.getByRole("button", { name: "+ Add field" }).last().click();
  await page.getByRole("dialog").getByLabel("Label", { exact: true }).fill("Remarks");
  await page.getByRole("dialog").getByLabel("Type").selectOption("long_text");
  await page.getByRole("dialog").getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.locator(".tree-item", { hasText: "Remarks" })).toBeVisible();

  // publish
  await page.getByRole("button", { name: /Check & publish/ }).click();
  await expect(page.getByText("Ready to publish")).toBeVisible();
  await page.getByRole("button", { name: "Publish now" }).click();
  await expect(page.getByRole("dialog", { name: "Published" })).toBeVisible();
  await page.getByRole("dialog").getByRole("button", { name: "Close" }).click();
  await expect(page.getByText("Live: v1")).toBeVisible();

  // PDF template: map Odometer to a report label
  await page.goto("/pdf");
  await page.getByLabel("Create a template for").selectOption({ label: "Used car" });
  await page.getByLabel("Add a block").selectOption("table");
  await page.getByLabel("Title").first().fill("Condition");
  await page.getByRole("button", { name: "+ Add row" }).click();
  await page.getByLabel("Field", { exact: true }).selectOption({ label: "inspection: Odometer" });
  await page.getByLabel("Report label").fill("Kilometres driven");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Saved");
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
  await json(await expert.post(`bookings/${b.id}/start`, { data: { client_uuid: crypto.randomUUID(), inspection_type: "used_car" } }));
  await json(await expert.post(`bookings/${b.id}/submit`, { data: { client_submission_uuid: crypto.randomUUID(), answers: { inspection: { chassis_no: "MA3ABCDEFG123456", odometer: 12345 }, ops: { payment_status: "pay_later" } } } }));

  await page.getByPlaceholder("Booking (internal id) for the preview").fill(b.id);
  const pdf = page.waitForResponse((r) => r.url().includes("/preview") && r.request().method() === "POST");
  await page.getByRole("button", { name: "Preview PDF" }).click();
  const res = await pdf;
  expect(res.status()).toBe(200);
  expect(res.headers()["content-type"]).toContain("application/pdf");
  expect((await res.body()).subarray(0, 4).toString()).toBe("%PDF");
  await expect(page.getByTitle("PDF preview")).toBeVisible();
});
