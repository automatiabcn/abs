// Customer Journey — Faz 3: Admin panel login + tour + marketplace showcase
import { chromium } from '@playwright/test';
import { mkdirSync } from 'node:fs';

const OUT = '/tmp/abs-cj';
mkdirSync(OUT, { recursive: true });

const BACKEND = process.env.ABS_BACKEND || 'http://localhost:8000';
const LANDING = process.env.ABS_LANDING || 'http://localhost:3000';

function ts() { return new Date().toISOString().slice(11, 19); }
function log(msg) { console.log(`[${ts()}] ${msg}`); }
async function pause(page, ms, reason) {
  log(`⏸  ${ms}ms — ${reason}`);
  await page.waitForTimeout(ms);
}

(async () => {
  log('🎬 FAZ 3 — Admin Panel + Marketplace Tour');
  log(`Backend: ${BACKEND} · Landing: ${LANDING}`);

  const browser = await chromium.launch({
    headless: false,
    slowMo: 1500,
    args: [
      '--window-size=1280,800',
      '--window-position=200,100',
      '--disable-blink-features=AutomationControlled',
    ],
  });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    ignoreHTTPSErrors: true,
    colorScheme: 'dark',
  });
  const page = await context.newPage();

  page.on('console', (m) => {
    if (m.type() === 'error') log(`🔴 console.error: ${m.text().slice(0, 200)}`);
  });

  // ─── 3.1 Login sayfası ──────────────────────────────────────────
  log('▶ 3.1 /panel/login');
  await page.goto(`${BACKEND}/panel/login`, { waitUntil: 'domcontentloaded' });
  await pause(page, 4000, 'login formu görünür — kullanıcı kart\'ı okur');
  await page.screenshot({ path: `${OUT}/p3-01-login-form.png` });

  // ─── 3.2 Yanlış şifre denemesi (BUG-CJ-007 kanıtı) ──────────────
  log('▶ 3.2 Setup\'tan gelen credentials denemesi (başarısız olmalı — BUG-CJ-007)');
  await page.locator('#email').click();
  await page.locator('#email').fill('admin@demo-acme.com');
  await pause(page, 2000, 'setup\'ta girilen email');
  await page.locator('#password').click();
  await page.locator('#password').fill('DemoAcme2026!');
  await pause(page, 2000, 'setup\'ta girilen parola');
  await page.screenshot({ path: `${OUT}/p3-02-wrong-creds.png` });
  await page.locator('#submit-btn').click();
  await pause(page, 4000, 'sunucu yanıtı — 401 bekleniyor');
  await page.screenshot({ path: `${OUT}/p3-03-login-fail.png` });

  // ─── 3.3 Bootstrap creds ────────────────────────────────────────
  log('▶ 3.3 Bootstrap credentials (workaround)');
  await page.locator('#email').click();
  await page.locator('#email').fill('admin@local');
  await pause(page, 2000, 'bootstrap email');
  await page.locator('#password').click();
  await page.locator('#password').fill('CHANGEME');
  await pause(page, 2000, 'bootstrap parola — DEMO İÇİN');
  await page.screenshot({ path: `${OUT}/p3-04-bootstrap-creds.png` });
  await page.locator('#submit-btn').click();
  await pause(page, 5000, 'login → /panel\'e yönlendirme');
  await page.screenshot({ path: `${OUT}/p3-05-after-login.png` });
  log(`   url after login = ${page.url()}`);

  // ─── 3.4 Panel ana sayfa ────────────────────────────────────────
  log('▶ 3.4 /panel ana sayfa keşif');
  if (!page.url().includes('/panel') || page.url().endsWith('/login')) {
    await page.goto(`${BACKEND}/panel`, { waitUntil: 'domcontentloaded' });
  }
  await pause(page, 5000, 'panel render — kullanıcı widget\'lara bakar');
  // scroll to see content
  await page.mouse.wheel(0, 300);
  await pause(page, 2500, 'scroll #1');
  await page.mouse.wheel(0, 300);
  await pause(page, 2500, 'scroll #2');
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' }));
  await pause(page, 2500, 'tepeye dön');
  await page.screenshot({ path: `${OUT}/p3-06-panel-home.png`, fullPage: true });
  log('   📸 panel-home (fullPage)');

  // ─── 3.5 MCP Tools listing ──────────────────────────────────────
  log('▶ 3.5 /v1/panel/tools — MCP tool envanteri');
  const toolsResp = await page.goto(`${BACKEND}/v1/panel/tools`, { waitUntil: 'domcontentloaded' }).catch(() => null);
  if (toolsResp) {
    log(`   tools API → HTTP ${toolsResp.status()}`);
  }
  await pause(page, 5000, 'JSON envanter — kullanıcı tool listesini görür');
  await page.screenshot({ path: `${OUT}/p3-07-tools-json.png` });

  // ─── 3.6 Landing marketplace showcase ───────────────────────────
  log('▶ 3.6 Landing /admin/marketplace — Sprint 19 plugin showcase');
  await page.goto(`${LANDING}/admin/marketplace`, { waitUntil: 'domcontentloaded' });
  await pause(page, 5000, 'marketplace galeri yüklendi');
  await page.mouse.wheel(0, 400);
  await pause(page, 2500, 'plugin kartlarına bak');
  await page.mouse.wheel(0, 400);
  await pause(page, 2500, 'aşağı scroll');
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' }));
  await pause(page, 2000, 'tepeye dön');
  const cards = await page.locator('article, [data-component="plugin-card"], .plugin-card').count();
  log(`   plugin cards = ${cards}`);
  await page.screenshot({ path: `${OUT}/p3-08-marketplace-tour.png`, fullPage: true });

  // ─── 3.7 Plugin detay denemesi ──────────────────────────────────
  log('▶ 3.7 İlk plugin\'e tıkla (varsa)');
  const firstCard = page.locator('article a, [data-component="plugin-card"] a').first();
  if (await firstCard.count() > 0) {
    await firstCard.scrollIntoViewIfNeeded();
    await pause(page, 1500, 'card hover');
    await firstCard.click().catch((e) => log(`   ⚠ click fail: ${e.message}`));
    await pause(page, 5000, 'plugin detay sayfası');
    await page.screenshot({ path: `${OUT}/p3-09-plugin-detail.png`, fullPage: true });
    log(`   detail url = ${page.url()}`);
  } else {
    log('   ⚠ tıklanabilir kart yok — kartlar static');
  }

  // ─── 3.8 Final ──────────────────────────────────────────────────
  log('▶ 3.8 Final state');
  await pause(page, 4000, 'son frame — kullanıcı değerlendirir');
  await page.screenshot({ path: `${OUT}/p3-10-final.png` });

  log('✅ FAZ 3 tamamlandı');
  await browser.close();
})().catch((err) => {
  console.error('💥 FAIL:', err);
  process.exit(1);
});
