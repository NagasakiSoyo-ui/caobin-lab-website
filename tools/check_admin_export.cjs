// Run with Playwright installed (or NODE_PATH pointing to its node_modules).
// A real HTTP stream exercises progress, cancellation and truncated downloads.
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '..');
const payload = Buffer.concat([Buffer.from('PK\x05\x06'), Buffer.alloc(1024 * 1024)]);
let requests = 0;
const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost');
  if (url.pathname === '/admin-export.js') {
    res.setHeader('Content-Type', 'text/javascript');
    return res.end(fs.readFileSync(path.join(root, 'static/admin-export.js')));
  }
  if (url.pathname === '/admin-custom.css') {
    res.setHeader('Content-Type', 'text/css');
    return res.end(fs.readFileSync(path.join(root, 'static/admin-custom.css')));
  }
  if (url.pathname === '/export') {
    requests++;
    const mode = url.searchParams.get('mode');
    if (mode === 'forbidden' || mode === 'failure') {
      res.writeHead(mode === 'forbidden' ? 403 : 500);
      return res.end('Error');
    }
    if (mode === 'login') {
      res.writeHead(302, {Location: '/login/'});
      return res.end();
    }
    if (mode === 'html') {
      res.setHeader('Content-Type', 'text/html');
      return res.end('<p>Not a ZIP</p>');
    }
    const headers = {'Content-Type': 'application/zip', 'Content-Disposition': 'attachment; filename="test.zip"'};
    if (mode !== 'unknown') headers['Content-Length'] = payload.length;
    res.writeHead(200, headers);
    res.write(payload.subarray(0, 262144));
    const timer = setTimeout(() => {
      if (mode === 'truncated') res.destroy();
      else res.end(payload.subarray(262144));
    }, 1800);
    res.on('close', () => clearTimeout(timer));
    return;
  }
  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  const mode = url.searchParams.get('mode') || 'success';
  res.end(`<link rel="stylesheet" href="/admin-custom.css"><a data-export href="/export?mode=${mode}">导出</a><a data-export href="/export?mode=${mode}">导出</a><div id="export-status" role="status"></div><div style="height:2000px"></div><script src="/admin-export.js"></script>`);
});
(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({headless: true, ...(process.env.CHROMIUM_EXECUTABLE ? {executablePath: process.env.CHROMIUM_EXECUTABLE} : {})});
  try {
    const page = await browser.newPage({acceptDownloads: true, viewport: {width: 390, height: 844}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    let downloads = 0;
    page.on('download', () => downloads++);
    for (const mode of ['success', 'unknown', 'cancel', 'truncated', 'forbidden', 'failure', 'html', 'login']) {
      await page.goto(`${base}/?mode=${mode}`);
      const before = requests;
      const downloadCount = downloads;
      const completedDownload = ['success', 'unknown'].includes(mode) ? page.waitForEvent('download') : null;
      await page.locator('[data-export]').first().click();
      const status = page.locator('#export-status');
      if (['success', 'unknown', 'cancel', 'truncated'].includes(mode)) {
        await page.waitForFunction(() => document.querySelector('#export-status').textContent.includes('0.3'));
        if (mode !== 'unknown') assert.match(await status.innerText(), /24%/);
        else assert.doesNotMatch(await status.innerText(), /%/);
        // Playwright normally waits until aria-disabled=false; force a real click while busy.
        await page.locator('[data-export]').last().click({force: true});
        assert.equal(requests, before + 1, 'Repeated clicks must not create duplicate exports');
        await page.evaluate(() => window.scrollTo(0, 1000));
        const bounds = await status.boundingBox();
        assert.ok(bounds.y >= 0 && bounds.y + bounds.height <= 844 && bounds.width <= 390);
        if (mode === 'cancel') await status.getByRole('button', {name: '取消导出'}).click();
      }
      await page.waitForFunction(() => document.querySelector('[data-export]').getAttribute('aria-disabled') === 'false');
      if (mode === 'success' || mode === 'unknown') {
        const download = await completedDownload;
        assert.equal(await download.failure(), null);
        assert.equal(downloads, downloadCount + 1);
        assert.match(await status.innerText(), /已交给浏览器保存/);
      } else {
        assert.equal(downloads, downloadCount, 'Failures must not save a file');
        const expected = {cancel: /已取消/, truncated: /不完整/, forbidden: /没有导出权限/, failure: /500/, html: /不是离线网站 ZIP/, login: /登录已过期/};
        assert.match(await status.innerText(), expected[mode]);
      }
      await status.getByRole('button', {name: '关闭提示'}).click();
      assert.equal(await status.innerText(), '');
      console.log(`PASS ${mode}`);
    }
    assert.deepEqual(errors, []);
  } finally {
    await browser.close();
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => {console.error(error); server.closeAllConnections(); server.close(); process.exitCode = 1;});
