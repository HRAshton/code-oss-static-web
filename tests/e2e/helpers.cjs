const { expect } = require('@playwright/test');

async function openWorkbench(page) {
  const pageErrors = [];
  const consoleErrors = [];
  const failedRequests = [];
  let signalPageError;
  const firstPageError = new Promise(resolve => {
    signalPageError = resolve;
  });

  page.on('pageerror', error => {
    const text = String(error && error.stack || error);
    pageErrors.push(text);
    signalPageError(text);
  });
  page.on('console', message => {
    if (message.type() === 'error') {
      consoleErrors.push(message.text());
    }
  });
  page.on('requestfailed', request => {
    const failure = request.failure();
    failedRequests.push(
      `${request.method()} ${request.url()} ${failure ? failure.errorText : 'failed'}`
    );
  });

  const response = await page.goto('./', { waitUntil: 'domcontentloaded' });
  expect(response && response.ok(), 'index.html should load successfully').toBeTruthy();

  const readyResult = expect(page.locator('.monaco-workbench'))
    .toBeVisible({ timeout: 60_000 })
    .then(() => ({ kind: 'ready' }))
    .catch(error => ({ kind: 'timeout', error }));
  const pageErrorResult = firstPageError.then(error => ({ kind: 'pageerror', error }));
  const result = await Promise.race([readyResult, pageErrorResult]);

  if (result.kind === 'pageerror') {
    throw new Error(`page error before workbench became ready:\n${result.error}`);
  }

  if (result.kind === 'timeout') {
    let bodyText = '';
    try {
      bodyText = (await page.locator('body').innerText()).slice(0, 1000);
    } catch {
      // Best-effort diagnostics only.
    }

    throw new Error([
      result.error && result.error.message || String(result.error),
      `page errors: ${JSON.stringify(pageErrors)}`,
      `console errors: ${JSON.stringify(consoleErrors)}`,
      `failed requests: ${JSON.stringify(failedRequests)}`,
      `body text: ${JSON.stringify(bodyText)}`,
    ].join('\n'));
  }

  await page.waitForTimeout(500);
  expect(pageErrors).toEqual([]);
  return { pageErrors, consoleErrors, failedRequests };
}

async function openCommandPalette(page) {
  await page.keyboard.press('Control+Shift+P');
  const input = page.locator('.quick-input-widget input').first();
  await expect(input).toBeVisible();
  return input;
}

module.exports = { openWorkbench, openCommandPalette };
