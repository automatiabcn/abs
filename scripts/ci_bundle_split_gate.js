#!/usr/bin/env node
// Q12-L17 Round 8 — CI gate: exit non-zero if any code-split decision
// returns a REVERT verdict for the LCP-relevant routes. Wraps
// validate_bundle_split.js for use in `npm run test:bundle-split`
// or as a GitHub Actions step.
const { evaluate } = require("./validate_bundle_split.js");

const rows = evaluate();
const reverts = rows.filter((r) => r.verdict === "REVERT");

if (reverts.length === 0) {
  console.log(`Q12-L17 gate: 0 REVERT verdicts across ${rows.length} rows. PASS`);
  process.exit(0);
}

console.error("Q12-L17 gate: REVERT verdict(s) detected — code-split harms LCP:");
for (const r of reverts) {
  console.error(
    `  - ${r.commit} faz=${r.faz} ${r.route} ${r.profile}: δ=${r.totalMs}ms`,
  );
}
process.exit(1);
