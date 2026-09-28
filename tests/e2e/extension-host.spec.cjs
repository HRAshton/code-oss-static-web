const { test, expect } = require('@playwright/test');
const { openWorkbench } = require('./helpers.cjs');

async function executeCommandWhenReady(page, command) {
  await expect.poll(async () => {
    return page.evaluate(async commandId => {
      try {
        const { commands } = await import('./out/vs/workbench/workbench.web.main.internal.js');
        await commands.executeCommand(commandId);
        return true;
      } catch {
        return false;
      }
    }, command);
  }, { timeout: 15_000 }).toBe(true);
}

test('@extension repository qualification web extension activates', async ({ page }) => {
  await openWorkbench(page);
  await executeCommandWhenReady(page, 'codeOssStaticWebTest.markReady');

  await expect(
    page.locator('.notification-toast').filter({ hasText: 'Static web test extension activated' }).first()
  ).toBeVisible({ timeout: 15_000 });
});

test('@extension global state persists across workbench reload', async ({ page }) => {
  await openWorkbench(page);
  await executeCommandWhenReady(page, 'codeOssStaticWebTest.markReady');

  await expect(
    page.locator('.notification-toast').filter({ hasText: 'Static web test extension activated' }).first()
  ).toBeVisible({ timeout: 15_000 });

  const navigation = page.waitForNavigation({ waitUntil: 'domcontentloaded' });
  await page.evaluate(() => {
    void import('./out/vs/workbench/workbench.web.main.internal.js').then(({ commands }) => {
      void commands.executeCommand('workbench.action.reloadWindow');
    });
  });
  await navigation;
  await expect(page.locator('.monaco-workbench')).toBeVisible({ timeout: 60_000 });

  await expect.poll(async () => {
    return page.evaluate(async () => {
      try {
        const { commands } = await import('./out/vs/workbench/workbench.web.main.internal.js');
        return await commands.executeCommand('codeOssStaticWebTest.readMarker');
      } catch {
        return 'not-ready';
      }
    });
  }, { timeout: 15_000 }).toBe('ready');
});
