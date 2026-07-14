// Setup wizard — state machine + i18n (EN default, TR/ES) controller.

const STEPS = ["admin", "license", "domain", "anthropic", "providers", "test"];

// ---- i18n -----------------------------------------------------------------
// EN is canonical (data-i18n text in index.html). TR/ES applied client-side;
// the picked language is also persisted server-side via /v1/setup/lang.
const I18N = {
  en: {}, // canonical — falls back to the data-i18n text already in the DOM
  tr: {
    tagline: "Kendi sunucunda AI orkestrasyonu", lang_label: "Dil",
    s1: "Yönetici", s2: "Lisans", s3: "Adres", s4: "Premium AI", s5: "Sağlayıcılar", s6: "Test",
    d1: "Giriş hesabını oluşturun", d2: "Opsiyonel — varsayılan ücretsiz katman",
    d3: "IP veya domain, ve SSL", d4: "Opsiyonel — ücretli anahtar",
    d5: "Ücretsiz sağlayıcı anahtarlarınız", d6: "Cevap verebildiğini kanıtlayın",
    rail_foot: "Çalıştırması ücretsiz · ücretli AI opsiyonel · veriniz kendi sunucunuzda kalır",
    of6_1: "Adım 1 / 6", of6_2: "Adım 2 / 6", of6_3: "Adım 3 / 6",
    of6_4: "Adım 4 / 6", of6_5: "Adım 5 / 6", of6_6: "Adım 6 / 6",
    btn_next: "Devam", btn_back: "Geri", btn_run_test: "Testi çalıştır", btn_finish: "Kurulumu Bitir",

    step1_h: "Yönetici hesabınızı oluşturun",
    step1_help: "Panele bu hesapla gireceksiniz. Hesap bu sunucuda kalır — ABS onu hiçbir yere göndermez.",
    f_email: "Email", f_password: "Şifre", pw_hint: "En az 8 karakter.",

    step2_h: "Lisans anahtarı",
    step2_help: "ABS lisanssız da çalışır. Ticari lisans satın aldıysanız anahtarı yapıştırın; almadıysanız devam edin — ücretsiz katman istediğiniz sürece açık kalır.",
    free_license_label: "Lisans anahtarım yok — ücretsiz katmanla devam et",
    free_license_sub: "Her şey çalışır. Lisans, ticari kullanımı ve desteği açar.",
    f_license: "Lisans", license_hint: "Anahtar yapıştırmak için işareti kaldırın.",

    step3_h: "Bu sunucu nereden cevap verecek?",
    step3_help: "ABS'yi dizüstünüzde veya özel bir ağda deniyorsanız IP seçin. İnsanların yazacağı bir adı varsa domain seçin — o zaman ABS onun için sertifika alabilir.",
    f_mode: "Mod", opt_ip: "IP — geliştirme", opt_domain: "Domain",
    f_domain: "Domain", f_ssl: "SSL", opt_internal: "Internal CA", opt_acme: "ACME · Let's Encrypt",
    domain_hint: "Mod Domain olunca etkinleşir.",

    step4_h: "Premium AI",
    step4_help: "ABS tamamen ücretsiz sağlayıcılarla çalışır. Zor soruları Claude cevaplasın istiyorsanız Anthropic anahtarı ekleyin — sonradan panelden eklemek de aynı derecede kolay.",
    free_label: "Ücretsiz başla — sadece ücretsiz sağlayıcılar",
    free_sub: "Groq, Gemini, Cerebras, Cohere ve Cloudflare'ın ücretsiz katmanı var.",
    f_anthropic: "Anthropic anahtarı", paid_hint: "Anthropic anahtarı yapıştırmak için işareti kaldırın.",

    step5_h: "Bir sağlayıcı bağlayın",
    step5_help: "ABS'nin bir soruya cevap verebilmesi için en az bir tanesi gerekir. Hepsine ücretsiz kaydolabilirsiniz ve sonradan panelden değiştirebilirsiniz.",
    p_groq: "En hızlısı · önerilir", p_gemini: "Uzun bağlam, görsel",
    p_cerebras: "Hızlı çıkarım", p_cohere: "Yeniden sıralama, embedding",
    f_cf_id: "Account ID", f_cf_token: "API token",
    prov_hint: "Bir tanesi yeter. Kalanları istediğiniz zaman ekleyin — ABS elindeki her anahtara sırayla düşer.",

    step6_h: "Cevap verebiliyor mu?",
    step6_help: "Verdiğiniz her anahtara gerçek bir istek. Bir anahtar yanlışsa burada öğrenirsiniz — ürüne ilk soruyu sorduğunuzda değil.",
    v_ok_one: "Bir sağlayıcı cevap verdi.", v_ok_many: "sağlayıcı cevap verdi.",
    v_ok_tail: "Bitirmeniz için bu yeterli — ABS sonradan eklediğiniz her anahtara da düşer.",
    v_none: "Hiçbir sağlayıcı cevap vermedi.",
    v_none_tail: "Bitirebilirsiniz, ama sohbet henüz bir soruya cevap veremez. Geri dönüp bir anahtar ekleyin ya da panelde Ayarlar → Sağlayıcılar'dan ekleyin.",
    r_ok: "Cevapladı", r_fail: "Başarısız", r_skipped: "Anahtar yok",
    a_free: "Ücretsiz katman", a_licensed: "Lisanslı", a_free_providers: "Sadece ücretsiz sağlayıcılar",
  },
  es: {
    tagline: "Orquestación de IA autoalojada", lang_label: "Idioma",
    s1: "Administrador", s2: "Licencia", s3: "Dirección", s4: "IA premium", s5: "Proveedores", s6: "Prueba",
    d1: "Cree la cuenta de acceso", d2: "Opcional — plan gratuito por defecto",
    d3: "IP o dominio, y SSL", d4: "Opcional — clave de pago",
    d5: "Sus claves gratuitas", d6: "Compruebe que puede responder",
    rail_foot: "Gratis de ejecutar · IA de pago opcional · sus datos se quedan en su servidor",
    of6_1: "Paso 1 de 6", of6_2: "Paso 2 de 6", of6_3: "Paso 3 de 6",
    of6_4: "Paso 4 de 6", of6_5: "Paso 5 de 6", of6_6: "Paso 6 de 6",
    btn_next: "Continuar", btn_back: "Atrás", btn_run_test: "Ejecutar la prueba", btn_finish: "Finalizar configuración",

    step1_h: "Cree su cuenta de administrador",
    step1_help: "Con esta cuenta iniciará sesión en el panel. Se queda en este servidor — ABS no la envía a ninguna parte.",
    f_email: "Correo electrónico", f_password: "Contraseña", pw_hint: "Al menos 8 caracteres.",

    step2_h: "Clave de licencia",
    step2_help: "ABS funciona sin ella. Pegue una clave solo si compró una licencia comercial; si no, continúe y el plan gratuito seguirá activo todo el tiempo que quiera.",
    free_license_label: "No tengo clave de licencia — continuar con el plan gratuito",
    free_license_sub: "Todo funciona. Una licencia habilita el uso comercial y el soporte.",
    f_license: "Licencia", license_hint: "Desmarque para pegar una clave.",

    step3_h: "¿Desde dónde responderá este servidor?",
    step3_help: "Elija IP si está probando ABS en un portátil o en una red privada. Elija dominio cuando tenga un nombre que la gente escribirá — entonces ABS puede obtener un certificado.",
    f_mode: "Modo", opt_ip: "IP — desarrollo", opt_domain: "Dominio",
    f_domain: "Dominio", f_ssl: "SSL", opt_internal: "Internal CA", opt_acme: "ACME · Let's Encrypt",
    domain_hint: "Se habilita cuando el modo es Dominio.",

    step4_h: "IA premium",
    step4_help: "ABS funciona completamente con proveedores gratuitos. Añada una clave de Anthropic solo si quiere que Claude responda las preguntas difíciles — y podrá añadirla más tarde desde el panel igual de fácil.",
    free_label: "Comenzar gratis — solo proveedores gratuitos",
    free_sub: "Groq, Gemini, Cerebras, Cohere y Cloudflare tienen plan gratuito.",
    f_anthropic: "Clave de Anthropic", paid_hint: "Desmarque para pegar una clave de Anthropic.",

    step5_h: "Conecte un proveedor",
    step5_help: "ABS necesita al menos uno para responder. Todos son gratuitos y puede cambiarlos más tarde desde el panel.",
    p_groq: "El más rápido · recomendado", p_gemini: "Contexto largo, visión",
    p_cerebras: "Inferencia rápida", p_cohere: "Reordenación, embeddings",
    f_cf_id: "ID de cuenta", f_cf_token: "API token",
    prov_hint: "Con uno basta. Añada el resto cuando quiera — ABS recurre a cada clave que tenga.",

    step6_h: "¿Puede responder?",
    step6_help: "Una petición real a cada clave que nos dio. Si una clave es incorrecta, lo descubre aquí — no la primera vez que le pregunte algo al producto.",
    v_ok_one: "Un proveedor respondió.", v_ok_many: "proveedores respondieron.",
    v_ok_tail: "Es suficiente para terminar — ABS también recurrirá a cualquier clave que añada después.",
    v_none: "Ningún proveedor respondió.",
    v_none_tail: "Puede terminar, pero el chat todavía no podrá responder. Vuelva atrás y añada una clave, o añádala en el panel en Ajustes → Proveedores.",
    r_ok: "Respondió", r_fail: "Falló", r_skipped: "Sin clave",
    a_free: "Plan gratuito", a_licensed: "Con licencia", a_free_providers: "Solo proveedores gratuitos",
  },
};

// EN canonical strings captured from the DOM on first load (for switching back).
const EN_BASE = {};
// Strings the test step renders from JS (no DOM node to read the English from).
const EN_RUNTIME = {
  v_ok_one: "One provider answered.", v_ok_many: "providers answered.",
  v_ok_tail: "That is enough to finish — ABS will also fall back to any key you add later.",
  v_none: "No provider answered.",
  v_none_tail: "You can finish, but chat will not be able to answer a question yet. Go back and add a key, or add one in the panel under Settings → Providers.",
  r_ok: "Answered", r_fail: "Failed", r_skipped: "No key",
  a_free: "Free tier", a_licensed: "Licensed", a_free_providers: "Free providers only",
};

let currentLang = "en";

function t(key) {
  const dict = I18N[currentLang] || {};
  return dict[key] !== undefined ? dict[key] : EN_RUNTIME[key] || key;
}

function captureBase() {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.dataset.i18n;
    if (!(key in EN_BASE)) EN_BASE[key] = el.textContent;
  });
}

function applyI18n(lang) {
  currentLang = lang;
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
  paintAnswers();
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

// A finished step shows what it answered ("License · Free tier") in place of its
// blurb, so you can see what you handed the installer without walking back into
// it. The wizard used to forget every answer the moment you left the screen.
// The answer is stored as the function that produces it, not as the string it
// produced: half of these are translated ("Free tier", "Free providers only"),
// and a customer who switches language mid-install would otherwise be left with
// a rail that answers in the language they just left.
const ANSWERS = {};

function recordAnswer(step, resolve) {
  ANSWERS[step] = resolve;
  paintAnswers();
}

function paintAnswers() {
  Object.entries(ANSWERS).forEach(([step, resolve]) => {
    const el = document.querySelector(`[data-answer="${step}"]`);
    if (!el) return;
    const text = resolve();
    el.textContent = text;
    el.hidden = !text;
    const li = document.querySelector(`[data-step-indicator="${step}"]`);
    const desc = li && li.querySelector(".setup-desc");
    if (desc) desc.hidden = Boolean(text);
  });
}

function showError(msg) {
  errBox.textContent = msg;
  errBox.hidden = false;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function formToJson(form) {
  const out = {};
  Array.from(form.elements).forEach((el) => {
    if (!el.name || el.disabled) return;
    const v = el.value;
    if (v !== "" && v !== undefined) out[el.name] = v;
  });
  return out;
}

async function postJson(path, body) {
  const r = await fetch(path, {
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

async function postStep(stepKey, body) {
  return postJson(`/v1/setup/step/${stepKey}`, body);
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
    if (keyRow) keyRow.hidden = checked;
  }
  skip.addEventListener("change", sync);
  sync(); // honor checked-by-default on first paint
}

// Same shape for the license step: a customer without a key is the default case,
// so the box is checked and the field is out of the way until they ask for it.
function initLicenseToggle() {
  const skip = document.getElementById("setup-skip-license");
  if (!skip) return;
  const keyInput = document.getElementById("setup-license-key");
  const keyRow = document.getElementById("setup-license-row");
  function sync() {
    const free = skip.checked;
    if (keyInput) {
      keyInput.required = !free;
      if (free) keyInput.value = "";
    }
    if (keyRow) keyRow.hidden = free;
  }
  skip.addEventListener("change", sync);
  sync();
}

// The server ignores `domain` while the mode is IP, so the field is disabled
// rather than sitting there inviting an entry that goes nowhere.
function initDomainToggle() {
  const mode = document.getElementById("setup-mode");
  const input = document.getElementById("setup-domain");
  const row = document.getElementById("setup-domain-row");
  if (!mode || !input) return;
  function sync() {
    const isDomain = mode.value === "domain";
    input.disabled = !isDomain;
    input.required = isDomain;
    if (!isDomain) input.value = "";
    if (row) row.classList.toggle("is-disabled", !isDomain);
  }
  mode.addEventListener("change", sync);
  sync();
}

async function loadState() {
  try {
    const r = await fetch("/v1/setup/status");
    const data = await r.json();
    if (data.completed) {
      window.location.href = "/login?next=/panel/chat";
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
      const body = formToJson(form);
      const data = await postStep(key, body);
      recordAnswer(_STEP_NUMBER[key], () => summarizeStep(key, body, data));
      showStep(data.current_step);
    } catch (err) {
      showError(err.message);
    }
  });
});

const _STEP_NUMBER = { admin: 1, license: 2, domain: 3, anthropic: 4, providers: 5 };

const PROVIDER_LABELS = {
  anthropic_api_key: "Anthropic (Claude)",
  groq_api_key: "Groq",
  gemini_api_key: "Gemini",
  cerebras_api_key: "Cerebras",
  cohere_api_key: "Cohere",
  cf_api_token: "Cloudflare",
  cf_account_id: "Cloudflare Account",
};

function summarizeStep(key, body, data) {
  if (key === "admin") return body.email || "";
  if (key === "license") return data.tier === "free" ? t("a_free") : t("a_licensed");
  if (key === "domain") return [body.domain || (body.mode || "ip").toUpperCase(), body.ssl_mode].filter(Boolean).join(" · ");
  if (key === "anthropic") return body.anthropic_api_key ? "Anthropic" : t("a_free_providers");
  if (key === "providers") {
    const names = Object.keys(body)
      .filter((f) => f in PROVIDER_LABELS && f !== "cf_account_id")
      .map((f) => PROVIDER_LABELS[f]);
    return names.length ? names.join(", ") : "—";
  }
  return "";
}

// ---- step 6: test, verdict, then finish -----------------------------------
// The test used to run only when you pressed Finish — which also completed the
// wizard, irreversibly. So the moment you learned a key was wrong was the moment
// you could no longer go back and fix it. The dry run is a separate call now.
const STATUS_PILL = { ok: "setup-pill--ok", fail: "setup-pill--fail", skipped: "setup-pill--skipped" };

// XSS-safe: every value goes through textContent, never innerHTML.
function renderTestResults(box, results) {
  box.textContent = "";
  const entries = Object.entries(results || {});
  const list = document.createElement("ul");
  list.className = "setup-test-list";
  for (const [field, res] of entries) {
    const status = (res && res.status) || "skipped";
    const li = document.createElement("li");
    li.className = "setup-res";

    const name = document.createElement("span");
    name.className = "setup-res-name";
    name.textContent = PROVIDER_LABELS[field] || field;
    li.appendChild(name);

    if (res && res.reason) {
      const reason = document.createElement("span");
      reason.className = "setup-res-reason";
      reason.textContent = String(res.reason);
      li.appendChild(reason);
    }

    const pill = document.createElement("span");
    pill.className = `setup-pill ${STATUS_PILL[status] || STATUS_PILL.skipped}`;
    pill.textContent = t(`r_${status}`);
    li.appendChild(pill);

    list.appendChild(li);
  }
  box.appendChild(list);
}

// Whether chat can answer at all is the only thing this step really tests, so it
// is said in a sentence — not left for the customer to infer from a list of ticks.
// With zero working providers the wizard used to print an empty box and let you
// walk straight into a chat that could not answer.
function renderVerdict(box, results) {
  const answered = Object.values(results || {}).filter(
    (r) => r && r.status === "ok",
  ).length;
  box.textContent = "";
  box.className = answered
    ? "setup-verdict setup-verdict--ok"
    : "setup-verdict setup-verdict--warn";

  const strong = document.createElement("b");
  strong.textContent = answered
    ? answered === 1
      ? t("v_ok_one")
      : `${answered} ${t("v_ok_many")}`
    : t("v_none");
  const tail = document.createTextNode(
    " " + (answered ? t("v_ok_tail") : t("v_none_tail")),
  );
  box.appendChild(strong);
  box.appendChild(tail);
  box.hidden = false;
}

const runBtn = document.getElementById("setup-run-test");
const finishBtn = document.querySelector(".setup-finish");

if (runBtn) {
  runBtn.addEventListener("click", async () => {
    runBtn.disabled = true;
    try {
      const data = await postJson("/v1/setup/test", {});
      renderTestResults(
        document.getElementById("setup-test-results"),
        data.test_results,
      );
      renderVerdict(
        document.getElementById("setup-verdict"),
        data.test_results,
      );
      runBtn.hidden = true;
      if (finishBtn) finishBtn.hidden = false;
    } catch (err) {
      showError(err.message);
    } finally {
      runBtn.disabled = false;
    }
  });
}

if (finishBtn) {
  finishBtn.addEventListener("click", async () => {
    finishBtn.disabled = true;
    try {
      const data = await postStep("test", {});
      if (data.completed) {
        window.location.href = "/login?next=/panel/chat";
        return;
      }
    } catch (err) {
      showError(err.message);
    } finally {
      finishBtn.disabled = false;
    }
  });
}

document.querySelectorAll(".setup-back").forEach((btn) => {
  btn.addEventListener("click", () => {
    const cur = Array.from(sections).find((s) => !s.hidden);
    const n = Number(cur.dataset.step);
    if (n > 1) showStep(n - 1);
  });
});

captureBase();
initSkipToggle();
initLicenseToggle();
initDomainToggle();
loadState();
