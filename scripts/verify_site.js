// Smoke-checks the marketing site after scripts/build_docs.py regenerates docs/*.html.
// Requires Playwright -- this repo has no node_modules of its own (zero-dependency static
// site by design), so run with NODE_PATH pointed at a repo that has `playwright` installed,
// e.g. the Kiteconnect app repo:
//
//   NODE_PATH="<path-to-Kiteconnect>\node_modules" node scripts/verify_site.js
//
// Exits non-zero if any check fails.
const { chromium } = require('playwright');
const fs = require('fs');
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

    // Read the raw source, not page.content() -- comments inside <head> round-trip through
    // Playwright's DOM serialization inconsistently, and this is source-level bookkeeping anyway.
    const rawHtml = fs.readFileSync(path.join(SITE_ROOT, 'index.html'), 'utf-8');
    const markerVersion = (rawHtml.match(/content-synced-through:\s*v([\d.]+)/) || [])[1];
    const footerVersion = (rawHtml.match(/id="site-app-version">ThetaPrime v([\d.]+)</) || [])[1];
    check('footer shows an app version', !!footerVersion);
    check('footer version matches the content-synced-through marker (both updated together)', !!markerVersion && markerVersion === footerVersion);

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
      sidebarLinks: document.querySelectorAll('.docs-sidebar .doc-link').length,
      activeLink: document.querySelector('.docs-sidebar .doc-link.active')?.textContent || '',
      hasSearchInput: !!document.querySelector('.docs-sidebar .doc-search-input'),
      hasPrevNext: !!document.querySelector('.doc-prev-next'),
    }));
    check('doc page renders its title', doc.h1 === 'Strategy Composer Guide');
    check('long doc page has a table of contents', doc.hasToc);
    check('doc page has no horizontal overflow at 1280px', !doc.overflow);
    check('desktop sidebar lists every doc', doc.sidebarLinks >= 10);
    check('desktop sidebar highlights the current page', doc.activeLink === 'Strategy Composer Guide');
    check('desktop sidebar has a search box', doc.hasSearchInput);
    check('doc page has prev/next navigation', doc.hasPrevNext);

    // Sticky rails (sidebar, TOC) must scroll internally when their own content is
    // taller than the viewport -- position:sticky alone doesn't provide that, and a
    // rail with no overflow-y traps its own bottom entries out of reach. Regression
    // check for the 2026-08-16 bug: both rails had no max-height/overflow-y at all.
    const railScroll = await page.evaluate(() => {
      const check = (sel) => {
        const el = document.querySelector(sel);
        if (!el) return null;
        const style = getComputedStyle(el);
        return { overflowY: style.overflowY, hasMaxHeight: style.maxHeight !== 'none' };
      };
      return { sidebar: check('.docs-sidebar'), toc: check('.doc-toc') };
    });
    check('desktop sidebar can scroll internally when taller than the viewport',
      railScroll.sidebar.overflowY === 'auto' && railScroll.sidebar.hasMaxHeight);
    check('right-rail TOC can scroll internally when taller than the viewport',
      railScroll.toc.overflowY === 'auto' && railScroll.toc.hasMaxHeight);
    // Search's fetch(search-index.json) can't be exercised under file:// (opaque-origin
    // fetch is blocked) -- it's covered by a manual HTTP-served check when build_docs.py's
    // search logic changes, not by this script. See update-website SKILL.md.

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

    await page.goto(base + '/docs/strategy-composer.html');
    const mobileNav = await page.evaluate(() => ({
      desktopSidebarHidden: getComputedStyle(document.querySelector('.docs-sidebar')).display === 'none',
      mobileDetailsVisible: getComputedStyle(document.querySelector('.docs-sidebar-mobile')).display !== 'none',
      collapsedByDefault: !document.querySelector('.docs-sidebar-mobile').open,
    }));
    check('desktop sidebar is hidden on mobile', mobileNav.desktopSidebarHidden);
    check('mobile docs nav (collapsible) is visible', mobileNav.mobileDetailsVisible);
    check('mobile docs nav is collapsed by default', mobileNav.collapsedByDefault);
    await page.click('.docs-sidebar-mobile summary');
    const opened = await page.evaluate(() =>
      document.querySelectorAll('.docs-sidebar-mobile .doc-link').length >= 10);
    check('mobile docs nav expands to list every doc', opened);
    const overflowAfterOpen = await page.evaluate(() => document.body.scrollWidth > window.innerWidth);
    check('expanded mobile docs nav has no horizontal overflow', !overflowAfterOpen);

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
