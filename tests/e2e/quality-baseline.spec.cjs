const fs = require('fs');
const path = require('path');
const { test, expect } = require('@playwright/test');

const repoRoot = path.resolve(__dirname, '../..');
const baselinePath = path.join(repoRoot, 'config', 'quality-baseline.json');
const baseline = JSON.parse(fs.readFileSync(baselinePath, 'utf8'));

function median(values) {
  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  if (sorted.length % 2) return sorted[middle];
  return (sorted[middle - 1] + sorted[middle]) / 2;
}

function fileSizes(root) {
  let distributionBytes = 0;
  let javascriptBytes = 0;
  const pending = [root];
  while (pending.length) {
    const directory = pending.pop();
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const fullPath = path.join(directory, entry.name);
      if (entry.isDirectory()) {
        pending.push(fullPath);
        continue;
      }
      if (!entry.isFile()) continue;
      const size = fs.statSync(fullPath).size;
      distributionBytes += size;
      if (['.js', '.mjs', '.cjs'].includes(path.extname(entry.name))) javascriptBytes += size;
    }
  }
  return { distributionBytes, javascriptBytes };
}

function metricLimit(spec) {
  return Math.ceil(spec.baseline * (1 + spec.relativeTolerance) + spec.absoluteTolerance);
}

function expectWithinBaseline(name, observed) {
  const spec = baseline.metrics[name];
  expect(spec, 'quality baseline should define ' + name).toBeTruthy();
  expect(spec.baseline, 'quality baseline should set ' + name).not.toBeNull();
  const limit = metricLimit(spec);
  expect(
    observed,
    name + ' regression: observed=' + observed + ', baseline=' + spec.baseline + ', ' +
      'relativeTolerance=' + spec.relativeTolerance + ', absoluteTolerance=' +
      spec.absoluteTolerance + ', limit=' + limit
  ).toBeLessThanOrEqual(limit);
}

function observePage(page, expectedOrigin) {
  const pageErrors = [];
  const consoleErrors = [];
  const failedRequests = [];
  const responses = [];

  page.on('pageerror', error => pageErrors.push(String(error && error.stack || error)));
  page.on('console', message => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  page.on('requestfailed', request => {
    const failure = request.failure();
    failedRequests.push(
      request.method() + ' ' + request.url() + ' ' + (failure ? failure.errorText : 'failed')
    );
  });
  page.on('response', response => {
    const url = response.url();
    if (/^https?:/.test(url) && new URL(url).origin === expectedOrigin) responses.push(response);
  });

  return { pageErrors, consoleErrors, failedRequests, responses };
}

async function transferBytes(responses) {
  let total = 0;
  for (const response of responses) {
    const value = await response.headerValue('content-length');
    if (value === null) continue;
    const length = Number(value);
    if (Number.isFinite(length) && length >= 0) total += length;
  }
  return total;
}

async function boot(page, baseURL) {
  const expectedOrigin = new URL(baseURL).origin;
  const observation = observePage(page, expectedOrigin);
  const started = performance.now();
  const response = await page.goto(baseURL, { waitUntil: 'domcontentloaded' });
  expect(response && response.ok(), 'index.html should load successfully').toBeTruthy();
  await expect(page.locator('.monaco-workbench')).toBeVisible({ timeout: 60_000 });
  const readyMs = performance.now() - started;
  const readyResponses = observation.responses.slice();
  return { readyMs, readyResponses, ...observation };
}

async function editorReady(page, navigationStarted) {
  await page.evaluate(async () => {
    const { commands } = await import('./out/vs/workbench/workbench.web.main.internal.js');
    await commands.executeCommand('workbench.action.files.newUntitledFile');
  });
  await expect(page.locator('.monaco-editor:visible').last()).toBeVisible();
  return performance.now() - navigationStarted;
}

async function focusSmoke(page) {
  const before = await page.evaluateHandle(() => document.activeElement);
  await page.keyboard.press('F6');
  await page.waitForTimeout(100);
  const result = await page.evaluate(previous => {
    const element = document.activeElement;
    if (!element) return null;
    const labelledBy = element.getAttribute('aria-labelledby');
    const labelledByText = labelledBy
      ? labelledBy
          .split(/\s+/)
          .map(id => document.getElementById(id)?.textContent || '')
          .join(' ')
          .trim()
      : '';
    const name = (
      element.getAttribute('aria-label') ||
      labelledByText ||
      element.getAttribute('title') ||
      element.textContent ||
      ''
    ).trim();
    return {
      changed: element !== previous,
      name,
      ariaHidden: element.getAttribute('aria-hidden'),
      disabled: element.hasAttribute('disabled') || element.getAttribute('aria-disabled') === 'true',
      tagName: element.tagName,
    };
  }, before);
  await before.dispose();

  expect(result, 'F6 should leave an active element').not.toBeNull();
  expect(result.changed, 'F6 should move focus to another workbench part').toBe(true);
  expect(result.ariaHidden, 'focused element must not be aria-hidden').not.toBe('true');
  expect(result.disabled, 'focused element must not be disabled').toBe(false);
  expect(result.name, 'focused ' + result.tagName + ' should have an accessible name').not.toBe('');
}

test('@quality performance and accessibility baseline', async ({ browser, baseURL }) => {
  test.skip(!baseURL, 'quality baseline requires the configured static server');
  const samples = baseline.sampling.samples;
  const settleMs = baseline.sampling.settleMs;
  expect(samples % 2, 'quality sample count should be odd so the median is an observed sample').toBe(1);

  const coldBootMs = [];
  const warmBootMs = [];
  const editorReadyMs = [];
  const staticTransferBytes = [];
  const pageErrors = [];
  const consoleErrors = [];
  const failedRequests = [];

  for (let index = 0; index < samples; index += 1) {
    const context = await browser.newContext({ serviceWorkers: 'block' });
    try {
      const coldPage = await context.newPage();
      const cold = await boot(coldPage, baseURL);
      coldBootMs.push(cold.readyMs);
      staticTransferBytes.push(await transferBytes(cold.readyResponses));
      await coldPage.waitForTimeout(settleMs);
      pageErrors.push(...cold.pageErrors);
      consoleErrors.push(...cold.consoleErrors);
      failedRequests.push(...cold.failedRequests);
      await coldPage.close();

      const warmPage = await context.newPage();
      const navigationStarted = performance.now();
      const warm = await boot(warmPage, baseURL);
      warmBootMs.push(warm.readyMs);
      editorReadyMs.push(await editorReady(warmPage, navigationStarted));
      if (index === 0) await focusSmoke(warmPage);
      await warmPage.waitForTimeout(settleMs);
      pageErrors.push(...warm.pageErrors);
      consoleErrors.push(...warm.consoleErrors);
      failedRequests.push(...warm.failedRequests);
      await warmPage.close();
    } finally {
      await context.close();
    }
  }

  const dist = process.env.CODE_OSS_STATIC_WEB_DIST || path.join(repoRoot, 'dist');
  const staticSizes = fileSizes(dist);
  const metrics = {
    coldBootMs: Math.round(median(coldBootMs)),
    warmBootMs: Math.round(median(warmBootMs)),
    editorReadyMs: Math.round(median(editorReadyMs)),
    staticTransferBytes: Math.round(median(staticTransferBytes)),
    distributionBytes: staticSizes.distributionBytes,
    javascriptBytes: staticSizes.javascriptBytes,
    failedRequests: failedRequests.length,
    pageErrors: pageErrors.length,
    consoleErrors: new Set(consoleErrors).size,
  };

  const report = {
    schemaVersion: 1,
    browser: 'chromium',
    sampling: baseline.sampling,
    samples: { coldBootMs, warmBootMs, editorReadyMs, staticTransferBytes },
    metrics,
    diagnostics: {
      failedRequests,
      pageErrors,
      consoleErrorOccurrences: consoleErrors.length,
      consoleErrors,
    },
  };
  const reportPath = process.env.CODE_OSS_STATIC_WEB_QUALITY_REPORT;
  if (reportPath) {
    fs.mkdirSync(path.dirname(reportPath), { recursive: true });
    fs.writeFileSync(reportPath, JSON.stringify(report, null, 2) + '\n');
  }
  console.log('[quality] metrics=' + JSON.stringify(metrics));

  for (const [name, observed] of Object.entries(metrics)) expectWithinBaseline(name, observed);
});
