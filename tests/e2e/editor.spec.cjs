const { test, expect } = require('@playwright/test');
const { openWorkbench, openCommandPalette } = require('./helpers.cjs');

test('editor accepts input and command palette works', async ({ page }) => {
  await openWorkbench(page);

  const newFileInput = await openCommandPalette(page);
  await newFileInput.fill('New Untitled Text File');
  const newFileCommand = page
    .locator('.quick-input-list .monaco-list-row')
    .filter({ hasText: 'New Untitled Text File' })
    .first();
  await expect(newFileCommand).toBeVisible();
  await newFileCommand.click();

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
