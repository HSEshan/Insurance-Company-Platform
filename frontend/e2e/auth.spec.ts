import { test, expect } from "@playwright/test";

async function clearAuth(page: import("@playwright/test").Page) {
  await page.addInitScript(() => {
    window.localStorage.removeItem("insurance-auth");
  });
}

async function loginViaForm(
  page: import("@playwright/test").Page,
  email: string,
  password: string,
) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page).toHaveURL(/\/dashboard/);
}

test.describe("auth", () => {
  test.beforeEach(async ({ page }) => {
    await clearAuth(page);
  });

  test("customer can sign in with seeded credentials", async ({ page }) => {
    await loginViaForm(page, "customer@insureco.com", "Customer123!");
    await expect(page.getByText(/welcome back/i)).toBeVisible();
    await expect(page.getByText(/customer/i).first()).toBeVisible();
  });

  test("demo button logs in as agent", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /enter as agent/i }).click();
    await expect(page).toHaveURL(/\/dashboard/);
    await expect(page.getByText(/welcome back/i)).toBeVisible();
  });

  test("bad credentials show an error", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Email").fill("customer@insureco.com");
    await page.getByLabel("Password").fill("WrongPassword1!");
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page.getByText(/invalid email or password/i)).toBeVisible();
  });
});
