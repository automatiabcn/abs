// Customer Demo Flow — Playwright headed canlı demo
// Süre: ~10 dk · Persona: müşteri toplantısında kullanıcı
// Slide ile senkron çalışır, her sahne 30-60s
import { chromium } from '@playwright/test';
import { mkdirSync } from 'node:fs';

const OUT = '/tmp/abs-cj/demo';
mkdirSync(OUT, { recursive: true });

const BACKEND = process.env.ABS_BACKEND || 'http://localhost:8000';
const LANDING = process.env.ABS_LANDING || 'http://localhost:3000';

function ts() { return new Date().toISOString().slice(11, 19); }
function log(msg) { console.log(`[${ts()}] ${msg}`); }
function narrate(scene, msg) { console.log(`\n🎬 SAHNE ${scene}: ${msg}\n`); }
async function pause(page, ms, reason) { log(`⏸ ${ms}ms — ${reason}`); await page.waitForTimeout(ms); }

(async () => {
  log('🎬 Customer Demo — başlıyor');

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

  // ─── SAHNE 1: Landing — Vaadler ──────────────────────────
  narrate(1, 'Landing — "100+ MCP tool, dakikalar içinde kurulum"');
  await page.goto(`${LANDING}/`, { waitUntil: 'domcontentloaded' });
  await pause(page, 6000, 'müşteri h1 + 6 sağlayıcı cascade görür');
  await page.mouse.wheel(0, 500);
  await pause(page, 4000, 'features 8 kart');
  await page.mouse.wheel(0, 500);
  await pause(page, 4000, 'FAQ');
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' }));
  await pause(page, 2000, 'tepe');
  await page.screenshot({ path: `${OUT}/01-landing.png`, fullPage: true });

  // ─── SAHNE 2: Setup wizard — 6 adım kurulum ──────────────
  narrate(2, 'Setup wizard — "Docker Compose tek komut, 6 adımda admin"');
  await page.goto(`${BACKEND}/setup`, { waitUntil: 'domcontentloaded' });
  await pause(page, 5000, '6 step indicator + completed state');
  await page.screenshot({ path: `${OUT}/02-setup-completed.png`, fullPage: true });

  // ─── SAHNE 3: Login + Panel ───────────────────────────────
  narrate(3, 'Admin login — "tek tıkla panel"');
  await page.goto(`${BACKEND}/panel/login`, { waitUntil: 'domcontentloaded' });
  await pause(page, 3000, 'login form');
  await page.locator('#email').fill('admin@demo-acme.local');
  await pause(page, 1500, 'email');
  await page.locator('#password').fill('LocalPass2026!');
  await pause(page, 1500, 'password');
  await page.locator('#submit-btn').click();
  await pause(page, 4000, 'panel render');
  await page.screenshot({ path: `${OUT}/03-panel.png`, fullPage: true });

  // ─── SAHNE 4: MCP Tool Inventory — 122 tool ──────────────
  narrate(4, 'MCP envanter — "100+ tool, hepsi hazır"');
  await page.goto(`${BACKEND}/v1/panel/tools`, { waitUntil: 'domcontentloaded' });
  await pause(page, 6000, 'JSON tool listesi — vaad 100+, gerçek 122');
  await page.screenshot({ path: `${OUT}/04-mcp-tools.png` });

  // ─── SAHNE 5: Marketplace — 5 plugin ─────────────────────
  narrate(5, 'Plugin marketplace — "5 referans plugin, cosign signed"');
  await page.goto(`${LANDING}/admin/marketplace`, { waitUntil: 'domcontentloaded' });
  await pause(page, 5000, 'plugin galerisi');
  await page.mouse.wheel(0, 400);
  await pause(page, 4000, 'detay');
  await page.screenshot({ path: `${OUT}/05-marketplace.png`, fullPage: true });

  // ─── SAHNE 6: Workflow Builder — NL graph ────────────────
  narrate(6, 'Workflow builder — "doğal dil → graph → execute"');
  await page.goto(`${LANDING}/admin/workflow-builder`, { waitUntil: 'domcontentloaded' });
  await pause(page, 6000, '4-node graph + Synthesize/Dry run/Save');
  await page.screenshot({ path: `${OUT}/06-workflow.png`, fullPage: true });

  // ─── SAHNE 7: Meetings — Coqui TTS + WhisperX ────────────
  narrate(7, 'Meetings & transcription — "free-tier audio stack"');
  await page.goto(`${LANDING}/panel/meetings`, { waitUntil: 'domcontentloaded' });
  await pause(page, 5000, 'meeting list + upload form');
  await page.screenshot({ path: `${OUT}/07-meetings.png`, fullPage: true });
  await page.goto(`${LANDING}/panel/transcription`, { waitUntil: 'domcontentloaded' });
  await pause(page, 4000, 'transcription panel');
  await page.screenshot({ path: `${OUT}/08-transcription.png`, fullPage: true });

  // ─── SAHNE 8: Quota tracker — Customer promise live ──────
  narrate(8, 'Quota — "Claude Plus + 5 free, real-time"');
  await page.goto(`${LANDING}/panel/quota`, { waitUntil: 'domcontentloaded' });
  await pause(page, 6000, 'quota bar — Claude Plus + Groq/Gemini/Cerebras/Cohere/CF');
  await page.screenshot({ path: `${OUT}/09-quota.png`, fullPage: true });

  // ─── SAHNE 9: Quality metrics ────────────────────────────
  narrate(9, 'Q1 metrics — "16s warm-boot, 0/8000 flake, p95<12ms"');
  await page.goto(`${BACKEND}/v1/system/quota_status`, { waitUntil: 'domcontentloaded' });
  await pause(page, 5000, 'JSON quota status — kalite kanıtı');
  await page.screenshot({ path: `${OUT}/10-quota-api.png` });

  // ─── SAHNE 10: Final ─────────────────────────────────────
  narrate(10, 'Kapanış — "demo bitti, sorularınızı bekliyoruz"');
  await page.goto(`${LANDING}/`, { waitUntil: 'domcontentloaded' });
  await pause(page, 5000, 'final screen — landing tepe');
  await page.screenshot({ path: `${OUT}/11-final.png`, fullPage: true });

  log('✅ Demo akışı tamamlandı');
  log(`📸 Screenshot: ${OUT}/`);
  log(`Toplam süre: ~9 dakika`);

  await pause(page, 3000, 'browser açık kalıyor — kullanıcı Q&A');
  await browser.close();
})().catch((err) => {
  console.error('💥 FAIL:', err);
  process.exit(1);
});
