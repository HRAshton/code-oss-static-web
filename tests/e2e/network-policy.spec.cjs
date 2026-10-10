const { test, expect } = require('@playwright/test');
const { openWorkbench } = require('./helpers.cjs');

test('startup permits only reviewed gallery origins and no WebSockets', async ({ page, request, baseURL }) => {
  const runtime = await (await request.get(new URL('runtime.json', baseURL).href)).json();
  const allowedOrigins = new Set([new URL(baseURL).origin]);
  if (runtime.gallery.mode === 'open-vsx') {
    allowedOrigins.add('https://open-vsx.org');
    allowedOrigins.add('https://openvsx.eclipsecontent.org');
  }
  const unexpectedRequests = [];
  const webSockets = [];

  page.on('request', request => {
    const url = request.url();
    if (!/^https?:/.test(url)) return;
    if (!allowedOrigins.has(new URL(url).origin)) unexpectedRequests.push(url);
  });
  page.on('websocket', socket => webSockets.push(socket.url()));

  await openWorkbench(page);
  await page.waitForTimeout(1500);

  expect(unexpectedRequests).toEqual([]);
  expect(webSockets).toEqual([]);
});

test('default CSP blocks an arbitrary cross-origin fetch', async ({ page }) => {
  await openWorkbench(page);
  const outcome = await page.evaluate(async () => {
    try {
      await fetch('https://example.invalid/code-oss-static-web-policy-probe');
      return 'allowed';
    } catch {
      return 'blocked';
    }
  });
  expect(outcome).toBe('blocked');
});
