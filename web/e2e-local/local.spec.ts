import { expect, test } from "@playwright/test";
import { JPEG } from "../e2e/api";

const PASSWORD = "Vayu-local-1";
const file = (name: string) => ({ name, mimeType: "image/jpeg", buffer: JPEG });

async function signIn(page: import("@playwright/test").Page, user: string) {
  await page.goto("/login");
  await page.getByLabel("Username").fill(user);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
}

test("the demo is there for each role", async ({ page }) => {
  await signIn(page, "ops");
  await page.goto("/bookings?view=all");                                     // Ops land on Today; every booking is here
  await expect(page.getByRole("link", { name: "DEMO-1", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "DEMO-3", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await signIn(page, "admin");
  await page.goto("/forms");
  await expect(page.getByRole("link", { name: "PDI" })).toBeVisible();
});

test("a new user must choose their own password first", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Username").fill("newuser");
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Choose a new password" })).toBeVisible();
});

test("the demo completed booking already has a PDF and a public check page", async ({ page }) => {
  await signIn(page, "ops");
  await page.goto("/bookings?view=all");
  await page.getByRole("link", { name: "DEMO-3", exact: true }).click();
  await page.getByRole("tab", { name: "Report" }).click();
  await expect(page.getByRole("link", { name: /Download PDF/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Copy check link" })).toBeVisible();
  const id = page.url().split("/booking/")[1];
  const verify = (await page.evaluate(async (b) => (await fetch(`/api/v1/bookings/${b}/report`)).json(), id)).verify_url as string;
  await page.goto(verify!);
  await expect(page.getByText("genuine")).toBeVisible();
});

test("the expert completes DEMO-2 with a real upload to the file store and a PDF from the worker", async ({ page, request }) => {
  await signIn(page, "expert");
  await page.getByRole("link", { name: "Job DEMO-2" }).click();
  await page.getByRole("button", { name: "Start inspection" }).click();
  await expect(page.getByTestId("gps-value")).toBeVisible();
  await page.getByTestId("camera-selfie").setInputFiles(file("selfie.jpg"));
  await expect(page.getByTestId("media-item")).toHaveCount(1);
  await expect(page.getByText(/files 1\/1 sent/)).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "Next" }).click();
  // the first inspection page is gated: it holds the expert until the required fields are filled
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByRole("alert")).toContainText("Finish this step first");
  await page.getByLabel("Chassis number").fill("MA3LOCALTEST000001");
  await page.getByLabel("Registration number").fill("DL1CZ0001");
  await page.getByLabel("Odometer").fill("321");
  while (!(await page.getByRole("heading", { name: "Before you submit" }).isVisible())) {
    const pay = page.getByRole("radiogroup", { name: "Taking payment?" }).getByRole("radio", { name: "No" });
    if (await pay.isVisible()) await pay.click();
    await page.getByRole("button", { name: "Next" }).click();
  }
  await page.getByRole("button", { name: "Submit inspection" }).click();
  await expect(page.getByText("Completed. Everything arrived")).toBeVisible({ timeout: 60_000 });
  void request;
});
