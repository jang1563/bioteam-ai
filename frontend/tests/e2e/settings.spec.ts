import { test, expect } from "@playwright/test";
import { mockAllRoutes } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await mockAllRoutes(page);
});

test.describe("Settings Page", () => {
  test("renders heading", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: /Settings/i })).toBeVisible();
  });

  test("shows API key section", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByText(/API Key/i).first()).toBeVisible();
    // Password input should be present
    await expect(page.locator('input[type="password"]')).toBeVisible({ timeout: 10_000 });
  });

  test("shows backend status", async ({ page }) => {
    await page.goto("/settings");
    // Should show healthy status
    await expect(page.getByText(/healthy/i).first()).toBeVisible({ timeout: 10_000 });
    // Version — may appear in both header and settings card
    await expect(page.getByText("0.6.0").first()).toBeVisible();
  });

  test("shows cold start section", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByText(/Cold Start/i).first()).toBeVisible();
    // Initialized badge
    await expect(page.getByText(/Initialized/i).first()).toBeVisible({ timeout: 10_000 });
  });

  test("shows dependency statuses", async ({ page }) => {
    await page.goto("/settings");
    // ChromaDB and SQLite deps should appear
    await expect(page.getByText(/chromadb/i)).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/sqlite/i)).toBeVisible();
  });

  test("API key can be typed", async ({ page }) => {
    await page.goto("/settings");
    const input = page.locator('input[type="password"]');
    await input.waitFor({ timeout: 10_000 });
    await input.fill("test-api-key-123");
    await expect(input).toHaveValue("test-api-key-123");
  });

  test("save button exists for API key", async ({ page }) => {
    await page.goto("/settings");
    const saveBtn = page.getByRole("button", { name: /Save/i }).first();
    await expect(saveBtn).toBeVisible({ timeout: 10_000 });
  });
});
