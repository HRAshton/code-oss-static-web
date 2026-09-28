const { test, expect } = require('@playwright/test');
const { openWorkbench } = require('./helpers.cjs');

test('runtime security defaults remain fail-closed', async ({ page, request, baseURL }) => {
  const runtimeResponse = await request.get(new URL('runtime.json', baseURL).href);
  expect(runtimeResponse.ok()).toBeTruthy();
  const runtime = await runtimeResponse.json();
  expect(runtime.telemetry).toBe(false);
  expect(runtime.gallery.mode).toBe('disabled');
  expect(runtime.webviews.mode).toBe('disabled');

  await openWorkbench(page);
  const bootstrapResponse = await request.get(new URL('static-bootstrap.mjs', baseURL).href);
  const bootstrap = await bootstrapResponse.text();
  expect(bootstrap).toContain('invalid.invalid');

  const csp = await page.locator('meta[http-equiv="Content-Security-Policy"]').getAttribute('content');
  expect(csp).toContain("connect-src 'self'");
  expect(csp).toContain("object-src 'none'");
});
