// Customer Journey — Faz 4: NL Workflow Builder canvas tour
import { chromium } from '@playwright/test';
import { mkdirSync } from 'node:fs';

const OUT = '/tmp/abs-cj';
mkdirSync(OUT, { recursive: true });

const LANDING = process.env.ABS_LANDING || 'http://localhost:3000';

function ts() { return new Date().toISOString().slice(11, 19); }
function log(msg) { console.log(`[${ts()}] ${msg}`); }
async function pause(page, ms, reason) {
  log(`⏸  ${ms}ms — ${reason}`);
  await page.waitForTimeout(ms);
}

(async () => {
  log('🎬 FAZ 4 — NL Workflow Builder');
  log(`Landing: ${LANDING}`);

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

  // ─── 4.1 Workflow builder sayfa ─────────────────────────────────
  log('▶ 4.1 /admin/workflow-builder');
  await page.goto(`${LANDING}/admin/workflow-builder`, { waitUntil: 'domcontentloaded' });
  await pause(page, 5000, 'canvas yükleniyor — kullanıcı tuvali görür');
  await page.screenshot({ path: `${OUT}/p4-01-canvas.png`, fullPage: false });

  // ─── 4.2 DOM analiz ─────────────────────────────────────────────
  log('▶ 4.2 Canvas DOM analiz');
  const headings = await page.locator('h1, h2').allTextContents();
  log(`   headings: ${JSON.stringify(headings.slice(0, 6))}`);
  const buttons = await page.locator('button').allTextContents();
  log(`   buttons (${buttons.length}): ${JSON.stringify(buttons.slice(0, 10))}`);
  const inputs = await page.locator('input, textarea').count();
  log(`   form inputs: ${inputs}`);
  const svgs = await page.locator('svg').count();
  log(`   svg elements (canvas yapı taşları): ${svgs}`);

  // ─── 4.3 NL prompt input ────────────────────────────────────────
  log('▶ 4.3 Doğal dil prompt arıyorum');
  const promptSelectors = [
    'textarea[placeholder*="Describe" i]',
    'textarea[placeholder*="prompt" i]',
    'textarea[placeholder*="açıkla" i]',
    'input[placeholder*="describe" i]',
    'textarea',
  ];
  let promptInput = null;
  for (const sel of promptSelectors) {
    const loc = page.locator(sel).first();
    if (await loc.count() > 0) {
      promptInput = loc;
      log(`   → prompt input bulundu: ${sel}`);
      break;
    }
  }
  if (promptInput) {
    await promptInput.scrollIntoViewIfNeeded();
    await pause(page, 2000, 'prompt alanı odakta');
    await promptInput.click();
    const samplePrompt = 'Slack #support kanalına yeni mesaj gelirse, Linear\'da issue oluştur ve customer\'a Gmail ile özür e-postası gönder.';
    await promptInput.fill(samplePrompt);
    await pause(page, 4000, 'KOBİ senaryosu yazıldı — kullanıcı okur');
    await page.screenshot({ path: `${OUT}/p4-02-prompt-typed.png` });

    // generate butonu
    const genBtn = page.locator('button:has-text("Generate"), button:has-text("Build"), button:has-text("Oluştur"), button:has-text("Compile")').first();
    if (await genBtn.count() > 0) {
      log('   → Generate butonu var, tıklıyorum');
      await pause(page, 1500, 'hover');
      await genBtn.click();
      await pause(page, 6000, 'graph compile bekleniyor');
      await page.screenshot({ path: `${OUT}/p4-03-generated.png`, fullPage: true });
    } else {
      log('   ⚠ Generate butonu bulunamadı');
    }
  } else {
    log('   ⚠ NL prompt textarea bulunamadı');
  }

  // ─── 4.4 Template seçici ────────────────────────────────────────
  log('▶ 4.4 Template galerisi probe');
  const tmplBtn = page.locator('button:has-text("Template"), a:has-text("Template"), button:has-text("Şablon")').first();
  if (await tmplBtn.count() > 0) {
    await tmplBtn.click().catch(() => null);
    await pause(page, 4000, 'template seçici ekranda');
    await page.screenshot({ path: `${OUT}/p4-04-templates.png` });
    const tmplCount = await page.locator('article, [data-component="template-card"], .template-card').count();
    log(`   template kart sayısı = ${tmplCount} (Sprint 19 hedefi: 50)`);
  } else {
    log('   ⚠ Template butonu yok');
  }

  // ─── 4.5 Cycle detection / validation ───────────────────────────
  log('▶ 4.5 Validation panel probe');
  const validation = page.locator('text=/cycle|validation|whitelist|blocked|geçerli/i').first();
  if (await validation.count() > 0) {
    log('   ✓ validation/cycle terminolojisi sayfada görünür');
  } else {
    log('   ⚠ validation feedback görülmedi');
  }

  // ─── 4.6 Final scroll ───────────────────────────────────────────
  log('▶ 4.6 Final tour');
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' }));
  await pause(page, 2500, 'tepeye dön');
  await page.screenshot({ path: `${OUT}/p4-05-final.png`, fullPage: true });
  await pause(page, 4000, 'son frame');

  log('✅ FAZ 4 tamamlandı');
  await browser.close();
})().catch((err) => {
  console.error('💥 FAIL:', err);
  process.exit(1);
});
