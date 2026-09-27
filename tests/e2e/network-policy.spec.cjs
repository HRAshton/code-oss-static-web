const { test, expect } = require('@playwright/test');
const { openWorkbench } = require('./helpers.cjs');

test('clean startup makes no cross-origin HTTP or WebSocket connections', async ({ page, baseURL }) => {
  const expectedOrigin = new URL(baseURL).origin;
  const unexpectedRequests = [];
  const webSockets = [];

  page.on('request', request => {
    const url = request.url();
    if (!/^https?:/.test(url)) return;
    if (new URL(url).origin !== expectedOrigin) unexpectedRequests.push(url);
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
