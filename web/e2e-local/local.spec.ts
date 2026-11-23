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
  await expect(page.getByRole("link", { name: "DEMO-1" })).toBeVisible();
  await expect(page.getByRole("link", { name: "DEMO-3" })).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
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
  await page.getByRole("link", { name: "DEMO-3" }).click();
  await page.getByRole("tab", { name: "Report" }).click();
  await expect(page.getByRole("link", { name: /Download DEMO-3PDI\.pdf/ })).toBeVisible();
  const verify = await page.getByRole("link", { name: /\/verify\// }).getAttribute("href");
  await page.goto(verify!);
  await expect(page.getByText("genuine")).toBeVisible();
});

test("the expert completes DEMO-2 with a real upload to the file store and a PDF from the worker", async ({ page, request }) => {
  await signIn(page, "expert");
  await page.getByRole("link", { name: "Job DEMO-2" }).click();
  await page.getByRole("button", { name: "Start inspection" }).click();
  await page.getByRole("button", { name: "Capture my location" }).click();
  await expect(page.getByTestId("gps-value")).toBeVisible();
  await page.getByTestId("camera-selfie").setInputFiles(file("selfie.jpg"));
  await expect(page.getByTestId("media-item")).toHaveCount(1);
  await expect(page.getByText(/files 1\/1 sent/)).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByLabel("Chassis number").fill("MA3LOCALTEST000001");
  await page.getByRole("radio", { name: "OK" }).click();
  await page.getByLabel("Odometer").fill("321");
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("radio", { name: "Pay later" }).click();
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Submit inspection" }).click();
  await expect(page.getByText("Completed. Everything arrived")).toBeVisible({ timeout: 60_000 });
  void request;
});
