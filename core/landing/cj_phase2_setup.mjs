// Customer Journey — Faz 2 v2: GERÇEK /setup wizard headed walkthrough
// Backend port 8000 → 6-step admin onboarding.
import { chromium } from '@playwright/test';
import { mkdirSync } from 'node:fs';

const OUT = '/tmp/abs-cj';
mkdirSync(OUT, { recursive: true });

const BACKEND = process.env.ABS_BACKEND || 'http://localhost:8000';

function ts() { return new Date().toISOString().slice(11, 19); }
function log(msg) { console.log(`[${ts()}] ${msg}`); }
async function pause(page, ms, reason) {
  log(`⏸  ${ms}ms — ${reason}`);
  await page.waitForTimeout(ms);
}

(async () => {
  log('🎬 FAZ 2 v2 — /setup wizard 6-step walkthrough');
  log(`Backend: ${BACKEND}`);

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

  // ─── 2.0 Setup sayfasına git ────────────────────────────────────
  log('▶ 2.0 /setup\'a git');
  await page.goto(`${BACKEND}/setup`, { waitUntil: 'domcontentloaded' });
  await pause(page, 4000, 'wizard ekrana gelir, kullanıcı progress bar\'ı görür');
  const stepCount = await page.locator('[data-step-indicator]').count();
  log(`   step indicators = ${stepCount}`);
  await page.screenshot({ path: `${OUT}/p2v2-00-wizard-start.png` });

  // ─── 2.1 STEP 1: Admin email + password ─────────────────────────
  log('▶ 2.1 STEP 1 — Yönetici hesabı');
  const step1 = page.locator('[data-step="1"]');
  await step1.scrollIntoViewIfNeeded();
  await pause(page, 2000, 'Step 1 başlığı okunur');

  const emailInput = step1.locator('input[name="email"]');
  await emailInput.click();
  await emailInput.fill('admin@demo-acme.com');
  await pause(page, 2000, 'email girildi');

  const pwInput = step1.locator('input[name="password"]');
  await pwInput.click();
  await pwInput.fill('DemoAcme2026!');
  await pause(page, 2000, 'parola girildi');
  await page.screenshot({ path: `${OUT}/p2v2-01-step1-filled.png` });

  await step1.locator('button.setup-next').click();
  await pause(page, 3000, 'Step 1 submit, sunucu yanıtı bekleniyor');

  // ─── 2.2 STEP 2: Lisans (skip — demo mode) ──────────────────────
  log('▶ 2.2 STEP 2 — Lisans (demo mode bypass)');
  const step2 = page.locator('[data-step="2"]:visible');
  if (await step2.count() > 0) {
    await step2.scrollIntoViewIfNeeded();
    await pause(page, 2500, 'lisans alanı görünür');
    // 14-day demo için boş bırakmak istesek de required textarea — placeholder JWT ile dolduralım
    const lic = step2.locator('textarea[name="license_key"]');
    await lic.click();
    await lic.fill('demo-mode-14-day-trial-2026-04-29');
    await pause(page, 2500, 'lisans demo değeri girildi');
    await page.screenshot({ path: `${OUT}/p2v2-02-step2-license.png` });
    await step2.locator('button.setup-next').click().catch((e) => log(`   ⚠ ${e.message}`));
    await pause(page, 3000, 'Step 2 submit');
  } else {
    log('   ⚠ Step 2 görünmedi — Step 1 başarısız olmuş olabilir');
    await page.screenshot({ path: `${OUT}/p2v2-02-step1-fail.png` });
    const err = await page.locator('#setup-error').textContent().catch(() => '');
    log(`   error = ${err}`);
  }

  // ─── 2.3 STEP 3: Domain ─────────────────────────────────────────
  log('▶ 2.3 STEP 3 — Domain (IP mode + Internal CA)');
  const step3 = page.locator('[data-step="3"]:visible');
  if (await step3.count() > 0) {
    await step3.scrollIntoViewIfNeeded();
    await pause(page, 2500, 'domain ayarları');
    // IP + Internal CA default — sadece submit
    await page.screenshot({ path: `${OUT}/p2v2-03-step3-domain.png` });
    await step3.locator('button.setup-next').click().catch((e) => log(`   ⚠ ${e.message}`));
    await pause(page, 3000, 'Step 3 submit');
  } else {
    log('   ⚠ Step 3 görünmedi');
  }

  // ─── 2.4 STEP 4: Anthropic API Key ──────────────────────────────
  log('▶ 2.4 STEP 4 — Anthropic API Key (BUG-CJ-004 adayı: müşteri vaadi Claude Plus, API key değil)');
  const step4 = page.locator('[data-step="4"]:visible');
  if (await step4.count() > 0) {
    await step4.scrollIntoViewIfNeeded();
    await pause(page, 3500, 'Anthropic key zorunlu — müşteri vaadi ile çelişki');
    const ak = step4.locator('input[name="anthropic_api_key"]');
    await ak.click();
    await ak.fill('sk-ant-test-placeholder-12345678');
    await pause(page, 2500, 'placeholder anahtar girildi');
    await page.screenshot({ path: `${OUT}/p2v2-04-step4-anthropic.png` });
    await step4.locator('button.setup-next').click().catch((e) => log(`   ⚠ ${e.message}`));
    await pause(page, 3500, 'Step 4 submit (validation hata verebilir)');
  } else {
    log('   ⚠ Step 4 görünmedi');
  }

  // ─── 2.5 STEP 5: Providers ──────────────────────────────────────
  log('▶ 2.5 STEP 5 — Provider keys (hepsi opsiyonel, atlanır)');
  const step5 = page.locator('[data-step="5"]:visible');
  if (await step5.count() > 0) {
    await step5.scrollIntoViewIfNeeded();
    await pause(page, 3000, 'opsiyonel provider alanları görünür');
    await page.screenshot({ path: `${OUT}/p2v2-05-step5-providers.png` });
    await step5.locator('button.setup-next').click().catch((e) => log(`   ⚠ ${e.message}`));
    await pause(page, 3000, 'Step 5 submit (boş bırakıldı)');
  } else {
    log('   ⚠ Step 5 görünmedi');
  }

  // ─── 2.6 STEP 6: Test ───────────────────────────────────────────
  log('▶ 2.6 STEP 6 — Provider test ping');
  const step6 = page.locator('[data-step="6"]:visible');
  if (await step6.count() > 0) {
    await step6.scrollIntoViewIfNeeded();
    await pause(page, 3000, 'test ekranı görünür');
    await page.screenshot({ path: `${OUT}/p2v2-06-step6-test.png` });
    const finish = step6.locator('button.setup-finish');
    if (await finish.count() > 0) {
      await finish.click().catch((e) => log(`   ⚠ ${e.message}`));
      await pause(page, 5000, 'kurulum tamamlanma yanıtı');
      await page.screenshot({ path: `${OUT}/p2v2-07-finish.png` });
    }
  } else {
    log('   ⚠ Step 6 görünmedi');
  }

  // ─── 2.7 Final state ────────────────────────────────────────────
  log('▶ 2.7 Final state');
  const finalUrl = page.url();
  log(`   final url = ${finalUrl}`);
  await pause(page, 4000, 'son frame — sonuç');

  log('✅ FAZ 2 v2 tamamlandı');
  await browser.close();
})().catch((err) => {
  console.error('💥 FAIL:', err);
  process.exit(1);
});
