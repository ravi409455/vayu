import { createHmac } from "node:crypto";
import { createServer, type Server } from "node:http";
import { expect, test } from "@playwright/test";
import { signIn, submittedJob, waitForReport } from "./api";

type Hit = { headers: Record<string, string | string[] | undefined>; body: string };

// J5: a webhook reaches a local receiver with a valid HMAC; the ZIP link prepares and downloads;
// the verify page shows the summary only
test("J5: webhook with a valid signature, ZIP download and the verify page", async ({ page }) => {
  const hits: Hit[] = [];
  const server: Server = createServer((req, res) => {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => { hits.push({ headers: req.headers, body }); res.writeHead(200).end("ok"); });
  });
  await new Promise<void>((r) => server.listen(9099, "127.0.0.1", r));
  try {
    await signIn(page, "admin");
    await page.goto("/integrations");
    await page.getByRole("button", { name: "New integration" }).click();
    const d = page.getByRole("dialog");
    await d.getByLabel("Name", { exact: true }).fill("Receiver");
    await d.getByLabel("Form", { exact: true }).selectOption({ label: "PDI" });
    await d.getByLabel("Webhook URL").fill("http://127.0.0.1:9099/hook");
    await d.getByRole("checkbox", { name: /PDF ready/ }).check();
    await d.getByRole("checkbox", { name: /PDF link/ }).check();
    await d.getByRole("checkbox", { name: /Image ZIP link/ }).check();
    await d.getByRole("button", { name: "Save" }).click();
    const secret = (await page.getByTestId("secret").textContent())!.trim();
    expect(secret).toMatch(/^whsec_/);
    await page.getByRole("dialog").getByRole("button", { name: "Close" }).click();

    // the test button
    await page.getByRole("button", { name: "Test", exact: true }).click();
    await expect(page.getByRole("status")).toContainText("Test sent: 200");
    await expect.poll(() => hits.length).toBe(1);

    // a real job with a photo, completed
    const id = await submittedJob({ bookingId: "J5-1", door: "dent", photo: true });
    const report = await waitForReport(id);
    await expect.poll(() => hits.filter((h) => h.headers["x-vayu-event"] === "pdf.ready").length, { timeout: 30_000 }).toBeGreaterThan(0);
    const hit = hits.find((h) => h.headers["x-vayu-event"] === "pdf.ready")!;
    const expected = "sha256=" + createHmac("sha256", secret).update(hit.body).digest("hex");
    expect(hit.headers["x-vayu-signature"]).toBe(expected);                       // signed over the raw body
    const payload = JSON.parse(hit.body);
    expect(payload.booking.booking_id).toBe("J5-1");
    expect(payload.booking.id).toBe(id);                                          // both IDs
    expect(payload.pdf_url).toMatch(/^http/);
    expect(payload.image_zip_url).toMatch(/\/zip\//);

    // the delivery log shows it
    await page.getByRole("button", { name: /^Actions for / }).first().click();
    await page.getByRole("menuitem", { name: "Deliveries" }).click();
    await expect(page.getByRole("dialog").locator("tr", { hasText: "pdf.ready" })).toContainText("success");
    await page.getByRole("dialog").getByRole("button", { name: "Close" }).click();

    // the ZIP link: "Preparing…" then the download starts by itself
    const zipPage = await page.context().newPage();
    const download = zipPage.waitForEvent("download", { timeout: 30_000 });
    await zipPage.goto(payload.image_zip_url);
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

test("verify page for a made-up token says so plainly", async ({ page }) => {
  await page.goto("/verify/not-a-real-token");
  await expect(page.getByRole("alert")).toContainText("could not find this report");
});

test("an expired or wrong ZIP link says so", async ({ page }) => {
  await page.goto("/zip/garbage");
  await expect(page.getByRole("alert")).toContainText("invalid, expired");
});
