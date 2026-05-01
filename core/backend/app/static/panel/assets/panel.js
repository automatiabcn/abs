// T-R02 — back-compat shim. The legacy 788-line IIFE was split into ES
// modules under `./panel/`. index.html now loads `panel/main.js` directly
// via `<script type="module">`; this file remains so any external bookmark
// or cached deep link still resolves to a working entry point.
import "./panel/main.js";
