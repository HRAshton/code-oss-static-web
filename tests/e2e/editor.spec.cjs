const { test, expect } = require('@playwright/test');
const { openWorkbench, openCommandPalette } = require('./helpers.cjs');

test('editor accepts input and command palette works', async ({ page }) => {
  await openWorkbench(page);

  await page.evaluate(async () => {
    const { commands } = await import('./out/vs/workbench/workbench.web.main.internal.js');
    await commands.executeCommand('workbench.action.files.newUntitledFile');
  });

  const editorInput = page.locator('.monaco-editor textarea.inputarea').last();
  await expect(editorInput).toBeAttached();
  await editorInput.focus();
  await page.keyboard.type('static-code-oss-qualification');
  await expect(page.locator('.view-lines').last()).toContainText('static-code-oss-qualification');

  const quickInput = await openCommandPalette(page);
  await quickInput.fill('Preferences: Open Settings');
  await expect(page.locator('.quick-input-widget')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.locator('.quick-input-widget')).toBeHidden();
});
