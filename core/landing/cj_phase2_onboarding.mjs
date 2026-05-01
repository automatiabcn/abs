// Customer Journey — Faz 2 HEADED: Onboarding Wizard
// Persona: demo-acme tenant, slow walkthrough.
import { chromium } from '@playwright/test';
import { mkdirSync } from 'node:fs';

const OUT = '/tmp/abs-cj';
mkdirSync(OUT, { recursive: true });

const BASE = process.env.ABS_BASE || 'http://localhost:3000';
const BACKEND = process.env.ABS_BACKEND || 'http://localhost:8000';

function ts() { return new Date().toISOString().slice(11, 19); }
function log(msg) { console.log(`[${ts()}] ${msg}`); }
async function pause(page, ms, reason) {
  log(`⏸  ${ms}ms — ${reason}`);
  await page.waitForTimeout(ms);
}

(async () => {
  log('🎬 FAZ 2 HEADED — Onboarding Wizard');
  log(`Landing: ${BASE} · Backend: ${BACKEND}`);

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
    if (m.type() === 'error') log(`🔴 console.error: ${m.text().slice(0, 160)}`);
  });

  // ─── 2.1 Landing → Get Started CTA ──────────────────────────────
  log('▶ 2.1 Landing → CTA');
  await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' });
  await pause(page, 4000, 'kullanıcı landing\'i tartar');

  // CTA tıklamayı dene — birden fazla olası selector
  const ctaSelectors = [
    'a:has-text("Get Started")',
    'a:has-text("Try Demo")',
    'a:has-text("Başla")',
    'a:has-text("Demo")',
    'a[href*="onboarding"]',
    'a[href*="signup"]',
  ];
  let clicked = false;
  for (const sel of ctaSelectors) {
    const loc = page.locator(sel).first();
    if (await loc.count() > 0) {
      log(`   → CTA bulundu: ${sel}`);
      await loc.scrollIntoViewIfNeeded();
      await pause(page, 1500, 'CTA hover');
      await loc.click().catch(() => null);
      clicked = true;
      break;
    }
  }
  if (!clicked) {
    log('   ⚠ CTA selector bulunamadı, /onboarding\'e direkt');
    await page.goto(`${BASE}/onboarding`, { waitUntil: 'domcontentloaded' });
  }
  await pause(page, 3000, 'navigation tamam');
  await page.screenshot({ path: `${OUT}/p2-01-after-cta.png` });
  log(`   📸 url=${page.url()}`);

  // ─── 2.2 Onboarding sayfası analiz ──────────────────────────────
  log('▶ 2.2 Onboarding sayfası DOM analiz');
  await page.goto(`${BASE}/onboarding`, { waitUntil: 'domcontentloaded' });
  await pause(page, 3000, 'sayfa render');
  const allButtons = await page.locator('button, a[role="button"]').allTextContents();
  log(`   buttons (${allButtons.length}): ${JSON.stringify(allButtons.slice(0, 8))}`);
  const allInputs = await page.locator('input, textarea, select').count();
  log(`   form fields = ${allInputs}`);
  const allLinks = await page.locator('a').allTextContents();
  log(`   links sample: ${JSON.stringify(allLinks.slice(0, 6))}`);
  await page.screenshot({ path: `${OUT}/p2-02-onboarding-analysis.png` });

  // ─── 2.3 Eğer email input varsa doldur ──────────────────────────
  log('▶ 2.3 Form doldurma denemesi');
  const emailInput = page.locator('input[type="email"], input[name*="email" i]').first();
  if (await emailInput.count() > 0) {
    log('   → email input bulundu, dolduruyorum');
    await emailInput.scrollIntoViewIfNeeded();
    await pause(page, 1500, 'input\'a hover');
    await emailInput.click();
    await pause(page, 800, 'focus');
    await emailInput.type('demo@acme.com', { delay: 80 });
    await pause(page, 2000, 'değer girildi');
    await page.screenshot({ path: `${OUT}/p2-03-email-typed.png` });

    // Submit
    const submitBtn = page.locator('button[type="submit"], button:has-text("Continue"), button:has-text("Sign in"), button:has-text("Magic"), button:has-text("Devam")').first();
    if (await submitBtn.count() > 0) {
      log('   → submit button tıklanıyor');
      await pause(page, 1500, 'submit hover');
      await submitBtn.click().catch((e) => log(`   ⚠ click fail: ${e.message}`));
      await pause(page, 4000, 'sunucu yanıtı bekleniyor');
      await page.screenshot({ path: `${OUT}/p2-04-after-submit.png` });
      log(`   url after submit = ${page.url()}`);
    } else {
      log('   ⚠ submit button bulunamadı');
    }
  } else {
    log('   ⚠ email input bulunamadı — onboarding muhtemelen post-login');
  }

  // ─── 2.4 /signup probe ──────────────────────────────────────────
  log('▶ 2.4 /signup route probe');
  const sigResp = await page.goto(`${BASE}/signup`, { waitUntil: 'domcontentloaded' }).catch(() => null);
  if (sigResp) {
    const status = sigResp.status();
    log(`   /signup → HTTP ${status}`);
    if (status === 404) log('   🔴 BUG-CJ-003 doğrulandı: /signup yok');
  }
  await pause(page, 3000, 'signup sayfası ekranda');
  await page.screenshot({ path: `${OUT}/p2-05-signup-probe.png` });

  // ─── 2.5 Backend health check (ekrana yansıt) ───────────────────
  log('▶ 2.5 Backend /health görsel kontrolü');
  await page.goto(`${BACKEND}/health`, { waitUntil: 'domcontentloaded' }).catch((e) => log(`   ⚠ ${e.message}`));
  await pause(page, 4000, 'backend JSON görünür');
  await page.screenshot({ path: `${OUT}/p2-06-backend-health.png` });
  const body = await page.locator('body').textContent().catch(() => '');
  log(`   backend body: ${body?.slice(0, 200)}`);

  await pause(page, 2500, 'final değerlendirme');

  log('✅ FAZ 2 HEADED tamamlandı');
  await browser.close();
})().catch((err) => {
  console.error('💥 FAIL:', err);
  process.exit(1);
});
