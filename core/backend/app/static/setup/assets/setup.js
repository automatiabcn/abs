// 012/023 — Setup wizard state machine + i18n (EN default, TR/ES) controller.

const STEPS = ["admin", "license", "domain", "anthropic", "providers", "test"];

// ---- i18n -----------------------------------------------------------------
// EN is canonical (data-i18n text in index.html). TR/ES applied client-side;
// the picked language is also persisted server-side via /v1/setup/lang.
const I18N = {
  en: {}, // canonical — falls back to the data-i18n text already in the DOM
  tr: {
    tagline: "Kendi Sunucunda AI Orkestrasyonu", lang_label: "Dil",
    s1: "Yönetici", s2: "Lisans", s3: "Domain", s4: "Premium", s5: "Provider'lar", s6: "Test",
    d1: "Panel giriş hesabını oluşturun", d2: "Lisansı veya demoyu etkinleştirin",
    d3: "IP veya domain + SSL seçin", d4: "Opsiyonel — ücretli AI anahtarı",
    d5: "Ücretsiz sağlayıcı anahtarları", d6: "Her şeyin bağlandığını doğrulayın",
    rail_foot: "Çalıştırması ücretsiz · ücretli AI opsiyonel · kendi sunucunda",
    step1_h: "Yönetici Hesabı", step1_help: "Panel girişini bu hesap kullanacak.",
    f_email: "Email", f_password: "Şifre", btn_next: "İleri", btn_back: "Geri",
    step2_h: "Lisans Anahtarı",
    step2_help: "Email ile aldığınız JWT lisansı yapıştırın. Lisans olmadan demo modu 14 gün aktif kalır.",
    f_license: "Lisans",
    step3_h: "Domain", f_mode: "Mod", opt_ip: "IP (geliştirme)", opt_domain: "Domain",
    f_domain: "Domain (opsiyonel)", f_ssl: "SSL", opt_internal: "Internal CA", opt_acme: "ACME / Let's Encrypt",
    step4_h: "Premium AI (opsiyonel)",
    step4_help: "ABS tamamen ücretsiz sağlayıcılarla çalışır. Premium kalite istemiyorsanız Anthropic (Claude) anahtarı eklemeyin — istediğinizde panel'den ekleyebilirsiniz.",
    free_label: "Ücretsiz başla — sadece ücretsiz sağlayıcıları kullanacağım",
    f_anthropic: "Anthropic Anahtarı",
    step5_h: "Ücretsiz Sağlayıcılar",
    step5_help: "ABS'yi ücretsiz çalıştırırlar. Sahip olduklarınızı ekleyin — hepsi opsiyonel, sonra panel'den düzenlenebilir.",
    f_cf_id: "CloudFlare Account ID", f_cf_token: "CloudFlare API Token",
    step6_h: "Bağlantı Testi",
    step6_help: "Yapılandırılmış her sağlayıcıya hızlı ping atarız; anahtarlarınızın çalışıp çalışmadığını burada görürsünüz.",
    btn_finish: "Kurulumu Bitir",
  },
  es: {
    tagline: "Orquestación de IA autoalojada", lang_label: "Idioma",
    s1: "Administrador", s2: "Licencia", s3: "Dominio", s4: "Premium", s5: "Proveedores", s6: "Prueba",
    d1: "Cree la cuenta de acceso al panel", d2: "Active su licencia o demo",
    d3: "Elija IP o dominio + SSL", d4: "Opcional — clave de IA de pago",
    d5: "Añada sus claves gratuitas", d6: "Verifique que todo conecta",
    rail_foot: "Gratis de ejecutar · IA de pago opcional · autoalojado",
    step1_h: "Cuenta de administrador", step1_help: "Esta cuenta iniciará sesión en el panel.",
    f_email: "Correo electrónico", f_password: "Contraseña", btn_next: "Siguiente", btn_back: "Atrás",
    step2_h: "Clave de licencia",
    step2_help: "Pegue la licencia JWT que recibió por correo electrónico. Sin una licencia, el modo demo permanecerá activo durante 14 días.",
    f_license: "Licencia",
    step3_h: "Dominio", f_mode: "Modo", opt_ip: "IP (desarrollo)", opt_domain: "Dominio",
    f_domain: "Dominio (opcional)", f_ssl: "SSL", opt_internal: "Internal CA", opt_acme: "ACME / Let's Encrypt",
    step4_h: "IA premium (opcional)",
    step4_help: "ABS funciona completamente con proveedores gratuitos. Añada una clave de Anthropic (Claude) solo si desea calidad premium; siempre podrá añadirla más tarde desde el panel.",
    free_label: "Comenzar gratis — usaré solo proveedores gratuitos",
    f_anthropic: "Clave de Anthropic",
    step5_h: "Proveedores gratuitos",
    step5_help: "Estos alimentan ABS sin coste. Añada los que tenga — todos son opcionales y se pueden editar más tarde desde el panel.",
    f_cf_id: "CloudFlare ID de cuenta", f_cf_token: "CloudFlare API Token",
    step6_h: "Prueba de conexión",
    step6_help: "Enviamos un ping rápido a cada proveedor configurado para que vea aquí mismo si sus claves funcionan.",
    btn_finish: "Finalizar configuración",
  },
};

// EN canonical strings captured from the DOM on first load (for switching back).
const EN_BASE = {};

function captureBase() {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.dataset.i18n;
    if (!(key in EN_BASE)) EN_BASE[key] = el.textContent;
  });
}

function applyI18n(lang) {
  const dict = I18N[lang] || {};
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.dataset.i18n;
    const val = dict[key] !== undefined ? dict[key] : EN_BASE[key];
    if (val !== undefined) el.textContent = val;
  });
  document.documentElement.lang = lang;
  document.querySelectorAll(".setup-lang").forEach((b) => {
    b.classList.toggle("active", b.dataset.lang === lang);
  });
}

async function persistLang(lang) {
  try {
    await fetch("/v1/setup/lang", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lang }),
    });
  } catch (_e) {
    /* non-blocking — UI language already applied */
  }
}

function initLangSwitcher(initial) {
  applyI18n(initial);
  document.querySelectorAll(".setup-lang").forEach((btn) => {
    btn.addEventListener("click", () => {
      const lang = btn.dataset.lang;
      applyI18n(lang);
      persistLang(lang);
    });
  });
}

function detectLang(stateLang) {
  if (stateLang && I18N[stateLang]) return stateLang;
  const nav = (navigator.language || "en").slice(0, 2).toLowerCase();
  return I18N[nav] ? nav : "en";
}

// ---- step machine ---------------------------------------------------------
const errBox = document.getElementById("setup-error");
const indicators = document.querySelectorAll("[data-step-indicator]");
const sections = document.querySelectorAll(".setup-step");

function showStep(n) {
  sections.forEach((s) => {
    s.hidden = Number(s.dataset.step) !== n;
  });
  indicators.forEach((li) => {
    const idx = Number(li.dataset.stepIndicator);
    li.classList.toggle("active", idx === n);
    li.classList.toggle("done", idx < n);
  });
  errBox.hidden = true;
}

function showError(msg) {
  errBox.textContent = msg;
  errBox.hidden = false;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function formToJson(form) {
  const out = {};
  Array.from(form.elements).forEach((el) => {
    if (!el.name) return;
    const v = el.value;
    if (v !== "" && v !== undefined) out[el.name] = v;
  });
  return out;
}

async function postStep(stepKey, body) {
  const r = await fetch(`/v1/setup/step/${stepKey}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  if (!r.ok) {
    const j = await r.json().catch(() => ({}));
    const d = j.detail;
    // Structured key-format error: detail = {error, fields:{field: reason}}.
    if (d && typeof d === "object" && d.fields) {
      const lines = Object.entries(d.fields).map(([f, why]) => `• ${f}: ${why}`);
      throw new Error(lines.join("\n"));
    }
    throw new Error((typeof d === "string" && d) || `HTTP ${r.status}`);
  }
  return r.json();
}

// Free-first: skip checkbox starts checked (free path is the default). Toggling
// it reveals the Anthropic key field and makes it required.
function initSkipToggle() {
  const skip = document.getElementById("setup-skip-paid");
  if (!skip) return;
  const hidden = document.querySelector('input[name="skip_paid_providers"]');
  const keyInput = document.getElementById("setup-anthropic-key");
  const keyRow = document.getElementById("setup-anthropic-row");
  function sync() {
    const checked = skip.checked;
    if (hidden) hidden.value = checked ? "true" : "false";
    if (keyInput) {
      keyInput.required = !checked;
      keyInput.minLength = checked ? 0 : 8;
      if (checked) keyInput.value = "";
    }
    if (keyRow) keyRow.style.display = checked ? "none" : "";
  }
  skip.addEventListener("change", sync);
  sync(); // honor checked-by-default on first paint
}

async function loadState() {
  try {
    const r = await fetch("/v1/setup/status");
    const data = await r.json();
    if (data.completed) {
      window.location.href = "/panel/login";
      return;
    }
    initLangSwitcher(detectLang(data.lang));
    showStep(data.current_step || 1);
  } catch (e) {
    initLangSwitcher(detectLang(null));
    showError("Setup status could not be read: " + e.message);
  }
}

document.querySelectorAll("form[data-step-key]").forEach((form) => {
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const key = form.dataset.stepKey;
    try {
      const data = await postStep(key, formToJson(form));
      showStep(data.current_step);
    } catch (err) {
      showError(err.message);
    }
  });
});

document.querySelectorAll(".setup-back").forEach((btn) => {
  btn.addEventListener("click", () => {
    const cur = Array.from(sections).find((s) => !s.hidden);
    const n = Number(cur.dataset.step);
    if (n > 1) showStep(n - 1);
  });
});

// Human-readable provider field labels for the test step (was raw JSON).
const PROVIDER_LABELS = {
  anthropic_api_key: "Anthropic (Claude)",
  groq_api_key: "Groq",
  gemini_api_key: "Gemini",
  cerebras_api_key: "Cerebras",
  cohere_api_key: "Cohere",
  cf_api_token: "Cloudflare",
  cf_account_id: "Cloudflare Account",
};
const STATUS_STYLE = {
  ok: { icon: "✓", color: "#16a34a" },
  fail: { icon: "✗", color: "#dc2626" },
  skipped: { icon: "–", color: "#9ca3af" },
};

// Render the per-provider ping result as a readable list instead of raw JSON.
// XSS-safe: every value goes through textContent, never innerHTML.
function renderTestResults(box, results) {
  box.textContent = "";
  const entries = Object.entries(results || {});
  if (entries.length === 0) {
    const empty = document.createElement("p");
    empty.className = "setup-help";
    empty.textContent = "Test edilecek yapılandırılmış sağlayıcı yok.";
    box.appendChild(empty);
    return;
  }
  const list = document.createElement("ul");
  list.className = "setup-test-list";
  for (const [field, res] of entries) {
    const status = (res && res.status) || "skipped";
    const style = STATUS_STYLE[status] || STATUS_STYLE.skipped;
    const li = document.createElement("li");
    li.style.display = "flex";
    li.style.alignItems = "baseline";
    li.style.gap = "8px";
    li.style.padding = "4px 0";

    const dot = document.createElement("span");
    dot.textContent = style.icon;
    dot.style.color = style.color;
    dot.style.fontWeight = "700";

    const name = document.createElement("span");
    name.textContent = PROVIDER_LABELS[field] || field;
    name.style.fontWeight = "600";

    li.appendChild(dot);
    li.appendChild(name);
    if (res && res.reason) {
      const reason = document.createElement("span");
      reason.textContent = "— " + String(res.reason);
      reason.style.color = "#9ca3af";
      reason.style.fontSize = "12px";
      li.appendChild(reason);
    }
    list.appendChild(li);
  }
  box.appendChild(list);
}

document.querySelector(".setup-finish").addEventListener("click", async () => {
  try {
    const data = await postStep("test", {});
    renderTestResults(
      document.getElementById("setup-test-results"),
      data.test_results,
    );
    if (data.completed) {
      setTimeout(() => (window.location.href = "/panel/login"), 1500);
    }
  } catch (err) {
    showError(err.message);
  }
});

captureBase();
initSkipToggle();
loadState();
