// T-R02 — SSE wiring extracted from panel.js. Handles open/error/event listeners
// and the orchestrator-extension that feeds the vital-signs strip + notifications.
import { safeParse, setFooterState } from "./dom.js";
import { SSE_URL, RECONNECT_DELAY } from "./constants.js";
import { sseState } from "./state.js";
import {
  onMetrics,
  onOrchestrator,
  onCohereUsage,
  onMcpTools,
  onBudget,
  onLicenseStatus,
  onUpdateAvailable,
  renderVital,
} from "./widgets.js";
import { pushNotif } from "./notif.js";

function onOrchestratorExt(d) {
  onOrchestrator(d);
  if (d && d.providers) {
    const byName = {};
    d.providers.forEach((p) => {
      byName[(p.name || "").toLowerCase()] = p;
    });
    renderVital(byName);
    const cohere = byName.cohere;
    if (cohere && cohere.state !== "ok") {
      pushNotif(
        "Cohere sağlayıcısı " + cohere.state + " durumda",
        cohere.state === "down" ? "error" : "warn",
      );
    }
  }
}

export function startSSE() {
  setFooterState("bağlanıyor…");
  try {
    sseState.source = new EventSource(SSE_URL);
  } catch (_e) {
    setFooterState("kopuk");
    return;
  }
  const sse = sseState.source;
  sse.addEventListener("open", () => setFooterState("bağlandı"));
  sse.addEventListener("error", () => {
    setFooterState("kopuk");
    if (sseState.source) sseState.source.close();
    if (sseState.reconnectTimer) clearTimeout(sseState.reconnectTimer);
    sseState.reconnectTimer = setTimeout(startSSE, RECONNECT_DELAY);
  });
  sse.addEventListener("metrics", (e) => onMetrics(safeParse(e.data)));
  sse.addEventListener("orchestrator", (e) =>
    onOrchestratorExt(safeParse(e.data)),
  );
  sse.addEventListener("cohere-usage", (e) => {
    const d = safeParse(e.data);
    onCohereUsage(d);
    if (d && d.warning) {
      pushNotif(d.detail || "Cohere kota uyarısı", "warn");
    }
  });
  sse.addEventListener("mcp-tools", (e) => onMcpTools(safeParse(e.data)));
  sse.addEventListener("budget-today", (e) => onBudget(safeParse(e.data)));
  sse.addEventListener("license-status", (e) =>
    onLicenseStatus(safeParse(e.data)),
  );
  sse.addEventListener("update-available", (e) =>
    onUpdateAvailable(safeParse(e.data)),
  );
}
