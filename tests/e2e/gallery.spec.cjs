const { test, expect } = require('@playwright/test');
const { openWorkbench } = require('./helpers.cjs');

test('@gallery Open VSX search API is usable from the browser', async ({ page, request, baseURL }) => {
  const runtime = await (await request.get(new URL('runtime.json', baseURL))).json();
  test.skip(runtime.gallery.mode !== 'open-vsx', 'offline baseline has no gallery');

  await openWorkbench(page);
  const result = await page.evaluate(async () => {
    try {
      const response = await fetch('https://open-vsx.org/vscode/gallery/extensionquery', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json;api-version=3.0-preview.1'
        },
        body: JSON.stringify({
          filters: [{ criteria: [{ filterType: 10, value: 'prettier' }],
            pageNumber: 1, pageSize: 5, sortBy: 0, sortOrder: 0 }],
          assetTypes: [],
          flags: 950
        })
      });
      return { ok: response.ok, status: response.status };
    } catch (error) {
      return { ok: false, error: String(error) };
    }
  });
  expect(result, JSON.stringify(result)).toMatchObject({ ok: true });
});
