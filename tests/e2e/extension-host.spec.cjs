const { test, expect } = require('@playwright/test');
const { openWorkbench } = require('./helpers.cjs');

test('@extension repository qualification web extension activates', async ({ page }) => {
  await openWorkbench(page);

  await expect.poll(async () => {
    return page.evaluate(async () => {
      try {
        const { commands } = await import('./out/vs/workbench/workbench.web.main.internal.js');
        await commands.executeCommand('codeOssStaticWebTest.markReady');
        return true;
      } catch {
        return false;
      }
    });
  }, { timeout: 15_000 }).toBe(true);

  await expect(
    page.locator('.notification-toast').filter({ hasText: 'Static web test extension activated' }).first()
  ).toBeVisible({ timeout: 15_000 });
});
