// Q5 sonrası sistem state screenshot — bittiğinde sahip olunacak ürün
import { chromium } from '@playwright/test';
import { mkdirSync } from 'node:fs';

const OUT = '/tmp/abs-cj/q5-state';
mkdirSync(OUT, { recursive: true });

const BACKEND = 'http://localhost:8000';
const LANDING = 'http://localhost:3000';

function ts() { return new Date().toISOString().slice(11, 19); }
function log(m) { console.log(`[${ts()}] ${m}`); }
async function pause(p, ms, r) { log(`⏸ ${ms}ms — ${r}`); await p.waitForTimeout(ms); }

(async () => {
  log('🎬 Q5 sonrası sistem state screenshot başlıyor');

  const browser = await chromium.launch({
    headless: false,
    slowMo: 1000,
    args: ['--window-size=1440,900', '--window-position=120,80', '--disable-blink-features=AutomationControlled'],
  });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    ignoreHTTPSErrors: true,
    colorScheme: 'dark',
  });
  const page = await context.newPage();

  // Login first (multi-row DB-first)
  log('▶ Login admin@demo-acme.local');
  await page.goto(`${BACKEND}/panel/login`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await pause(page, 2500, 'login form');
  await page.locator('#email').fill('admin@demo-acme.local');
  await page.locator('#password').fill('LocalPass2026!');
  await page.locator('#submit-btn').click();
  await pause(page, 4000, 'redirect');
  await page.screenshot({ path: `${OUT}/00-after-login.png`, fullPage: false });

  // Routes to capture
  const routes = [
    { url: `${LANDING}/`, label: '01-landing', scroll: true },
    { url: `${LANDING}/showcase`, label: '02-showcase', scroll: true },
    { url: `${BACKEND}/setup`, label: '03-setup-wizard', scroll: false },
    { url: `${BACKEND}/panel`, label: '04-panel-home', scroll: true },
    { url: `${BACKEND}/v1/panel/tools`, label: '05-mcp-tools', scroll: false },
    { url: `${LANDING}/admin/marketplace`, label: '06-marketplace', scroll: true },
    { url: `${LANDING}/admin/workflow-builder`, label: '07-workflow-builder', scroll: true },
    { url: `${LANDING}/panel/meetings`, label: '08-meetings', scroll: true },
    { url: `${LANDING}/panel/transcription`, label: '09-transcription', scroll: false },
    { url: `${LANDING}/panel/quota`, label: '10-quota', scroll: true },
    { url: `${BACKEND}/v1/system/quota_status`, label: '11-quota-api-json', scroll: false },
    { url: `${BACKEND}/v1/cascade/providers`, label: '12-cascade-providers-json', scroll: false },
    { url: `${BACKEND}/v1/admin/dashboard`, label: '13-admin-dashboard-json', scroll: false },
  ];

  for (const r of routes) {
    log(`▶ ${r.label} ${r.url}`);
    try {
      await page.goto(r.url, { waitUntil: 'domcontentloaded', timeout: 60000 });
      await pause(page, 2500, 'render');
      if (r.scroll) {
        await page.mouse.wheel(0, 400);
        await pause(page, 1500, 'scroll #1');
        await page.mouse.wheel(0, 400);
        await pause(page, 1500, 'scroll #2');
        await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' }));
        await pause(page, 1500, 'top');
      }
      await page.screenshot({ path: `${OUT}/${r.label}.png`, fullPage: r.scroll });
      log(`   📸 ${r.label}.png`);
    } catch (e) {
      log(`   ⚠ ${r.label} fail: ${e.message.slice(0, 60)}`);
    }
  }

  log('✅ Tamamlandı');
  log(`📂 ${OUT}`);
  await pause(page, 2000, 'final');
  await browser.close();
})().catch((err) => {
  console.error('💥 FAIL:', err);
  process.exit(1);
});
