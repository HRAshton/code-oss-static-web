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

async function executeCommand(page, command) {
  return page.evaluate(async commandId => {
    const { commands } = await import('./out/vs/workbench/workbench.web.main.internal.js');
    return commands.executeCommand(commandId);
  }, command);
}

async function reloadWorkbench(page) {
  const navigation = page.waitForNavigation({ waitUntil: 'domcontentloaded' });
  await page.evaluate(() => {
    void import('./out/vs/workbench/workbench.web.main.internal.js').then(({ commands }) => {
      void commands.executeCommand('workbench.action.reloadWindow');
    });
  });
  await navigation;
  await expect(page.locator('.monaco-workbench')).toBeVisible({ timeout: 60_000 });
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

  await reloadWorkbench(page);

  await expect.poll(async () => {
    try {
      return await executeCommand(page, 'codeOssStaticWebTest.readMarker');
    } catch {
      return 'not-ready';
    }
  }, { timeout: 15_000 }).toBe('ready');
});

test('@extension browser filesystem persists across workbench reload', async ({ page }) => {
  await openWorkbench(page);
  await executeCommandWhenReady(page, 'codeOssStaticWebTest.writeStorageFile');
  await expect.poll(
    () => executeCommand(page, 'codeOssStaticWebTest.readStorageFile'),
    { timeout: 15_000 }
  ).toBe('browser-filesystem-ready');

  await reloadWorkbench(page);

  await expect.poll(async () => {
    try {
      return await executeCommand(page, 'codeOssStaticWebTest.readStorageFile');
    } catch {
      return 'not-ready';
    }
  }, { timeout: 15_000 }).toBe('browser-filesystem-ready');
});

test('@extension JavaScript language service returns completions', async ({ page }) => {
  await openWorkbench(page);
  await executeCommandWhenReady(page, 'codeOssStaticWebTest.probeLanguageService');

  await expect.poll(async () => {
    try {
      return await executeCommand(page, 'codeOssStaticWebTest.probeLanguageService');
    } catch {
      return 0;
    }
  }, { timeout: 30_000 }).toBeGreaterThan(0);
});
