import { createServer, type Server } from "node:http";
import { expect, test, type Page } from "@playwright/test";
import { signIn, submittedJob, waitForReport } from "./api";

type Hit = { method: string; url: string; headers: Record<string, string | string[] | undefined>; body: string };

/** Pick a value (by its ref) from the searchable list that "+ value" opens next to `label`. */
async function pick(page: Page, label: string, ref: string) {
  await page.getByRole("button", { name: `Insert a value into ${label}` }).click();
  await page.locator(`[role=option][title="${ref}"]`).click();
}

// J5: an integration designed in the editor (method, a value in the URL path, a header, a custom
// body) reaches a local receiver exactly as previewed; the ZIP link prepares and downloads;
// the verify page shows the summary only
test("J5: a designed request reaches the receiver, the ZIP downloads and the verify page shows a summary", async ({ page }) => {
  const hits: Hit[] = [];
  const server: Server = createServer((req, res) => {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => { hits.push({ method: req.method!, url: req.url!, headers: req.headers, body }); res.writeHead(200).end("ok"); });
  });
  await new Promise<void>((r) => server.listen(9099, "127.0.0.1", r));
  try {
    await signIn(page, "admin");
    await page.goto("/integrations");
    await page.getByRole("button", { name: "New integration" }).click();
    await page.getByRole("textbox", { name: "Name", exact: true }).fill("Receiver");
    await page.getByRole("combobox", { name: "Form", exact: true }).selectOption({ label: "PDI" });
    await page.getByRole("combobox", { name: "Send when" }).selectOption("pdf.ready");
    await page.getByRole("combobox", { name: "Method" }).selectOption("PUT");
    await page.getByRole("textbox", { name: "URL", exact: true }).fill("http://127.0.0.1:9099/hook/");
    await pick(page, "URL", "job.booking_id");
    await page.getByRole("button", { name: "Add header" }).click();
    await page.getByRole("textbox", { name: "Header name 1" }).fill("X-Token");
    await page.getByRole("textbox", { name: "Header value 1" }).fill("abc123");
    await page.getByRole("button", { name: "Custom" }).click();
    await page.getByRole("button", { name: "Add row" }).click();
    await page.getByRole("textbox", { name: "Key 1", exact: true }).fill("ref");
    await pick(page, "Value 1", "job.booking_id");
    await page.getByRole("button", { name: "Add row" }).click();
    await page.getByRole("textbox", { name: "Key 2", exact: true }).fill("report");
    await pick(page, "Value 2", "link.pdf");
    await page.getByRole("button", { name: "Add row" }).click();
    await page.getByRole("textbox", { name: "Key 3", exact: true }).fill("images");
    await pick(page, "Value 3", "link.image_zip");
    await page.getByRole("button", { name: "Add group" }).click();
    await page.getByRole("textbox", { name: "Key 4", exact: true }).fill("customer");
    await page.locator(".brow", { has: page.getByRole("textbox", { name: "Key 4", exact: true }) }).getByRole("button", { name: "Add row" }).click();
    await page.getByRole("textbox", { name: "Key 4.1", exact: true }).fill("name");
    await pick(page, "Value 4.1", "booking.customer_name");
    // the preview shows the request that will be sent
    const preview = page.getByTestId("preview-request");
    await expect(preview).toContainText("PUT http://127.0.0.1:9099/hook/");
    await expect(preview).toContainText("X-Token: abc123");
    await expect(preview).toContainText('"customer"');
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByRole("link", { name: "Integrations" }).first()).toBeVisible();
    await expect(page.getByText("Receiver")).toBeVisible();

    // a real job with a photo, completed
    const id = await submittedJob({ bookingId: "J5-1", door: "dent", photo: true });
    const report = await waitForReport(id);
    await expect.poll(() => hits.filter((h) => h.headers["x-vayu-event"] === "pdf.ready").length, { timeout: 30_000 }).toBeGreaterThan(0);
    const hit = hits.find((h) => h.headers["x-vayu-event"] === "pdf.ready")!;
    expect(hit.method).toBe("PUT");
    expect(hit.url).toBe("/hook/J5-1");                                           // the Booking ID went into the path
    expect(hit.headers["x-token"]).toBe("abc123");
    expect(hit.headers["x-vayu-signature"]).toBeUndefined();                      // no signing: the token header is the proof
    const payload = JSON.parse(hit.body);
    expect(payload.ref).toBe("J5-1");
    expect(payload.report).toMatch(/^http/);
    expect(payload.images).toMatch(/\/zip\//);
    expect(payload.customer.name).toBe("Test Customer");                          // only what was mapped
    expect(Object.keys(payload).sort()).toEqual(["customer", "images", "ref", "report"]);

    // the test button sends the same designed request, marked as a test
    await page.getByRole("button", { name: "Test", exact: true }).click();
    await expect(page.getByRole("status")).toContainText("Test sent: 200");
    await expect.poll(() => hits.some((h) => h.headers["x-vayu-test"] === "1")).toBe(true);

    // the delivery log shows it
    await page.getByRole("button", { name: /^Actions for / }).first().click();
    await page.getByRole("menuitem", { name: "Deliveries" }).click();
    await expect(page.getByRole("dialog").locator("tr", { hasText: "PDF ready" })).toContainText("Delivered");
    await page.getByRole("dialog").getByRole("button", { name: "Close" }).click();

    // the ZIP link: "Preparing…" then the download starts by itself
    const zipPage = await page.context().newPage();
    const download = zipPage.waitForEvent("download", { timeout: 30_000 });
    await zipPage.goto(payload.images);
    const file = await download;
    expect(file.suggestedFilename()).toBe("J5-1.zip");

    // the verify page: a summary and nothing about the customer
    const verify = await page.context().newPage();
    await verify.goto(report.verify_url);
    await expect(verify.getByText("genuine")).toBeVisible();
    await expect(verify.getByText("J5-1")).toBeVisible();
    const text = await verify.locator("body").innerText();
    expect(text).not.toContain("Test Customer");
    expect(text).not.toContain("9876500099");
    expect(text).not.toContain("9 Test Street");
  } finally {
    server.close();
  }
});

test("a GET or DELETE integration has no body, and the editor says what a booking form can send", async ({ page }) => {
  await signIn(page, "admin");
  await page.goto("/integrations/new");
  await page.getByRole("textbox", { name: "Name", exact: true }).fill("Lookup");
  await expect(page.getByRole("combobox", { name: "Send when" }).locator("option")).toHaveCount(3);   // the booking form: booking events only
  await page.getByRole("combobox", { name: "Method" }).selectOption("GET");
  await expect(page.getByText("No body is sent with GET.")).toBeVisible();
  await page.getByRole("textbox", { name: "URL", exact: true }).fill("http://127.0.0.1:9099/lookup/");
  await pick(page, "URL", "job.booking_id");
  await expect(page.getByTestId("preview-request")).toContainText("GET http://127.0.0.1:9099/lookup/");
  await page.getByRole("combobox", { name: "Method" }).selectOption("DELETE");
  await expect(page.getByText("No body is sent with DELETE.")).toBeVisible();
});

test("verify page for a made-up token says so plainly", async ({ page }) => {
  await page.goto("/verify/not-a-real-token");
  await expect(page.getByRole("alert")).toContainText("could not find this report");
});

test("an expired or wrong ZIP link says so", async ({ page }) => {
  await page.goto("/zip/garbage");
  await expect(page.getByRole("alert")).toContainText("invalid, expired");
});
