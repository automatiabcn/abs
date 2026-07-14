// UI bindings + clock + symbol explorer extracted from panel.js.
import { clear, makeEl, setText } from "./dom.js";

export function startClock() {
  const el = document.getElementById("clock");
  if (!el) return;
  const tick = () =>
    (el.textContent = new Date().toLocaleTimeString("tr-TR"));
  tick();
  setInterval(tick, 1000);
}

export function bindLogout() {
  const btn = document.getElementById("logout-btn");
  if (!btn) return;
  btn.addEventListener("click", async () => {
    try {
      const r = await fetch("/auth/logout", {
        method: "POST",
        credentials: "same-origin",
      });
      if (r.ok) window.location.href = "/panel/login";
    } catch (e) {
      console.error("Logout error:", e);
    }
  });
}

export function bindTheme() {
  const btn = document.getElementById("theme-toggle");
  const icon = document.getElementById("theme-icon");
  if (!btn) return;
  const apply = (theme) => {
    if (theme === "light") {
      document.documentElement.setAttribute("data-theme", "light");
      if (icon) icon.textContent = "☀";
    } else {
      document.documentElement.removeAttribute("data-theme");
      if (icon) icon.textContent = "🌙";
    }
    try {
      localStorage.setItem("abs-theme", theme);
    } catch (_e) {
      // localStorage may be unavailable; non-fatal.
    }
  };
  let current = "dark";
  try {
    const saved = localStorage.getItem("abs-theme");
    if (saved === "light" || saved === "dark") current = saved;
  } catch (_e) {
    // localStorage may be unavailable; keep default.
  }
  apply(current);
  btn.addEventListener("click", () => {
    current = current === "light" ? "dark" : "light";
    apply(current);
  });
  btn.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      btn.click();
    }
  });
}

export function bindAnchorNav() {
  const nav = document.getElementById("anchor-nav");
  if (!nav) return;
  const links = Array.from(nav.querySelectorAll("a"));
  if (!links.length) return;
  const targets = links
    .map((a) => {
      const id = a.getAttribute("href").replace(/^#/, "");
      const el = document.getElementById(id);
      return el ? { link: a, el } : null;
    })
    .filter(Boolean);
  const setActive = (id) => {
    links.forEach((a) =>
      a.classList.toggle("active", a.getAttribute("href") === "#" + id),
    );
  };
  if ("IntersectionObserver" in window) {
    const io = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (visible) setActive(visible.target.id);
      },
      { rootMargin: "-40% 0px -50% 0px", threshold: [0, 0.25, 0.5] },
    );
    targets.forEach((t) => io.observe(t.el));
  }
}

async function runSymbolQuery() {
  const input = document.getElementById("sym-explorer-input");
  const btn = document.getElementById("sym-explorer-btn");
  const results = document.getElementById("sym-explorer-results");
  const sum = document.getElementById("sym-explorer-summary");
  if (!input || !results) return;
  const q = input.value.trim();
  if (!q) {
    if (sum) sum.textContent = "Sorgu gir (ör. ask_groq)";
    return;
  }
  if (btn) btn.disabled = true;
  if (sum) sum.textContent = "aranıyor…";
  try {
    const r = await fetch(
      "/api/symbol-graph/neighbors?name=" + encodeURIComponent(q),
      { credentials: "same-origin", signal: AbortSignal.timeout(6000) },
    );
    if (!r.ok) throw new Error("HTTP " + r.status);
    const d = await r.json();
    clear(results);
    if (d.status === "empty" || !d.neighbors || !d.neighbors.length) {
      if (sum) sum.textContent = "veri yok (009-rag sonrası)";
      results.appendChild(
        makeEl("div", {
          className: "empty",
          text: d.note || "Henüz veri yok.",
        }),
      );
      return;
    }
    if (sum) {
      sum.textContent =
        d.neighbors.length + " komşu · " + (d.symbol_count || "—") + " sembol";
    }
    d.neighbors.forEach((n) => {
      const row = makeEl("div", { className: "sym-result" });
      row.appendChild(
        makeEl("span", { className: "name", text: n.name || "?" }),
      );
      row.appendChild(
        makeEl("span", { className: "type", text: n.type || "" }),
      );
      row.appendChild(
        makeEl("span", {
          className: "count",
          text: String(n.count == null ? "" : n.count),
        }),
      );
      results.appendChild(row);
    });
  } catch (e) {
    if (sum) sum.textContent = "hata: " + e.message;
  } finally {
    if (btn) btn.disabled = false;
  }
}

export function bindSymbolExplorer() {
  const btn = document.getElementById("sym-explorer-btn");
  const input = document.getElementById("sym-explorer-input");
  if (btn) btn.addEventListener("click", runSymbolQuery);
  if (input) {
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") runSymbolQuery();
    });
  }
  // Defensive: also expose for legacy <button onclick=...>.
  void setText;
}

// Inline-onclick handlers for index.html banners.
function dismissDemoBanner() {
  const banner = document.getElementById("demo-banner");
  if (banner) banner.hidden = true;
  try {
    localStorage.setItem("abs_demo_banner_dismissed_at", String(Date.now()));
  } catch (_e) {
    // localStorage may be unavailable.
  }
}

async function applyUpdate() {
  try {
    const r = await fetch("/v1/update/apply", {
      method: "POST",
      credentials: "include",
    });
    if (!r.ok) {
      alert("Güncelleme başlatılamadı (status " + r.status + ")");
      return;
    }
    alert("Güncelleme istendi. Host'ta `docker compose pull && up -d` çalıştırın.");
  } catch (e) {
    alert("Güncelleme hatası: " + e.message);
  }
}

function dismissUpdateBanner() {
  const banner = document.getElementById("update-banner");
  if (banner) banner.hidden = true;
}

export function exposeInlineHandlers() {
  window.dismissDemoBanner = dismissDemoBanner;
  window.applyUpdate = applyUpdate;
  window.dismissUpdateBanner = dismissUpdateBanner;
}
