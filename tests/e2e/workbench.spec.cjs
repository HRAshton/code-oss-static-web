const { test, expect } = require('@playwright/test');
const { openWorkbench } = require('./helpers.cjs');

test('workspace trust remains enabled in the packaged workbench', async ({ page }) => {
  await openWorkbench(page);
  const configuration = await page.locator('#vscode-workbench-web-configuration').getAttribute('data-settings');
  expect(configuration).toBeTruthy();
  expect(JSON.parse(configuration).enableWorkspaceTrust).toBe(true);
});

test('keyboard shortcut opens and closes the command palette', async ({ page }) => {
  await openWorkbench(page);
  await page.keyboard.press('F1');
  const palette = page.locator('.quick-input-widget');
  await expect(palette).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(palette).toBeHidden();
});

test('settings UI opens through the workbench command', async ({ page }) => {
  await openWorkbench(page);
  await page.evaluate(async () => {
    const { commands } = await import('./out/vs/workbench/workbench.web.main.internal.js');
    await commands.executeCommand('workbench.action.openSettings');
  });
  await expect(page.locator('.settings-editor:visible')).toBeVisible();
});

test('static mode does not advertise an offline service-worker cache', async ({ page }) => {
  await openWorkbench(page);
  const registrations = await page.evaluate(async () => {
    if (!('serviceWorker' in navigator)) return [];
    return (await navigator.serviceWorker.getRegistrations()).map(registration => registration.scope);
  });
  expect(registrations).toEqual([]);
});
