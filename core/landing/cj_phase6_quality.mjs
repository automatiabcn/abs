// Customer Journey — Faz 6: Quality Gates + Quota Tracker
import { chromium } from '@playwright/test';
import { mkdirSync } from 'node:fs';

const OUT = '/tmp/abs-cj/phase6';
mkdirSync(OUT, { recursive: true });

const BACKEND = process.env.ABS_BACKEND || 'http://localhost:8000';

function ts() { return new Date().toISOString().slice(11, 19); }
function log(msg) { console.log(`[${ts()}] ${msg}`); }
async function pause(page, ms, reason) { log(`⏸ ${ms}ms — ${reason}`); await page.waitForTimeout(ms); }

(async () => {
  log('🎬 FAZ 6 — Quality Gates + Quota Tracker');

  const browser = await chromium.launch({
    headless: false, slowMo: 1200,
    args: ['--window-size=1280,800', '--window-position=200,100'],
  });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 }, ignoreHTTPSErrors: true, colorScheme: 'dark',
  });
  const page = await context.newPage();
  page.on('console', (m) => { if (m.type() === 'error') log(`🔴 ${m.text().slice(0, 160)}`); });

  // login
  log('▶ login');
  await page.goto(`${BACKEND}/panel/login`, { waitUntil: 'domcontentloaded' });
  await pause(page, 2000, 'form');
  await page.locator('#email').fill('admin@local');
  await page.locator('#password').fill('CHANGEME');
  await page.locator('#submit-btn').click();
  await pause(page, 4000, 'redirect');

  // probe quality + quota endpoints
  const probes = [
    { url: `${BACKEND}/v1/panel/cascade/recent`, label: 'cascade-recent' },
    { url: `${BACKEND}/v1/panel/pipeline/recent`, label: 'pipeline-recent' },
    { url: `${BACKEND}/v1/panel/tools`, label: 'tools-list' },
    { url: `${BACKEND}/v1/system/quota_status`, label: 'quota-status' },
    { url: `${BACKEND}/v1/admin/dashboard`, label: 'admin-dashboard' },
    { url: `${BACKEND}/v1/admin/audit/recent`, label: 'admin-audit-recent' },
    { url: `${BACKEND}/v1/admin/errors/recent`, label: 'admin-errors-recent' },
    { url: `${BACKEND}/v1/admin/status/full`, label: 'admin-status-full' },
    { url: `${BACKEND}/v1/admin/analytics/licenses`, label: 'analytics-licenses' },
    { url: `${BACKEND}/v1/admin/analytics/churn`, label: 'analytics-churn' },
    { url: `${BACKEND}/v1/admin/vault/audit`, label: 'vault-audit' },
  ];

  const results = [];
  for (const p of probes) {
    const resp = await page.goto(p.url, { waitUntil: 'domcontentloaded' }).catch(() => null);
    const status = resp ? resp.status() : 0;
    const body = await page.locator('body').textContent().catch(() => '');
    const len = body?.length || 0;
    log(`   ${p.label} ${p.url} → ${status} (${len} chars)`);
    results.push({ ...p, status, len });
    await page.screenshot({ path: `${OUT}/q-${p.label}.png` }).catch(() => null);
    await pause(page, 1500, 'render');
  }

  log('📊 results: ' + JSON.stringify(results, null, 2));

  await pause(page, 2000, 'final');
  log('✅ FAZ 6 done');
  await browser.close();
})().catch((err) => {
  console.error('💥 FAIL:', err);
  process.exit(1);
});
