// Export the offline slides to PDF, and optionally collect visual QA captures.
// Prerequisites: npm ci in web/, Microsoft Edge.
// Usage: node docs/defense/source/export.mjs [--check]
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';
import fs from 'node:fs/promises';
const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '../../..');
const require = createRequire(path.join(root, 'web/package.json'));
const { chromium } = require('@playwright/test');
const out = path.resolve(here, '..');
const qa = path.join(root, 'artifacts/defense-qa');
const browser = await chromium.launch({ channel: 'msedge', headless: true });
try {
  const context = await browser.newContext({ viewport: { width: 1600, height: 900 }, offline: true });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(pathToFileURL(path.join(out, 'LANE-SHIFT-defense.html')).href);
  await page.evaluate(() => document.fonts.ready);
  await page.locator('img').evaluateAll(images => Promise.all(images.map(img => img.decode())));
  const count = await page.locator('#deck > .slide').count();
  if (process.argv.includes('--check')) {
    await fs.mkdir(qa, { recursive: true });
    const report = [];
    for (let i = 1; i <= count; i++) {
      await page.evaluate(index => window.goToSlide(index), i);
      const slide = page.locator('#deck > .slide').nth(i - 1);
      const issues = await slide.evaluate(s => {
        const boundary = s.getBoundingClientRect();
        return [...s.querySelectorAll('h1,h2,h3,p,li,.row-val,.crash,.label,.layer-desc,.source')].flatMap(e => {
          const r = e.getBoundingClientRect();
          return r.width && (r.left < boundary.left - 2 || r.right > boundary.right + 2 || r.top < -2 || r.bottom > innerHeight - 38)
            ? [{ text: e.textContent.slice(0, 90), top: r.top, bottom: r.bottom, width: r.width }]
            : [];
        });
      });
      await page.screenshot({ path: path.join(qa, 'slide-' + String(i).padStart(2, '0') + '.png') });
      report.push({ page: i, title: await slide.getAttribute('data-title'), issues });
    }
    await page.keyboard.press('Home');
    await page.keyboard.press('ArrowRight');
    if (!page.url().endsWith('#2')) throw new Error('Arrow navigation failed');
    await page.keyboard.press('Escape');
    if (!(await page.locator('#overview').isVisible())) throw new Error('Index did not open');
    await page.locator('#overview .index-list button').nth(9).click();
    if (!page.url().endsWith('#10')) throw new Error('Index navigation failed');
    await page.keyboard.press('b');
    await page.keyboard.press('b');
    await page.evaluate(() => document.body.classList.add('low-power'));
    await fs.writeFile(path.join(qa, 'layout-check.json'), JSON.stringify({ errors, slides: report }, null, 2));
    if (errors.length || report.some(r => r.issues.length)) throw new Error('Visual bounds or browser error; inspect artifacts/defense-qa/layout-check.json');
  }
  await page.evaluate(() => window.goToSlide(1));
  await page.pdf({
    path: path.join(out, 'LANE-SHIFT-defense.pdf'),
    width: '1600px', height: '900px',
    preferCSSPageSize: true, printBackground: true,
    displayHeaderFooter: false,
  });
  console.log('Exported ' + count + ' slides to ' + path.join(out, 'LANE-SHIFT-defense.pdf'));
} finally {
  await browser.close();
}
