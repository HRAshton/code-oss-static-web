const path = require('path');
const { defineConfig } = require('@playwright/test');

const basePath = process.env.CODE_OSS_STATIC_WEB_BASE_PATH || '/code-oss-web/';
const port = Number(process.env.CODE_OSS_STATIC_WEB_PORT || '4173');
const dist = process.env.CODE_OSS_STATIC_WEB_DIST || path.resolve(__dirname, '../../dist');
const baseURL = `http://127.0.0.1:${port}${basePath}`;
const reportDir = process.env.CODE_OSS_STATIC_WEB_PLAYWRIGHT_REPORT || 'playwright-report';
const resultsDir = process.env.CODE_OSS_STATIC_WEB_PLAYWRIGHT_RESULTS || 'test-results';

module.exports = defineConfig({
  testDir: __dirname,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [['line'], ['html', { outputFolder: reportDir, open: 'never' }]] : 'list',
  outputDir: resultsDir,
  use: {
    baseURL,
    serviceWorkers: 'block',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  webServer: {
    command: `python3 scripts/serve_static.py --directory "${dist}" --base-path "${basePath}" --port ${port}`,
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
    { name: 'firefox', use: { browserName: 'firefox' } },
    { name: 'webkit', use: { browserName: 'webkit' } },
  ],
});
