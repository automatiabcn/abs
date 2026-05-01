// T-R02 — notification bell extracted from panel.js.
import { clear, makeEl } from "./dom.js";
import { notifState } from "./state.js";

export function renderNotif() {
  const badge = document.getElementById("notif-badge");
  const list = document.getElementById("notif-list");
  if (badge) {
    if (notifState.unread > 0) {
      badge.hidden = false;
      badge.textContent = String(notifState.unread);
    } else {
      badge.hidden = true;
    }
  }
  if (list) {
    clear(list);
    if (!notifState.items.length) {
      list.appendChild(
        makeEl("div", {
          className: "notif-empty",
          text: "Henüz bildirim yok.",
        }),
      );
      return;
    }
    notifState.items.forEach((n) => {
      const item = makeEl("div", {
        className: "notif-item",
        dataset: { kind: n.kind || "info" },
      });
      item.appendChild(
        makeEl("span", { className: "notif-t", text: "[" + n.t + "]" }),
      );
      item.appendChild(document.createTextNode(n.msg));
      list.appendChild(item);
    });
  }
}

export function pushNotif(msg, kind) {
  notifState.items.unshift({
    t: new Date().toLocaleTimeString("tr-TR"),
    msg: String(msg),
    kind: kind || "info",
  });
  if (notifState.items.length > 50) notifState.items.length = 50;
  notifState.unread += 1;
  renderNotif();
}

export function bindNotif() {
  const bell = document.getElementById("notif-bell");
  const panel = document.getElementById("notif-panel");
  const clearBtn = document.getElementById("notif-clear");
  const closeBtn = document.getElementById("notif-close");
  if (!bell || !panel) return;
  const toggle = () => {
    const willOpen = panel.hidden;
    panel.hidden = !willOpen;
    if (willOpen) {
      notifState.unread = 0;
      renderNotif();
    }
  };
  bell.addEventListener("click", toggle);
  bell.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      toggle();
    }
  });
  if (closeBtn) {
    closeBtn.addEventListener("click", () => (panel.hidden = true));
  }
  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      notifState.items = [];
      notifState.unread = 0;
      renderNotif();
    });
  }
  renderNotif();
}
