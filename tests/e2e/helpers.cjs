const { expect } = require('@playwright/test');

async function openWorkbench(page) {
  const pageErrors = [];
  page.on('pageerror', error => pageErrors.push(String(error && error.stack || error)));

  const response = await page.goto('./', { waitUntil: 'domcontentloaded' });
  expect(response && response.ok(), 'index.html should load successfully').toBeTruthy();
  await expect(page.locator('.monaco-workbench')).toBeVisible({ timeout: 60_000 });
  await page.waitForTimeout(500);
  expect(pageErrors).toEqual([]);
  return { pageErrors };
}

async function openCommandPalette(page) {
  await page.keyboard.press('F1');
  const input = page.locator('.quick-input-widget input').first();
  await expect(input).toBeVisible();
  return input;
}

module.exports = { openWorkbench, openCommandPalette };
