// Customer Journey — Faz 1 HEADED replay
// Browser görünür, slowMo 800ms, kullanıcı persona ekrana bakacak.
import { chromium } from '@playwright/test';
import { mkdirSync } from 'node:fs';

const OUT = '/tmp/abs-cj';
mkdirSync(OUT, { recursive: true });

const BASE = process.env.ABS_BASE || 'http://localhost:3000';
const ADMIN = process.env.ABS_ADMIN || 'http://localhost:3000';

function ts() { return new Date().toISOString().slice(11, 19); }
function log(msg) { console.log(`[${ts()}] ${msg}`); }

async function pause(page, ms, reason) {
  log(`⏸  ${ms}ms — ${reason}`);
  await page.waitForTimeout(ms);
}

(async () => {
  log('🎬 FAZ 1 HEADED — Customer Journey Live');
  log(`Base URL: ${BASE}`);

  const browser = await chromium.launch({
    headless: false,
    slowMo: 1500,
    args: [
      '--window-size=1280,800',
      '--window-position=200,100',
      '--disable-blink-features=AutomationControlled',
      '--no-default-browser-check',
    ],
  });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    ignoreHTTPSErrors: true,
    colorScheme: 'dark',
  });
  const page = await context.newPage();

  page.on('console', (m) => {
    if (m.type() === 'error') log(`🔴 console.error: ${m.text()}`);
  });

  // ─── 1.1 Landing ───────────────────────────────────────────────
  log('▶ 1.1 Landing — navigating to /');
  const t0 = Date.now();
  await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' });
  log(`   loaded in ${Date.now() - t0}ms`);
  const h1 = await page.locator('h1').first().textContent().catch(() => '(no h1)');
  log(`   h1 = "${h1?.trim().slice(0, 120)}"`);
  await pause(page, 5000, 'kullanıcı landing\'i okuyor');
  // Sayfayı aşağı kaydır ki içerik görünsün
  await page.mouse.wheel(0, 400);
  await pause(page, 2000, 'scroll #1');
  await page.mouse.wheel(0, 400);
  await pause(page, 2000, 'scroll #2');
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' }));
  await pause(page, 2000, 'tepeye dön');
  await page.screenshot({ path: `${OUT}/headed-01-landing.png`, fullPage: false });
  log('   📸 headed-01-landing.png');

  // ─── 1.2 Showcase ──────────────────────────────────────────────
  log('▶ 1.2 Showcase — navigating to /showcase');
  await page.goto(`${BASE}/showcase`, { waitUntil: 'domcontentloaded' });
  await pause(page, 2500, 'galerinin render\'ını izle');
  const articles = await page.locator('article').count();
  log(`   article_count = ${articles}`);
  await page.screenshot({ path: `${OUT}/headed-02-showcase.png` });
  log('   📸 headed-02-showcase.png');

  // ─── 1.3 Onboarding ────────────────────────────────────────────
  log('▶ 1.3 Onboarding — navigating to /onboarding');
  await page.goto(`${BASE}/onboarding`, { waitUntil: 'domcontentloaded' });
  await pause(page, 2500, 'onboarding wizard\'a ilk bakış');
  const buttons = await page.locator('button').count();
  log(`   button_count = ${buttons}`);
  await page.screenshot({ path: `${OUT}/headed-03-onboarding.png` });
  log('   📸 headed-03-onboarding.png');

  // ─── 1.4 Marketplace (admin) ───────────────────────────────────
  log('▶ 1.4 Marketplace — navigating to /admin/marketplace');
  await page.goto(`${ADMIN}/admin/marketplace`, { waitUntil: 'domcontentloaded' }).catch((e) => {
    log(`   ⚠ navigation error: ${e.message}`);
  });
  await pause(page, 3000, 'plugin marketplace turuyor');
  const cards = await page.locator('[data-component="plugin-card"], article, .plugin-card').count();
  log(`   plugin_cards = ${cards}`);
  await page.screenshot({ path: `${OUT}/headed-04-marketplace.png` });
  log('   📸 headed-04-marketplace.png');

  await pause(page, 2000, 'son frame — kullanıcı son değerlendirme');

  log('✅ FAZ 1 HEADED tamamlandı');
  await browser.close();
})().catch((err) => {
  console.error('💥 FAIL:', err);
  process.exit(1);
});
