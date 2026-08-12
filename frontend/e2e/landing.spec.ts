import { test, expect } from "@playwright/test";

/** Clear persisted auth so each spec starts anonymous. */
async function clearAuth(page: import("@playwright/test").Page) {
  await page.addInitScript(() => {
    window.localStorage.removeItem("insurance-auth");
  });
}

test.describe("landing", () => {
  test.beforeEach(async ({ page }) => {
    await clearAuth(page);
  });

  test("loads hero and demo login section", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", {
        name: /full-stack insurance management platform/i,
      }),
    ).toBeVisible();
    await expect(page.getByText(/one-click demo logins/i)).toBeVisible();
    await expect(
      page.getByRole("button", { name: /enter as customer/i }),
    ).toBeVisible();
  });

  test("chat launcher is available for visitors", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("button", { name: /open chat|chat/i })).toBeVisible();
  });
});
