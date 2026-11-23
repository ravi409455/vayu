import { expect, test } from "@playwright/test";
import { signIn } from "./api";

test("an admin signs in and sees the forms", async ({ page }) => {
  await signIn(page, "admin");
  await page.goto("/forms");
  await expect(page.getByRole("heading", { name: /^Forms/ })).toBeVisible();
  await expect(page.getByRole("link", { name: "PDI" })).toBeVisible();
});

test("a wrong password is refused with a clear message", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByLabel("Password").fill("nope-nope");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toContainText("Invalid username or password");
});
