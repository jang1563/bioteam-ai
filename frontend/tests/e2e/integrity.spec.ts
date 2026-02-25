import { test, expect } from "@playwright/test";
import { mockAllRoutes } from "./fixtures";

test.describe("Data Integrity page", () => {
  test.beforeEach(async ({ page }) => {
    await mockAllRoutes(page);
    await page.goto("/integrity");
  });

  test("should render page heading", async ({ page }) => {
    await expect(page.getByRole("heading", { name: /Data Integrity/i })).toBeVisible();
  });

  test("should display findings table", async ({ page }) => {
    await expect(page.getByRole("table", { name: /integrity findings/i })).toBeVisible();
  });

  test("should show severity badges", async ({ page }) => {
    await expect(page.getByText("warning")).toBeVisible();
    await expect(page.getByText("error")).toBeVisible();
  });

  test("should show Run Audit button", async ({ page }) => {
    await expect(page.getByRole("button", { name: /Run Audit/i })).toBeVisible();
  });

  test("should have severity filter", async ({ page }) => {
    await expect(page.locator("#severity-filter")).toBeVisible();
  });

  test("should have status filter", async ({ page }) => {
    await expect(page.locator("#status-filter")).toBeVisible();
  });

  test("should have search input", async ({ page }) => {
    await expect(page.locator("#integrity-search")).toBeVisible();
  });
});
