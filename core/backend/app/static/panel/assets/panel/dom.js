// DOM helpers extracted from the legacy panel.js IIFE.
// All public-DOM mutation in the panel goes through these so we keep the
// "no innerHTML, ever" rule encapsulated.

export function safeParse(txt) {
  try {
    return JSON.parse(txt);
  } catch (e) {
    console.error("JSON parse error:", e);
    return null;
  }
}

export function setText(id, val) {
  const el = document.getElementById(id);
  if (el !== null && val !== undefined && val !== null) {
    el.textContent = String(val);
  }
}

export function clear(el) {
  while (el && el.firstChild) el.removeChild(el.firstChild);
}

export function makeEl(tag, opts) {
  const el = document.createElement(tag);
  if (!opts) return el;
  if (opts.className) el.className = opts.className;
  if (opts.text != null) el.textContent = String(opts.text);
  if (opts.attrs) {
    for (const k of Object.keys(opts.attrs)) {
      el.setAttribute(k, opts.attrs[k]);
    }
  }
  if (opts.dataset) {
    for (const k of Object.keys(opts.dataset)) {
      el.dataset[k] = opts.dataset[k];
    }
  }
  return el;
}

export function setFooterState(msg) {
  setText("footer-stream-state", msg);
}
