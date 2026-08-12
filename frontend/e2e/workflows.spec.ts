import { test, expect } from "@playwright/test";

async function clearAuth(page: import("@playwright/test").Page) {
  await page.addInitScript(() => {
    window.localStorage.removeItem("insurance-auth");
  });
}

async function demoLogin(
  page: import("@playwright/test").Page,
  roleLabel: RegExp,
) {
  await page.goto("/");
  await page.getByRole("button", { name: roleLabel }).click();
  await expect(page).toHaveURL(/\/dashboard/);
}

test.describe("customer smoke", () => {
  test.beforeEach(async ({ page }) => {
    await clearAuth(page);
  });

  test("customer can open policies and claims", async ({ page }) => {
    await demoLogin(page, /enter as customer/i);

    await page.getByRole("link", { name: /^policies$/i }).click();
    await expect(page).toHaveURL(/\/policies/);
    await expect(page.getByRole("heading", { name: /polic/i })).toBeVisible();

    await page.getByRole("link", { name: /^claims$/i }).click();
    await expect(page).toHaveURL(/\/claims/);
  });

  test("chat opens on customer dashboard", async ({ page }) => {
    await demoLogin(page, /enter as customer/i);
    const chatBtn = page.getByRole("button", { name: /open chat|chat/i });
    await expect(chatBtn).toBeVisible();
    await chatBtn.click();
    await expect(page.getByText(/insureco chat/i)).toBeVisible();
    await expect(page.getByText(/virtual assistant/i)).toBeVisible();
  });
});

test.describe("staff smoke", () => {
  test.beforeEach(async ({ page }) => {
    await clearAuth(page);
  });

  test("agent can open customers and quotes", async ({ page }) => {
    await demoLogin(page, /enter as agent/i);

    await page.getByRole("link", { name: /^customers$/i }).click();
    await expect(page).toHaveURL(/\/customers/);

    await page.getByRole("link", { name: /^quotes$/i }).click();
    await expect(page).toHaveURL(/\/quotes/);
  });

  test("manager can open reports and audit", async ({ page }) => {
    await demoLogin(page, /enter as manager/i);

    await page.getByRole("link", { name: /^reports$/i }).click();
    await expect(page).toHaveURL(/\/reports/);

    await page.getByRole("link", { name: /audit log/i }).click();
    await expect(page).toHaveURL(/\/audit/);
  });
});
