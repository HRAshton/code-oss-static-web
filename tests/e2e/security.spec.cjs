const { test, expect } = require('@playwright/test');
const { openWorkbench } = require('./helpers.cjs');

test('runtime security defaults remain fail-closed', async ({ page, request, baseURL }) => {
  const runtimeResponse = await request.get(new URL('runtime.json', baseURL).href);
  expect(runtimeResponse.ok()).toBeTruthy();
  const runtime = await runtimeResponse.json();
  expect(runtime.telemetry).toBe(false);
  expect(runtime.gallery.mode).toBe('open-vsx');
  expect(runtime.webviews.mode).toBe('disabled');

  await openWorkbench(page);
  const bootstrapResponse = await request.get(new URL('static-bootstrap.mjs', baseURL).href);
  const bootstrap = await bootstrapResponse.text();
  expect(bootstrap).toContain('invalid.invalid');

  const csp = await page.locator('meta[http-equiv="Content-Security-Policy"]').getAttribute('content');
  expect(csp).toContain("connect-src 'self'");
  expect(csp).toContain('https://open-vsx.org');
  expect(csp).toContain('https://openvsx.eclipsecontent.org');
  const configuration = JSON.parse(await page.locator('#vscode-workbench-web-configuration').getAttribute('data-settings'));
  expect(configuration.productConfiguration.enableTelemetry).toBe(false);
  expect(configuration.productConfiguration.extensionsGallery.serviceUrl).toBe('https://open-vsx.org/vscode/gallery');
  expect(csp).toContain("object-src 'none'");
});
