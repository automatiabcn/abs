// Customer Journey — Faz 5: Meetings + Sprint 20 free-tier (Coqui XTTS, meetily, jitsi)
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
  log('🎬 FAZ 5 — Meetings + Free-tier (Sprint 20)');

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

  // bootstrap login first
  log('▶ login (bootstrap creds)');
  await page.goto(`${BACKEND}/panel/login`, { waitUntil: 'domcontentloaded' });
  await pause(page, 2500, 'login form');
  await page.locator('#email').fill('admin@local');
  await page.locator('#password').fill('CHANGEME');
  await pause(page, 1500, 'creds');
  await page.locator('#submit-btn').click();
  await pause(page, 4000, 'redirect bekleniyor');
  log(`   url after login = ${page.url()}`);

  // probe meetings/transcription routes
  const probes = [
    `${BACKEND}/panel/meetings`,
    `${BACKEND}/panel/transcription`,
    `${BACKEND}/panel/quota`,
    `${LANDING}/admin/meetings`,
    `${LANDING}/admin/quota`,
  ];

  log('▶ Faz 5 route probing');
  for (const url of probes) {
    log(`▶ probe ${url}`);
    const resp = await page.goto(url, { waitUntil: 'domcontentloaded' }).catch(() => null);
    const status = resp ? resp.status() : 0;
    log(`   → ${status}`);
    await pause(page, 3500, `kullanıcı ${url} ekranını okur`);
    const slug = url.split('/').pop();
    await page.screenshot({ path: `${OUT}/p5-${slug}.png`, fullPage: true }).catch(() => null);
  }

  // backend API probes (görüntülenebilir JSON)
  const apis = [
    `${BACKEND}/v1/system/quota_status`,
    `${BACKEND}/v1/admin/dashboard`,
    `${BACKEND}/v1/panel/cascade/recent`,
    `${BACKEND}/v1/panel/pipeline/recent`,
  ];

  log('▶ API probes');
  for (const url of apis) {
    const resp = await page.goto(url, { waitUntil: 'domcontentloaded' }).catch(() => null);
    log(`   ${url} → ${resp ? resp.status() : 'fail'}`);
    await pause(page, 3000, `JSON çıktıyı oku`);
    const slug = url.replace(/[^a-z0-9]/gi, '_').slice(-50);
    await page.screenshot({ path: `${OUT}/p5-api-${slug}.png` }).catch(() => null);
  }

  await pause(page, 3000, 'final');
  log('✅ FAZ 5 tamamlandı');
  await browser.close();
})().catch((err) => {
  console.error('💥 FAIL:', err);
  process.exit(1);
});
