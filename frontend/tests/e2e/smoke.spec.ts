import { test, expect } from '@playwright/test';

test.describe('Page Load Smoke Tests', () => {
  test('mission control page loads', async ({ page }) => {
    await page.goto('/');
    // Page should render without crashing
    await expect(page).toHaveTitle(/BioTeam/i);
    // Main layout elements should be visible
    await expect(page.locator('body')).toBeVisible();
  });

  test('query page loads', async ({ page }) => {
    await page.goto('/query');
    // Query textarea should be present
    await expect(page.locator('textarea').first()).toBeVisible({ timeout: 10_000 });
  });

  test('lab kb page loads', async ({ page }) => {
    await page.goto('/lab-kb');
    await expect(page.locator('body')).toBeVisible();
  });

  test('settings page loads', async ({ page }) => {
    await page.goto('/settings');
    await expect(page.locator('body')).toBeVisible();
  });
});

test.describe('Navigation', () => {
  test('sidebar navigation between pages', async ({ page }) => {
    await page.goto('/');

    // Navigate to query page via sidebar link
    const queryLink = page.locator('a[href="/query"]').first();
    if (await queryLink.isVisible()) {
      await queryLink.click();
      await expect(page).toHaveURL(/\/query/);
    }

    // Navigate to settings via sidebar link
    const settingsLink = page.locator('a[href="/settings"]').first();
    if (await settingsLink.isVisible()) {
      await settingsLink.click();
      await expect(page).toHaveURL(/\/settings/);
    }
  });

  test('pages render without JS errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (err) => errors.push(err.message));

    await page.goto('/');
    await page.waitForTimeout(2000);

    // Filter out expected errors (e.g., API connection failures in test env)
    const criticalErrors = errors.filter(
      (e) => !e.includes('fetch') && !e.includes('NetworkError') && !e.includes('ERR_CONNECTION_REFUSED')
    );
    expect(criticalErrors).toHaveLength(0);
  });
});
