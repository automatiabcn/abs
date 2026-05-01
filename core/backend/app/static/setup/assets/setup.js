// 012 — Setup wizard 6-step state machine UI controller (vanilla JS)

const STEPS = ["admin", "license", "domain", "anthropic", "providers", "test"];

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

async function loadState() {
  try {
    const r = await fetch("/v1/setup/status");
    const data = await r.json();
    if (data.completed) {
      window.location.href = "/panel/login";
      return;
    }
    showStep(data.current_step || 1);
  } catch (e) {
    showError("Setup durumu okunamadi: " + e.message);
  }
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
    throw new Error(j.detail || `HTTP ${r.status}`);
  }
  return r.json();
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

document.querySelector(".setup-finish").addEventListener("click", async () => {
  try {
    const data = await postStep("test", {});
    const box = document.getElementById("setup-test-results");
    box.textContent = JSON.stringify(data.test_results || {}, null, 2);
    if (data.completed) {
      setTimeout(() => (window.location.href = "/panel/login"), 1500);
    }
  } catch (err) {
    showError(err.message);
  }
});

loadState();
