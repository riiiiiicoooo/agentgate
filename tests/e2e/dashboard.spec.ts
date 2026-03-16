import { test, expect } from "@playwright/test";

test.describe("AgentGate Dashboard", () => {
  test("should load the dashboard", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle(/AgentGate/);
  });

  test("should display agent list", async ({ page }) => {
    await page.goto("/agents");
    const heading = page.getByRole("heading", { name: /agents/i });
    await expect(heading).toBeVisible();
  });

  test("should navigate to policies page", async ({ page }) => {
    await page.goto("/");
    const policiesLink = page.getByRole("link", { name: /policies/i });
    await policiesLink.click();
    await expect(page).toHaveURL(/policies/);
  });

  test("should display audit log", async ({ page }) => {
    await page.goto("/audit");
    await expect(page.getByText(/audit/i)).toBeVisible();
  });

  test("should be keyboard navigable", async ({ page }) => {
    await page.goto("/");
    await page.keyboard.press("Tab");
    const focused = page.locator(":focus");
    await expect(focused).toBeVisible();
  });
});
