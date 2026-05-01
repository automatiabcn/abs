// Annotated Screenshot Tour — her sayfada caption banner overlay
// Cookie trick: backend session cookie'yi frontend domain'e de set et
import { chromium } from '@playwright/test';
import { mkdirSync } from 'node:fs';

const OUT = '/tmp/abs-cj/annotated';
mkdirSync(OUT, { recursive: true });

const BACKEND = 'http://localhost:8000';
const LANDING = 'http://localhost:3000';

const PAGES = [
  {
    url: `${LANDING}/`,
    label: '01-landing',
    caption: '🏠 LANDING — Müşterinin gördüğü ilk sayfa. 100+ MCP tool · cascade · kurulum',
    backend: false,
  },
  {
    url: `${LANDING}/showcase`,
    label: '02-showcase',
    caption: '🎨 SHOWCASE — Tasarım sistemi galerisi (renkler, ikonlar, kartlar) + Pilot/PoC kartları',
    backend: false,
  },
  {
    url: `${BACKEND}/setup`,
    label: '03-setup-wizard',
    caption: '⚙️ SETUP WIZARD — 6 adımda kurulum: Admin → Lisans → Domain → Anthropic → Provider\'lar → Test',
    backend: true,
  },
  {
    url: `${BACKEND}/panel`,
    label: '04-panel-home',
    caption: '🏢 PANEL ANA SAYFA — Sistem genel durumu, MCP envanter, son cascade çağrıları',
    backend: true,
  },
  {
    url: `${BACKEND}/v1/panel/tools`,
    label: '05-mcp-tools',
    caption: '🔧 122+ MCP TOOL ENVANTERİ — Cascade router\'ın seçtiği tüm modeller, JSON API',
    backend: true,
  },
  {
    url: `${BACKEND}/v1/cascade/providers`,
    label: '06-cascade-providers',
    caption: '🌊 CASCADE PROVIDER MATRIX — 6 provider, configured/missing, anthropic_mock_mode',
    backend: true,
  },
  {
    url: `${BACKEND}/v1/system/quota_status`,
    label: '07-quota-api',
    caption: '📊 KOTA API — Claude Plus + 5 ücretsiz provider aylık kullanım, 80%/95% threshold',
    backend: true,
  },
  {
    url: `${BACKEND}/v1/admin/dashboard`,
    label: '08-admin-dashboard',
    caption: '🛡️ ADMIN DASHBOARD — Billing, beta, compliance, audit log özet',
    backend: true,
  },
  {
    url: `${LANDING}/admin/marketplace`,
    label: '09-marketplace',
    caption: '🏪 PLUGIN MARKETPLACE — 5 hazır entegrasyon (Slack, Gmail, Linear, Notion, Postgres) — "Tenant\'a Yükle"',
    backend: false,
  },
  {
    url: `${LANDING}/admin/workflow-builder`,
    label: '10-workflow-builder',
    caption: '🔀 WORKFLOW BUILDER — Doğal dil → JSON workflow → Synthesize → Dry run → Execute',
    backend: false,
    interact: async (page) => {
      const ta = page.locator('textarea').first();
      if (await ta.count() > 0) {
        await ta.fill('Slack #support kanalına yeni mesaj geldiğinde Linear issue oluştur ve sesli özet at');
        await page.waitForTimeout(2000);
      }
    },
  },
  {
    url: `${LANDING}/panel/meetings`,
    label: '11-meetings',
    caption: '🎙️ TOPLANTI YÖNETİMİ — Audio yükle → WhisperX deşifre → aksiyon item → Linear ticket',
    backend: false,
  },
  {
    url: `${LANDING}/panel/transcription`,
    label: '12-transcription',
    caption: '📝 CANLI TRANSKRİPT — Mikrofon kaydı → speaker diarize → JSON/SRT/TXT export',
    backend: false,
  },
  {
    url: `${LANDING}/panel/quota`,
    label: '13-quota-ui',
    caption: '📈 KOTA TAKİBİ — Bar chart 6 provider + 80%/95% threshold + real-time auto-refresh',
    backend: false,
  },
];

function ts() { return new Date().toISOString().slice(11, 19); }
function log(m) { console.log(`[${ts()}] ${m}`); }

async function injectBanner(page, caption) {
  await page.evaluate((cap) => {
    const old = document.getElementById('abs-tour-banner');
    if (old) old.remove();
    const banner = document.createElement('div');
    banner.id = 'abs-tour-banner';
    banner.style.cssText = `
      position: fixed; top: 0; left: 0; right: 0;
      background: linear-gradient(135deg, #1e57ac 0%, #3a9dff 100%);
      color: white; padding: 14px 28px;
      font-family: 'JetBrains Mono', 'SF Mono', monospace;
      font-size: 15px; font-weight: 600;
      z-index: 999999; box-shadow: 0 4px 16px rgba(0,0,0,0.5);
      letter-spacing: 0.02em; line-height: 1.4;
    `;
    banner.textContent = cap;
    document.body.appendChild(banner);
  }, caption);
}

(async () => {
  log('🎬 Annotated Tour başlıyor');

  const browser = await chromium.launch({
    headless: false,
    slowMo: 600,
    args: ['--window-size=1440,900', '--window-position=120,80'],
  });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    ignoreHTTPSErrors: true,
    colorScheme: 'dark',
  });
  const page = await context.newPage();

  // Login (backend) — get session cookie
  log('▶ Login (backend)');
  await page.goto(`${BACKEND}/panel/login`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2500);
  await page.locator('#email').fill('admin@demo-acme.local');
  await page.locator('#password').fill('LocalPass2026!');
  await page.locator('#submit-btn').click();
  await page.waitForTimeout(4000);

  // Cookie copy: backend port 8000 → frontend port 3000 (same hostname)
  const cookies = await context.cookies();
  const sessionCookie = cookies.find((c) => c.name === 'abs_session');
  if (sessionCookie) {
    await context.addCookies([
      {
        name: 'abs_session',
        value: sessionCookie.value,
        domain: 'localhost',
        path: '/',
      },
    ]);
    log('   ✓ session cookie cross-port set');
  }

  // Tour
  for (const [i, p] of PAGES.entries()) {
    log(`▶ ${i + 1}/${PAGES.length} ${p.label}: ${p.caption.slice(0, 60)}...`);
    try {
      await page.goto(p.url, { waitUntil: 'domcontentloaded', timeout: 30000 });
      await page.waitForTimeout(p.backend ? 3000 : 6000); // frontend daha uzun render
      if (p.interact) await p.interact(page);
      await injectBanner(page, p.caption);
      await page.waitForTimeout(1500);
      await page.screenshot({ path: `${OUT}/${p.label}.png`, fullPage: false });
      log(`   📸 ${p.label}.png`);
    } catch (e) {
      log(`   ⚠ ${p.label} fail: ${e.message.slice(0, 80)}`);
    }
  }

  log('✅ Tour tamamlandı');
  log(`📂 ${OUT}/`);
  await page.waitForTimeout(2000);
  await browser.close();
})().catch((err) => {
  console.error('💥 FAIL:', err);
  process.exit(1);
});
