// Developer regression check against a populated live site or exported offline site.
const assert = require('node:assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const base = process.argv[2];
  if (!base) throw new Error('Usage: node tools/check_resource_navigation.cjs <site-root-url>');
  const browser = await chromium.launch(process.env.CHROMIUM_EXECUTABLE
    ? {executablePath: process.env.CHROMIUM_EXECUTABLE} : {});
  try {
    const context = await browser.newContext();
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const open = () => page.goto(new URL('resources.html', base).href);
    const currentURL = () => page.evaluate(() => location.href);
    const search = page.locator('#resource-search');
    const pagination = page.locator('#resource-pagination');
    const currentPage = () => pagination.locator('select').inputValue();
    await open();
    await search.pressSequentially('肺炎');
    // Do not blur/submit first: the initial physical click must work.
    await pagination.getByRole('button', {name: '下一页', exact: true}).click();
    assert.equal(await currentPage(), '2');
    await page.reload();
    assert.equal(await currentPage(), '2');
    await page.goBack();
    assert.equal(await currentPage(), '1');
    await page.goForward();
    assert.equal(await currentPage(), '2');
    await open();
    await search.pressSequentially('肺炎');
    await pagination.locator('select').click();
    await pagination.locator('select').selectOption('3');
    assert.equal(await currentPage(), '3');

    await open();
    await search.pressSequentially('流感');
    await search.press('Backspace');
    await search.press('Backspace');
    await page.locator('[data-resource-category="视频课程"]').click();
    const categoryURL = await currentURL();
    await search.pressSequentially('流感');
    await page.goBack();
    await page.waitForURL(categoryURL);
    assert.equal(await currentURL(), categoryURL);
    assert.equal(await page.locator('#resource-kind').inputValue(), '视频课程');
    assert.equal(await search.inputValue(), '');

    await open();
    const before = await page.evaluate(() => history.length);
    await search.pressSequentially('influenza');
    assert.equal(await page.evaluate(() => history.length), before + 1);
    await page.goBack();
    assert.equal(await search.inputValue(), '');
    await page.goForward();
    assert.equal(await search.inputValue(), 'influenza');

    await open();
    const startingURL = await currentURL();
    const ime = await context.newCDPSession(page);
    await search.focus();
    await ime.send('Input.imeSetComposition', {text: 'liugan', selectionStart: 6, selectionEnd: 6});
    assert.equal(await currentURL(), startingURL);
    await ime.send('Input.insertText', {text: '流感'});
    assert.equal(new URL(await currentURL()).searchParams.get('q'), '流感');
    await page.goBack();
    assert.equal(await page.locator('#resource-overview').isVisible(), true);
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({base, firstPaginationClick: 'pass', pageSelect: 'pass',
      refreshAndHistory: 'pass', categorySearchHistory: 'pass', typingHistory: 'pass',
      chromiumCompositionEvents: 'pass', pageErrors: errors}, null, 2));
  } finally {
    await browser.close();
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
