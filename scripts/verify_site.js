// Smoke-checks the marketing site after scripts/build_docs.py regenerates docs/*.html.
// Requires Playwright -- this repo has no node_modules of its own (zero-dependency static
// site by design), so run with NODE_PATH pointed at a repo that has `playwright` installed,
// e.g. the Kiteconnect app repo:
//
//   NODE_PATH="<path-to-Kiteconnect>\node_modules" node scripts/verify_site.js
//
// Exits non-zero if any check fails.
const { chromium } = require('playwright');
const path = require('path');

const SITE_ROOT = path.resolve(__dirname, '..');
const base = 'file://' + SITE_ROOT;
const failures = [];

function check(desc, cond) {
  console.log(`  ${cond ? 'OK  ' : 'FAIL'} ${desc}`);
  if (!cond) failures.push(desc);
}

(async () => {
  const browser = await chromium.launch();

  console.log('--- Desktop (1280x800) ---');
  {
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    await page.goto(base + '/index.html');
    const nav = await page.evaluate(() => {
      const inner = document.querySelector('.nav-links-inner').getBoundingClientRect();
      const cta = document.querySelector('.nav-cta').getBoundingClientRect();
      return { innerRight: inner.right, ctaLeft: cta.left, ctaVisible: cta.width > 0 };
    });
    check('desktop nav links do not overlap the "Request a license" CTA', nav.innerRight < nav.ctaLeft);
    check('desktop CTA is visible', nav.ctaVisible);

    await page.click('.nav-links a[href="docs/index.html"]');
    await page.waitForLoadState();
    check('Docs nav link opens the docs hub', page.url().endsWith('/docs/index.html'));

    const hubLinks = await page.evaluate(() => document.querySelectorAll('.doc-hub-list a').length);
    check('docs hub lists at least 10 guides', hubLinks >= 10);

    await page.click('.doc-hub-list a[href="strategy-composer.html"]');
    await page.waitForLoadState();
    const doc = await page.evaluate(() => ({
      h1: document.querySelector('.doc-body h1')?.textContent || '',
      hasToc: !!document.querySelector('.doc-toc'),
      overflow: document.body.scrollWidth > window.innerWidth,
    }));
    check('doc page renders its title', doc.h1 === 'Strategy Composer Guide');
    check('long doc page has a table of contents', doc.hasToc);
    check('doc page has no horizontal overflow at 1280px', !doc.overflow);

    await page.close();
  }

  console.log('--- Mobile (390x844) ---');
  {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    await page.goto(base + '/index.html');
    await page.click('#nav-toggle-btn');
    await page.waitForTimeout(300);
    const links = await page.evaluate(() =>
      Array.from(document.querySelectorAll('.nav-links a')).map(a => a.getBoundingClientRect().width > 0)
    );
    check('mobile hamburger menu opens with every link visible', links.length > 0 && links.every(Boolean));

    await page.click('.nav-links a[href="docs/index.html"]');
    await page.waitForLoadState();
    check('mobile Docs link opens the docs hub', page.url().endsWith('/docs/index.html'));

    await page.goto(base + '/docs/composer-strategy-examples.html');
    const overflow = await page.evaluate(() => document.body.scrollWidth > window.innerWidth);
    check('table-heavy doc page has no horizontal overflow at 390px', !overflow);

    await page.goto(base + '/docs/obtaining-credentials.html');
    const hasToc = await page.evaluate(() => !!document.querySelector('.doc-toc'));
    check('short doc page correctly has no table of contents', !hasToc);

    await page.close();
  }

  await browser.close();

  console.log('');
  if (failures.length) {
    console.log(`${failures.length} check(s) failed:`);
    failures.forEach((f) => console.log(`  - ${f}`));
    process.exitCode = 1;
  } else {
    console.log('All checks passed.');
  }
})();
