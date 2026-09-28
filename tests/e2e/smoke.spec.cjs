const { test, expect } = require('@playwright/test');
const { openWorkbench } = require('./helpers.cjs');

test('packaged workbench boots from static hosting', async ({ page }) => {
  await openWorkbench(page);

  const configuration = await page.locator('#vscode-workbench-web-configuration').getAttribute('data-settings');
  expect(configuration).toBeTruthy();
  const parsed = JSON.parse(configuration);
  expect(parsed.enableWorkspaceTrust).toBe(true);
  expect(parsed.productConfiguration.enableTelemetry).toBe(false);
});

test('required static assets resolve beneath the configured base path', async ({ page, request, baseURL }) => {
  await openWorkbench(page);
  const origin = new URL(baseURL).origin;
  for (const relative of ['runtime.json', 'extensions.json', 'out/nls.messages.js']) {
    const result = await request.get(new URL(relative, baseURL).href);
    expect(result.ok(), relative).toBeTruthy();
    expect(new URL(result.url()).origin).toBe(origin);
  }
});
