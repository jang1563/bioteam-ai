import { test, expect } from "@playwright/test";
import { mockAllRoutes } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await mockAllRoutes(page);
});

test.describe("Agent Detail Sheet", () => {
  test("opens agent detail sheet on agent click", async ({ page }) => {
    await page.goto("/");
    // Click on an agent card to open the detail sheet
    await page.getByText("Research Director").first().click();
    // Sheet should open with agent name
    await expect(page.getByRole("heading", { name: /Research Director/i })).toBeVisible({ timeout: 10_000 });
  });

  test("shows three tabs: Overview, Ask Agent, History", async ({ page }) => {
    await page.goto("/");
    await page.getByText("Research Director").first().click();
    await expect(page.getByRole("tab", { name: /Overview/i })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole("tab", { name: /Ask Agent/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /History/i })).toBeVisible();
  });

  test("Ask Agent tab shows textarea and submit button", async ({ page }) => {
    await page.goto("/");
    await page.getByText("Research Director").first().click();
    await page.getByRole("tab", { name: /Ask Agent/i }).click();
    await expect(page.getByPlaceholder(/Ask this agent/i)).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole("button", { name: /Ask/i })).toBeVisible();
  });

  test("History tab shows execution entries", async ({ page }) => {
    await page.goto("/");
    await page.getByText("Research Director").first().click();
    await page.getByRole("tab", { name: /History/i }).click();
    // Should show "3 executions" from mock data
    await expect(page.getByText(/3 executions/i)).toBeVisible({ timeout: 10_000 });
    // Should show total cost
    await expect(page.getByText(/\$0\.1600/i)).toBeVisible();
  });
});
