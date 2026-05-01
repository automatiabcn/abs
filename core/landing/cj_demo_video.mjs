// Demo video + tam-render screenshot capture
// Output: /tmp/abs-cj/demo-video/{video.webm, *.png}
import { chromium } from '@playwright/test';
import { mkdirSync } from 'node:fs';

const OUT = '/tmp/abs-cj/demo-video';
mkdirSync(OUT, { recursive: true });

const BACKEND = 'http://localhost:8000';
const LANDING = 'http://localhost:3000';

function ts() { return new Date().toISOString().slice(11, 19); }
function log(m) { console.log(`[${ts()}] ${m}`); }
async function pause(p, ms, r) { log(`⏸ ${ms}ms — ${r}`); await p.waitForTimeout(ms); }

(async () => {
  log('🎬 Demo video + tam-render screenshot capture');

  const browser = await chromium.launch({
    headless: false,
    slowMo: 800,
    args: ['--window-size=1440,900', '--window-position=120,80', '--disable-blink-features=AutomationControlled'],
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    ignoreHTTPSErrors: true,
    colorScheme: 'dark',
    recordVideo: {
      dir: OUT,
      size: { width: 1440, height: 900 },
    },
  });
  const page = await context.newPage();

  // ─── Login (DB-first multi-row) ──────────────────────────
  log('▶ 1/13 Login');
  await page.goto(`${BACKEND}/panel/login`, { waitUntil: 'domcontentloaded' });
  await pause(page, 3500, 'login form fully rendered');
  await page.locator('#email').fill('admin@demo-acme.local');
  await pause(page, 1500, 'email');
  await page.locator('#password').fill('LocalPass2026!');
  await pause(page, 1500, 'password');
  await page.locator('#submit-btn').click();
  await pause(page, 5000, 'panel redirect');
  await page.screenshot({ path: `${OUT}/01-panel-after-login.png`, fullPage: true });

  // ─── Landing tam render ──────────────────────────────────
  log('▶ 2/13 Landing fullpage');
  await page.goto(`${LANDING}/`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await pause(page, 5000, 'landing networkidle');
  await page.evaluate(() => window.scrollTo({ top: document.body.scrollHeight / 2, behavior: 'smooth' }));
  await pause(page, 3000, 'mid-scroll');
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' }));
  await pause(page, 3000, 'top');
  await page.screenshot({ path: `${OUT}/02-landing-full.png`, fullPage: true });

  // ─── Showcase ──────────────────────────────────────────────
  log('▶ 3/13 Showcase');
  await page.goto(`${LANDING}/showcase`, { waitUntil: 'domcontentloaded' });
  await pause(page, 4000, 'showcase render');
  await page.screenshot({ path: `${OUT}/03-showcase-full.png`, fullPage: true });

  // ─── Setup wizard (active) ────────────────────────────────
  log('▶ 4/13 Setup wizard');
  await page.goto(`${BACKEND}/setup`, { waitUntil: 'domcontentloaded' });
  await pause(page, 4000, 'wizard active');
  await page.screenshot({ path: `${OUT}/04-setup-wizard.png`, fullPage: true });

  // ─── Panel home (full render with widgets) ────────────────
  log('▶ 5/13 Panel home full render');
  await page.goto(`${BACKEND}/panel`, { waitUntil: 'domcontentloaded' });
  await pause(page, 6000, 'all widgets render — JS heavy');
  await page.evaluate(() => window.scrollTo({ top: 600, behavior: 'smooth' }));
  await pause(page, 3000, 'mid');
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' }));
  await pause(page, 2000, 'top');
  await page.screenshot({ path: `${OUT}/05-panel-home-full.png`, fullPage: true });

  // ─── MCP tools listing ────────────────────────────────────
  log('▶ 6/13 MCP tools');
  await page.goto(`${BACKEND}/v1/panel/tools`, { waitUntil: 'domcontentloaded' });
  await pause(page, 4000, 'json render');
  await page.screenshot({ path: `${OUT}/06-mcp-tools.png` });

  // ─── Marketplace (interaktif - hover bir karta) ──────────
  log('▶ 7/13 Marketplace + hover plugin');
  await page.goto(`${LANDING}/admin/marketplace`, { waitUntil: 'domcontentloaded' });
  await pause(page, 5000, 'plugin cards render');
  const firstPlugin = page.locator('article, [data-component="plugin-card"]').first();
  if (await firstPlugin.count() > 0) {
    await firstPlugin.hover();
    await pause(page, 2500, 'plugin hover');
  }
  await page.screenshot({ path: `${OUT}/07-marketplace-full.png`, fullPage: true });

  // ─── Workflow Builder (interaktif - prompt yaz + Synthesize) ──
  log('▶ 8/13 Workflow Builder + canlı Synthesize');
  await page.goto(`${LANDING}/admin/workflow-builder`, { waitUntil: 'domcontentloaded' });
  await pause(page, 5000, 'canvas render');
  const promptInput = page.locator('textarea').first();
  if (await promptInput.count() > 0) {
    await promptInput.click();
    await promptInput.fill('Slack #support kanalına yeni mesaj geldiğinde Linear issue oluştur ve sesli özet at');
    await pause(page, 3000, 'prompt yazıldı');
    const synthBtn = page.locator('button:has-text("Synthesize"), [data-testid="synthesize-button"]').first();
    if (await synthBtn.count() > 0) {
      await synthBtn.click();
      await pause(page, 6000, 'synthesize çalışıyor');
    }
  }
  await page.screenshot({ path: `${OUT}/08-workflow-synthesized.png`, fullPage: true });

  // ─── Meetings sayfa (audio upload form full) ──────────────
  log('▶ 9/13 Meetings full');
  await page.goto(`${LANDING}/panel/meetings`, { waitUntil: 'domcontentloaded' });
  await pause(page, 6000, 'meeting list fetch + render');
  await page.screenshot({ path: `${OUT}/09-meetings-full.png`, fullPage: true });

  // ─── Transcription sayfa (mic UI) ──────────────────────────
  log('▶ 10/13 Transcription full');
  await page.goto(`${LANDING}/panel/transcription`, { waitUntil: 'domcontentloaded' });
  await pause(page, 5000, 'mic UI render');
  await page.screenshot({ path: `${OUT}/10-transcription-full.png`, fullPage: true });

  // ─── Quota panel (bar chart full) ──────────────────────────
  log('▶ 11/13 Quota full');
  await page.goto(`${LANDING}/panel/quota`, { waitUntil: 'domcontentloaded' });
  await pause(page, 6000, 'bar chart render + 30s polling first tick');
  await page.screenshot({ path: `${OUT}/11-quota-full.png`, fullPage: true });

  // ─── API JSON (cascade providers) ────────────────────────
  log('▶ 12/13 Cascade providers JSON');
  await page.goto(`${BACKEND}/v1/cascade/providers`, { waitUntil: 'domcontentloaded' });
  await pause(page, 3000, 'json view');
  await page.screenshot({ path: `${OUT}/12-cascade-json.png` });

  // ─── Final landing ────────────────────────────────────────
  log('▶ 13/13 Final landing zoom');
  await page.goto(`${LANDING}/`, { waitUntil: 'domcontentloaded' });
  await pause(page, 4000, 'final hero');
  await page.screenshot({ path: `${OUT}/13-final-landing.png`, fullPage: false });

  log('✅ Tüm sayfalar yakalandı');
  await pause(page, 3000, 'video tail');
  await context.close();
  await browser.close();

  log(`📂 Screenshot: ${OUT}/`);
  log(`🎥 Video: ${OUT}/*.webm (otomatik isimlendirildi)`);
})().catch((err) => {
  console.error('💥 FAIL:', err);
  process.exit(1);
});
