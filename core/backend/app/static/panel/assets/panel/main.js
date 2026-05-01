// T-R02 — panel ES-module entry point (replaces the legacy IIFE in panel.js).
// Loaded via `<script type="module" src="...panel/main.js">` from index.html.
import { COLORS } from "./constants.js";
import { Sparkline } from "./sparkline.js";
import { sparkInstances } from "./state.js";
import {
  renderQuotaRadar,
  renderDisagreement,
} from "./widgets.js";
import { bindNotif } from "./notif.js";
import {
  bindAnchorNav,
  bindLogout,
  bindSymbolExplorer,
  bindTheme,
  exposeInlineHandlers,
  startClock,
} from "./ui.js";
import { startSSE } from "./sse.js";

document.addEventListener("DOMContentLoaded", () => {
  sparkInstances.deleg = new Sparkline("spark-deleg", COLORS.deleg);
  sparkInstances.gpu = new Sparkline("spark-gpu", COLORS.gpu);
  sparkInstances.cache = new Sparkline("spark-cache", COLORS.cache);

  exposeInlineHandlers();
  startClock();
  bindLogout();
  bindTheme();
  bindAnchorNav();
  bindNotif();
  bindSymbolExplorer();
  startSSE();

  renderQuotaRadar();
  renderDisagreement();
  setInterval(renderQuotaRadar, 30000);
  setInterval(renderDisagreement, 30000);
});
