// Customer Journey — Faz 2 v3: Setup wizard Step 2-6 (Step 1 zaten tamamlandı)
import { chromium } from '@playwright/test';
import { mkdirSync, readFileSync } from 'node:fs';

const OUT = '/tmp/abs-cj';
mkdirSync(OUT, { recursive: true });

const BACKEND = process.env.ABS_BACKEND || 'http://localhost:8000';
const LICENSE = readFileSync('/tmp/abs-cj/demo_license.jwt', 'utf-8').trim();

function ts() { return new Date().toISOString().slice(11, 19); }
function log(msg) { console.log(`[${ts()}] ${msg}`); }
async function pause(page, ms, reason) {
  log(`⏸  ${ms}ms — ${reason}`);
  await page.waitForTimeout(ms);
}

(async () => {
  log('🎬 FAZ 2 v3 — Setup wizard Step 2→6');
  log(`Backend: ${BACKEND}`);
  log(`License: ${LICENSE.slice(0, 50)}... (${LICENSE.length} chars)`);

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

  await page.goto(`${BACKEND}/setup`, { waitUntil: 'domcontentloaded' });
  await pause(page, 4000, 'wizard yüklendi (Step 2 aktif olmalı)');
  await page.screenshot({ path: `${OUT}/p2v3-00-resume.png` });

  // ─── Step 2: License ────────────────────────────────────────────
  log('▶ Step 2 — Demo lisans JWT girdiriliyor');
  const step2 = page.locator('[data-step="2"]:visible');
  if (await step2.count() === 0) {
    log('   ⚠ Step 2 görünmüyor, manuel showStep(2) tetikliyorum');
    await page.evaluate(() => {
      document.querySelectorAll('.setup-step').forEach((s) => {
        s.hidden = Number(s.dataset.step) !== 2;
      });
    });
    await pause(page, 1500, 'forced show step 2');
  }
  const step2v = page.locator('[data-step="2"]');
  await step2v.scrollIntoViewIfNeeded();
  await pause(page, 2500, 'lisans alanı odakta');

  const lic = step2v.locator('textarea[name="license_key"]');
  await lic.click();
  // Yavaş yapıştır — kullanıcı görsün
  await lic.fill(LICENSE);
  await pause(page, 3000, 'JWT yapıştırıldı, görsel doğrulama');
  await page.screenshot({ path: `${OUT}/p2v3-01-license-filled.png` });

  await step2v.locator('button.setup-next').click();
  await pause(page, 4000, 'Step 2 submit → tier doğrulama');

  const errAfter2 = await page.locator('#setup-error:not([hidden])').textContent().catch(() => '');
  if (errAfter2) log(`   🔴 Step 2 ERROR: ${errAfter2}`);

  // ─── Step 3: Domain ─────────────────────────────────────────────
  log('▶ Step 3 — Domain (IP + Internal CA)');
  const step3 = page.locator('[data-step="3"]:visible');
  if (await step3.count() > 0) {
    await step3.scrollIntoViewIfNeeded();
    await pause(page, 3000, 'domain seçenekleri görünür');
    await page.screenshot({ path: `${OUT}/p2v3-02-domain.png` });
    await step3.locator('button.setup-next').click();
    await pause(page, 3000, 'Step 3 submit');
  } else {
    log('   ⚠ Step 3 yok');
  }

  // ─── Step 4: Anthropic ──────────────────────────────────────────
  log('▶ Step 4 — Anthropic API Key (placeholder, customer-promise mismatch)');
  const step4 = page.locator('[data-step="4"]:visible');
  if (await step4.count() > 0) {
    await step4.scrollIntoViewIfNeeded();
    await pause(page, 3500, 'müşteri vaadi: Claude Plus → buraya API key gerekiyor');
    const ak = step4.locator('input[name="anthropic_api_key"]');
    await ak.click();
    await ak.fill('sk-ant-api03-placeholder-for-customer-journey-test-12345');
    await pause(page, 2500, 'placeholder anahtar girildi');
    await page.screenshot({ path: `${OUT}/p2v3-03-anthropic.png` });
    await step4.locator('button.setup-next').click();
    await pause(page, 4000, 'Step 4 submit');

    const errAfter4 = await page.locator('#setup-error:not([hidden])').textContent().catch(() => '');
    if (errAfter4) log(`   🔴 Step 4 ERROR: ${errAfter4}`);
  } else {
    log('   ⚠ Step 4 yok');
  }

  // ─── Step 5: Providers ──────────────────────────────────────────
  log('▶ Step 5 — Provider keys (boş bırakılır)');
  const step5 = page.locator('[data-step="5"]:visible');
  if (await step5.count() > 0) {
    await step5.scrollIntoViewIfNeeded();
    await pause(page, 3500, 'Groq, Gemini, Cerebras, Cohere, Cloudflare alanları (hepsi opsiyonel)');
    await page.screenshot({ path: `${OUT}/p2v3-04-providers.png` });
    await step5.locator('button.setup-next').click();
    await pause(page, 3000, 'Step 5 submit (boş)');
  } else {
    log('   ⚠ Step 5 yok');
  }

  // ─── Step 6: Test ───────────────────────────────────────────────
  log('▶ Step 6 — Provider test ping');
  const step6 = page.locator('[data-step="6"]:visible');
  if (await step6.count() > 0) {
    await step6.scrollIntoViewIfNeeded();
    await pause(page, 3000, 'test ekranı');
    await page.screenshot({ path: `${OUT}/p2v3-05-test.png` });
    const finish = step6.locator('button.setup-finish');
    await finish.click();
    await pause(page, 6000, 'kurulum tamamlanıyor, panel\'e yönlendirme bekleniyor');
    await page.screenshot({ path: `${OUT}/p2v3-06-after-finish.png` });
    log(`   url after finish = ${page.url()}`);
  } else {
    log('   ⚠ Step 6 yok');
  }

  // ─── Final ──────────────────────────────────────────────────────
  log('▶ Final state');
  await pause(page, 4000, 'son frame');
  log(`   final url = ${page.url()}`);
  await page.screenshot({ path: `${OUT}/p2v3-07-final.png` });

  log('✅ FAZ 2 v3 tamamlandı');
  await browser.close();
})().catch((err) => {
  console.error('💥 FAIL:', err);
  process.exit(1);
});
