// SSE event handlers + polling renderers extracted from panel.js.
import { clear, makeEl, setText } from "./dom.js";
import { LOG_MAX } from "./constants.js";
import { logBuffer, sparkInstances } from "./state.js";

export function onMetrics(d) {
  if (!d) return;
  setText("h-tasks", d.tasks);
  setText("h-tokens", d.tokens);
  setText("h-savings", d.savings_pct != null ? d.savings_pct + "%" : "—");
  setText("cs-deleg", d.deleg_rate);
  setText("cs-gpu-temp", d.gpu_temp);
  setText("cs-gpu-vram", d.gpu_vram ? "VRAM " + d.gpu_vram : "VRAM —");
  setText("cs-cache-hr", d.cache_hit);
  setText("deleg-rate", d.deleg_rate != null ? "%" + d.deleg_rate : "—");
  setText("deleg-stats", d.deleg_stats || "—");
  if (sparkInstances.deleg) sparkInstances.deleg.push(d.deleg_rate);
  if (sparkInstances.gpu) sparkInstances.gpu.push(d.gpu_temp);
  if (sparkInstances.cache) sparkInstances.cache.push(d.cache_hit);
}

export function onOrchestrator(d) {
  if (!d) return;
  const providers = d.providers || [];

  const grid = document.getElementById("provider-grid");
  if (grid) {
    clear(grid);
    providers.forEach((p) => {
      const card = makeEl("div", {
        className: "provider-card",
        attrs: { role: "listitem" },
        dataset: { state: p.state || "unknown" },
      });
      card.appendChild(makeEl("div", { className: "name", text: p.name }));
      card.appendChild(
        makeEl("div", {
          className: "meta",
          text: p.latency_ms != null ? p.latency_ms + " ms" : "—",
        }),
      );
      grid.appendChild(card);
    });
  }

  const dots = document.getElementById("cs-provider-dots");
  if (dots) {
    clear(dots);
    providers.forEach((p) => {
      dots.appendChild(
        makeEl("span", {
          className: "dot",
          text: p.name,
          dataset: { state: p.state || "unknown" },
          attrs: { role: "listitem" },
        }),
      );
    });
  }
  const okCount = providers.filter((p) => p.state === "ok").length;
  setText("cs-provider-sub", okCount + "/" + providers.length + " ok");

  const events = d.events || [];
  const logEl = document.getElementById("cs-log");
  if (logEl && events.length) {
    events.forEach((ev) => {
      const line = makeEl("div", { className: "ev" });
      line.appendChild(
        makeEl("span", { className: "t", text: "[" + (ev.t || "") + "]" }),
      );
      line.appendChild(document.createTextNode(ev.msg || ""));
      logBuffer.unshift(line);
    });
    while (logBuffer.length > LOG_MAX) logBuffer.pop();
    clear(logEl);
    logBuffer.forEach((node) => logEl.appendChild(node.cloneNode(true)));
  }

  if (d.judge) {
    const sum = d.judge.score != null
      ? d.judge.score + " / 10 · " + (d.judge.summary || "")
      : d.judge.summary || "—";
    setText("judge-summary", sum);
    setText("judge-body", d.judge.body || "");
  }
}

export function onCohereUsage(d) {
  if (!d) return;
  setText("cs-cohere-count", d.count);
  const fill = document.getElementById("cs-cohere-fill");
  if (fill && d.limit) {
    fill.style.width = Math.min(100, (d.count / d.limit) * 100) + "%";
  }
  const banner = document.getElementById("cohere-alert-banner");
  if (banner) banner.hidden = !d.warning;
  setText("cohere-alert-detail", d.detail || "");
}

export function onMcpTools(d) {
  if (!d) return;
  const tools = d.tools || [];
  const grid = document.getElementById("feat-grid");
  if (grid) {
    clear(grid);
    tools.forEach((t) => {
      const div = makeEl("div", {
        className: "feat",
        attrs: { role: "listitem" },
      });
      div.appendChild(makeEl("span", { className: "n", text: t.name }));
      div.appendChild(makeEl("span", { className: "v", text: t.count_24h }));
      grid.appendChild(div);
    });
  }
  setText("feat-summary", tools.length + " tool aktif");
  setText("feat-trend-total", (d.total_24h || 0) + " aksiyon/24s");
}

export function onBudget(d) {
  if (!d) return;
  if (typeof d.today_usd === "number") {
    setText("cs-budget-usd", d.today_usd.toFixed(2));
    setText("v8-budget-stat", d.today_usd.toFixed(2));
  }
  if (typeof d.projected_monthly_usd === "number") {
    setText(
      "v8-budget-proj",
      "Tahmini ay sonu: $" + d.projected_monthly_usd.toFixed(2),
    );
    setText("cs-budget-sub", "Proj. $" + d.projected_monthly_usd.toFixed(0));
  }
  setText("v8-learnings-stat", d.learnings_count);
  setText(
    "deleg-budget",
    d.today_usd != null ? "Bütçe: $" + d.today_usd.toFixed(2) : "Bütçe: —",
  );

  const wf = d.workflow;
  if (wf) {
    setText("wf-detail-summary", wf.summary || "—");
    const list = document.getElementById("wf-detail-list");
    if (list) {
      clear(list);
      (wf.items || []).forEach((it) => {
        const line = makeEl("div", {
          className: "ev",
          dataset: { status: it.status || "" },
          text:
            (it.id || "-") +
            " · " +
            (it.status || "?") +
            " · " +
            (it.step || "-"),
        });
        list.appendChild(line);
      });
    }
  }
}

export function renderVital(providersByName) {
  const dots = document.querySelectorAll("#vital-dots .vital-item");
  let ok = 0;
  const total = dots.length;
  dots.forEach((el) => {
    const key = el.dataset.key;
    let state = "unknown";
    if (key === "backend" || key === "stream") state = "ok";
    else if (providersByName && providersByName[key]) {
      state = providersByName[key].state || "unknown";
    }
    el.dataset.state = state;
    if (state === "ok") ok += 1;
  });
  const overall = document.getElementById("vital-overall-dot");
  const label = document.getElementById("vital-overall-label");
  const sub = document.getElementById("vital-overall-sub");
  let state = "ok";
  if (ok < total) state = ok >= total - 2 ? "warn" : "down";
  if (overall) overall.dataset.state = state;
  if (label) {
    label.textContent =
      state === "ok"
        ? "TÜM SİSTEMLER SAĞLIKLI"
        : state === "warn"
          ? "KISITLI İŞLEYİŞ"
          : "BOZUK SERVİSLER";
  }
  if (sub) sub.textContent = ok + "/" + total + " OK";
  setText("vital-updated", new Date().toLocaleTimeString("tr-TR"));
}

export async function renderQuotaRadar() {
  const grid = document.getElementById("quota-radar-grid");
  const dayEl = document.getElementById("quota-radar-day");
  if (!grid) return;
  try {
    const r = await fetch("/api/quota-status", {
      credentials: "same-origin",
      signal: AbortSignal.timeout(5000),
    });
    if (!r.ok) throw new Error("HTTP " + r.status);
    const d = await r.json();
    clear(grid);
    const providers = d.providers || {};
    Object.keys(providers).forEach((key) => {
      const p = providers[key];
      const pct = Number(p.pct) || 0;
      const state = pct >= 90 ? "full" : pct >= 70 ? "warn" : "ok";
      const cell = makeEl("div", {
        className: "quota-cell",
        dataset: { state, provider: key },
      });
      cell.appendChild(makeEl("div", { className: "q-name", text: key }));
      const bar = makeEl("div", { className: "q-bar" });
      bar.appendChild(
        makeEl("div", {
          className: "q-fill",
          attrs: { style: "width:" + Math.min(100, pct) + "%" },
        }),
      );
      cell.appendChild(bar);
      const limitTxt = p.limit == null ? "—" : String(p.limit);
      cell.appendChild(
        makeEl("div", {
          className: "q-text",
          text: (p.used || 0) + " / " + limitTxt + " (" + pct + "%)",
        }),
      );
      grid.appendChild(cell);
    });
    if (dayEl && d.updated_at) {
      const t = new Date(d.updated_at);
      dayEl.textContent = t.toLocaleTimeString("tr-TR");
    }
  } catch (_e) {
    // silent — will retry on next poll tick
  }
}

export async function renderDisagreement() {
  const body = document.getElementById("disagree-body");
  const sum = document.getElementById("disagree-summary");
  if (!body) return;
  try {
    const r = await fetch("/api/disagreement/latest", {
      credentials: "same-origin",
      signal: AbortSignal.timeout(5000),
    });
    if (!r.ok) throw new Error("HTTP " + r.status);
    const d = await r.json();
    clear(body);
    if (d.status === "empty" || !d.models || !d.models.length) {
      if (sum) sum.textContent = "henüz ask_disagree çağrılmadı";
      const empty = makeEl("div", {
        className: "empty",
        text: d.note || "Henüz veri yok.",
      });
      body.appendChild(empty);
      return;
    }
    if (sum) {
      sum.textContent =
        "skor " +
        (d.consensus_score != null ? d.consensus_score.toFixed(2) : "—") +
        " · " +
        d.models.length +
        " model";
    }
    (d.matrix || []).forEach((row) => {
      const line = makeEl("div", {
        className: "ev",
        text: JSON.stringify(row),
      });
      body.appendChild(line);
    });
  } catch (_e) {
    if (sum) sum.textContent = "bağlantı hatası";
  }
}

export function onLicenseStatus(d) {
  const banner = document.getElementById("demo-banner");
  if (!banner || !d) return;
  if (d.license_active) {
    banner.hidden = true;
    return;
  }
  if (!d.demo_active) {
    banner.hidden = false;
    banner.classList.remove("demo-warn");
    banner.classList.add("demo-danger");
    const days = document.getElementById("demo-days");
    if (days) days.textContent = "0";
    return;
  }
  banner.hidden = false;
  const days = d.demo_days_remaining ?? 14;
  const daysEl = document.getElementById("demo-days");
  if (daysEl) daysEl.textContent = days;
  banner.classList.toggle("demo-warn", days <= 7 && days > 3);
  banner.classList.toggle("demo-danger", days <= 3);
}

export function onUpdateAvailable(d) {
  const banner = document.getElementById("update-banner");
  if (!banner || !d) return;
  if (d.state === "current" || d.state === "unknown") {
    banner.hidden = true;
    return;
  }
  banner.hidden = false;
  banner.classList.toggle("update-critical", d.state === "critical");
  const ver = document.getElementById("update-version");
  const sum = document.getElementById("update-summary");
  if (ver) ver.textContent = d.latest || "—";
  if (sum) sum.textContent = d.changelog_summary || "";
}
