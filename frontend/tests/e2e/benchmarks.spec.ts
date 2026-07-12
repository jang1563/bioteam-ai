import { test, expect } from "@playwright/test";
import { mockAllRoutes } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await mockAllRoutes(page);
});

test.describe("Benchmarks Page", () => {
  test("page loads with heading", async ({ page }) => {
    await page.goto("/benchmarks");
    await expect(page.getByRole("heading", { name: /Benchmarks/i })).toBeVisible();
  });

  test("shows summary cards", async ({ page }) => {
    await page.goto("/benchmarks");
    await expect(page.getByText("Total Runs")).toBeVisible();
    await expect(page.getByText("Latest BioAgent Score")).toBeVisible();
    await expect(page.getByText("Latest Concern Recall")).toBeVisible();
    await expect(page.getByText("Active Run")).toBeVisible();
  });

  test("tabs are visible", async ({ page }) => {
    await page.goto("/benchmarks");
    await expect(page.getByRole("tab", { name: /Results/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /Datasets/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /Trends/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /Compare/i })).toBeVisible();
  });

  test("results tab shows table with data", async ({ page }) => {
    await page.goto("/benchmarks");
    // Results tab is default
    await expect(page.getByText("cancer_pathway")).toBeVisible();
    await expect(page.getByText("W9", { exact: true }).first()).toBeVisible();
  });

  test("w8 results appear in results table", async ({ page }) => {
    await page.goto("/benchmarks");
    await expect(page.getByText("pilot")).toBeVisible();
    await expect(page.getByText("W8", { exact: true }).first()).toBeVisible();
  });

  test("datasets tab shows dataset cards", async ({ page }) => {
    await page.goto("/benchmarks");
    await page.getByRole("tab", { name: /Datasets/i }).click();
    await expect(page.getByText("TCGA BRCA Pathway Enrichment")).toBeVisible();
    await expect(page.getByText("query-only")).toBeVisible();
  });

  test("filter chips work in results tab", async ({ page }) => {
    await page.goto("/benchmarks");
    // Click W9 filter
    await page.getByRole("button", { name: "W9 Bioinfo" }).click();
    await expect(page.getByText("cancer_pathway")).toBeVisible();
    // Click W8 filter
    await page.getByRole("button", { name: "W8 Peer Review" }).click();
    await expect(page.getByText("pilot")).toBeVisible();
  });

  test("sidebar has benchmarks link", async ({ page }) => {
    await page.goto("/");
    const link = page.locator('a[href="/benchmarks"]').first();
    await expect(link).toBeVisible();
  });

  test("navigate to benchmarks from sidebar", async ({ page }) => {
    await page.goto("/");
    await page.locator('a[href="/benchmarks"]').first().click();
    await expect(page).toHaveURL(/\/benchmarks/);
    await expect(page.getByRole("heading", { name: /Benchmarks/i })).toBeVisible();
  });
});
