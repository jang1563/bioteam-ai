import { test, expect } from "@playwright/test";
import { mockAllRoutes } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await mockAllRoutes(page);
});

test.describe("Navigation & Layout", () => {
  test("sidebar shows navigation links", async ({ page }) => {
    await page.goto("/");
    const nav = page.locator('nav[aria-label="Main navigation"]');
    await expect(nav).toBeVisible();

    // All nav links should be present
    await expect(page.locator('a[href="/"]').first()).toBeVisible();
    await expect(page.locator('a[href="/query"]').first()).toBeVisible();
    await expect(page.locator('a[href="/digest"]').first()).toBeVisible();
    await expect(page.locator('a[href="/lab-kb"]').first()).toBeVisible();
    await expect(page.locator('a[href="/settings"]').first()).toBeVisible();
  });

  test("navigate to Direct Query page", async ({ page }) => {
    await page.goto("/");
    await page.locator('a[href="/query"]').first().click();
    await expect(page).toHaveURL(/\/query/);
    await expect(page.getByRole("heading", { name: /Direct Query/i })).toBeVisible();
  });

  test("navigate to Digest page", async ({ page }) => {
    await page.goto("/");
    await page.locator('a[href="/digest"]').first().click();
    await expect(page).toHaveURL(/\/digest/);
    await expect(page.getByRole("heading", { name: /Research Digest/i })).toBeVisible();
  });

  test("navigate to Lab KB page", async ({ page }) => {
    await page.goto("/");
    await page.locator('a[href="/lab-kb"]').first().click();
    await expect(page).toHaveURL(/\/lab-kb/);
    await expect(page.getByRole("heading", { name: /Lab Knowledge Base/i })).toBeVisible();
  });

  test("navigate to Settings page", async ({ page }) => {
    await page.goto("/");
    await page.locator('a[href="/settings"]').first().click();
    await expect(page).toHaveURL(/\/settings/);
    await expect(page.getByRole("heading", { name: /Settings/i })).toBeVisible();
  });

  test("pages render without JS errors", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(err.message));

    await page.goto("/");
    await page.waitForTimeout(2000);

    // Filter out expected errors (API connection failures in test env)
    const criticalErrors = errors.filter(
      (e) =>
        !e.includes("fetch") &&
        !e.includes("NetworkError") &&
        !e.includes("ERR_CONNECTION_REFUSED"),
    );
    expect(criticalErrors).toHaveLength(0);
  });

  test("app title is set correctly", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle(/BioTeam/i);
  });

  test("sidebar has proper aria labels", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator('aside[aria-label="Sidebar"]')).toBeVisible();
    await expect(page.locator('nav[aria-label="Main navigation"]')).toBeVisible();
  });
});
