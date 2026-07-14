// Shared mutable state singletons for the panel.
// Modules that touch SSE / spark instances / notifications import from here.

export const sseState = {
  source: null,
  reconnectTimer: null,
};

export const logBuffer = [];

export const notifState = { items: [], unread: 0 };

// Sparkline instances are allocated by main.js at DOMContentLoaded so the
// canvas elements exist. Other modules read sparkInstances.deleg etc.
export const sparkInstances = {
  deleg: null,
  gpu: null,
  cache: null,
};
