// Visual Audit — Round 2: focused close-ups for shape/animation/pixel evaluation
import { chromium } from '@playwright/test';
import { mkdirSync } from 'node:fs';

const OUT = '/tmp/abs-cj/visual_audit_2';
mkdirSync(OUT, { recursive: true });

const BACKEND = process.env.ABS_BACKEND || 'http://localhost:8000';
const LANDING = process.env.ABS_LANDING || 'http://localhost:3000';

function ts() { return new Date().toISOString().slice(11, 19); }
function log(msg) { console.log(`[${ts()}] ${msg}`); }
async function pause(page, ms, reason) { log(`⏸ ${ms}ms — ${reason}`); await page.waitForTimeout(ms); }

(async () => {
  log('🎬 VISUAL AUDIT — Round 2');

  const browser = await chromium.launch({
    headless: false,
    slowMo: 1200,
    args: ['--window-size=1280,800', '--window-position=200,100', '--disable-blink-features=AutomationControlled'],
  });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    deviceScaleFactor: 2, // retina sim
    ignoreHTTPSErrors: true,
    colorScheme: 'dark',
  });
  const page = await context.newPage();

  // 1) Login form close-up
  log('▶ login form close-up @2x');
  await page.goto(`${BACKEND}/panel/login`, { waitUntil: 'domcontentloaded' });
  await pause(page, 3000, 'render');
  await page.screenshot({ path: `${OUT}/01-login-fullpage.png`, fullPage: true });
  // close-up: form bbox
  const card = await page.locator('form#login-form').boundingBox();
  if (card) {
    await page.screenshot({
      path: `${OUT}/02-login-card-zoom.png`,
      clip: { x: Math.max(0, card.x - 20), y: Math.max(0, card.y - 20), width: card.width + 40, height: card.height + 40 },
    });
    log(`   bbox=${JSON.stringify(card)}`);
  }

  // 2) Setup wizard (skip if completed) — toleranslı
  log('▶ setup step indicator zoom (best-effort)');
  await page.goto(`${BACKEND}/setup`, { waitUntil: 'domcontentloaded' });
  await pause(page, 3000, 'wizard');
  await page.screenshot({ path: `${OUT}/03-wizard-fullpage.png`, fullPage: true });
  try {
    const nav = await page.locator('nav.setup-progress').boundingBox({ timeout: 3000 });
    if (nav) {
      await page.screenshot({
        path: `${OUT}/04-wizard-progress-zoom.png`,
        clip: { x: Math.max(0, nav.x - 10), y: Math.max(0, nav.y - 10), width: nav.width + 20, height: nav.height + 20 },
      });
    }
  } catch (e) {
    log(`   ⚠ wizard nav yok (setup completed) — skip zoom`);
  }

  // 3) Workflow builder canvas zoom
  log('▶ workflow builder node zoom');
  await page.goto(`${LANDING}/admin/workflow-builder`, { waitUntil: 'domcontentloaded' });
  await pause(page, 4000, 'canvas');
  await page.screenshot({ path: `${OUT}/05-builder-fullpage.png`, fullPage: true });
  // first SVG bbox
  const firstSvg = await page.locator('svg').first().boundingBox();
  if (firstSvg) {
    await page.screenshot({
      path: `${OUT}/06-builder-svg-zoom.png`,
      clip: {
        x: Math.max(0, firstSvg.x - 10),
        y: Math.max(0, firstSvg.y - 10),
        width: Math.min(1280, firstSvg.width + 20),
        height: Math.min(800, firstSvg.height + 20),
      },
    });
    log(`   svg bbox=${JSON.stringify(firstSvg)}`);
  }

  // 4) Admin marketplace plugin card zoom
  log('▶ marketplace card zoom');
  await page.goto(`${LANDING}/admin/marketplace`, { waitUntil: 'domcontentloaded' });
  await pause(page, 4000, 'cards');
  await page.screenshot({ path: `${OUT}/07-marketplace-fullpage.png`, fullPage: true });
  const firstCard = await page.locator('article').first().boundingBox();
  if (firstCard) {
    await page.screenshot({
      path: `${OUT}/08-marketplace-card-zoom.png`,
      clip: {
        x: Math.max(0, firstCard.x - 10),
        y: Math.max(0, firstCard.y - 10),
        width: Math.min(1280, firstCard.width + 20),
        height: Math.min(800, firstCard.height + 20),
      },
    });
  }

  // 5) Computed style scan: animation count + svg count + decorative tags
  log('▶ DOM/CSS metrics scan');
  const metrics = {};
  for (const [name, url] of [
    ['login', `${BACKEND}/panel/login`],
    ['wizard', `${BACKEND}/setup`],
    ['builder', `${LANDING}/admin/workflow-builder`],
    ['marketplace', `${LANDING}/admin/marketplace`],
    ['panel-home', `${BACKEND}/panel`],
    ['landing', `${LANDING}/`],
  ]) {
    await page.goto(url, { waitUntil: 'domcontentloaded' }).catch(() => null);
    await page.waitForTimeout(1500);
    const m = await page.evaluate(() => {
      const all = document.querySelectorAll('*');
      let svgs = 0, animations = 0, transitions = 0, gradients = 0, glows = 0;
      const styleSheets = Array.from(document.styleSheets);
      for (const s of styleSheets) {
        try {
          for (const r of s.cssRules) {
            const t = r.cssText || '';
            if (t.includes('@keyframes')) animations++;
            if (t.includes('transition')) transitions++;
            if (t.includes('linear-gradient') || t.includes('radial-gradient')) gradients++;
            if (t.includes('box-shadow') && t.includes('rgba')) glows++;
          }
        } catch (e) {}
      }
      svgs = document.querySelectorAll('svg').length;
      const dom = all.length;
      return { dom, svgs, animations, transitions, gradients, glows };
    });
    metrics[name] = m;
    log(`   ${name}: ${JSON.stringify(m)}`);
  }
  log(`📊 metrics summary: ${JSON.stringify(metrics, null, 2)}`);

  await pause(page, 2000, 'final');
  log('✅ VISUAL AUDIT 2 done');
  await browser.close();
})().catch((err) => {
  console.error('💥 FAIL:', err);
  process.exit(1);
});
