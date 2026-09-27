const { test, expect } = require('@playwright/test');
const { openWorkbench, openCommandPalette } = require('./helpers.cjs');

test('@extension repository qualification web extension activates', async ({ page }) => {
  await openWorkbench(page);

  const input = await openCommandPalette(page);
  await input.fill('Static Web Test: Mark Ready');
  const command = page.locator('.quick-input-list .monaco-list-row').filter({ hasText: 'Static Web Test: Mark Ready' }).first();
  await expect(command).toBeVisible();
  await command.click();

  await expect(page.locator('.notification-toast').filter({ hasText: 'Static web test extension activated' }).first())
    .toBeVisible({ timeout: 15_000 });
});
