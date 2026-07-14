// Q12-L17 Round 8 — node:test unit tests for the break-even validator.
// Covers the formula derivation + edge cases that the review
// surfaced (zero bytes, cascade RTTs, fast-network fiber neutrality).
const test = require("node:test");
const assert = require("node:assert/strict");
const {
  rttBreakEven,
  evaluate,
  NETWORK_PROFILES,
  SPRINT_21_DECISIONS,
} = require("../validate_bundle_split.js");

test("rttBreakEven returns negative delta when bytes saved dominate RTT", () => {
  const r = rttBreakEven(404 * 1024, 3200, 1, 400);
  assert.equal(r.rttPenaltyMs, 400);
  assert.ok(r.downloadMs < 0, "downloadMs must be negative (savings)");
  assert.ok(r.totalMs < -50, `expected SHIP delta, got ${r.totalMs}`);
});

test("rttBreakEven returns positive delta when RTT dominates (zero bytes)", () => {
  const r = rttBreakEven(0, 51200, 1, 400);
  assert.equal(r.downloadMs, 0);
  assert.equal(r.totalMs, 400);
});

test("rttBreakEven correctly penalises cascade RTTs", () => {
  const single = rttBreakEven(487 * 1024, 3200, 1, 400);
  const cascade = rttBreakEven(487 * 1024, 3200, 2, 400);
  assert.equal(cascade.rttPenaltyMs - single.rttPenaltyMs, 400);
  assert.ok(cascade.totalMs > single.totalMs, "cascade must be slower");
});

test("rttBreakEven scales linearly with savedBytes", () => {
  const small = rttBreakEven(100 * 1024, 3200, 0, 0);
  const large = rttBreakEven(200 * 1024, 3200, 0, 0);
  // 2x savedBytes → 2x download saving (no RTT confound)
  assert.ok(Math.abs(large.downloadMs * 0.5 - small.downloadMs) < 0.5);
});

test("Evaluation covers all 4 decisions × 3 profiles = 12 rows", () => {
  const rows = evaluate(SPRINT_21_DECISIONS);
  assert.equal(rows.length, 12, `unexpected row count ${rows.length}`);
});

test("/panel/quota on the fiber profile is NEUTRAL (the boundary case)", () => {
  const rows = evaluate(SPRINT_21_DECISIONS).filter(
    (r) => r.faz === "B" && r.route === "/panel/quota" && r.profileKey === "fiber",
  );
  assert.equal(rows.length, 1);
  assert.equal(rows[0].verdict, "NEUTRAL", "fiber quota verdict drifted from NEUTRAL");
});

test("Non-LCP routes are NON_LCP (ssr:false defer)", () => {
  const rows = evaluate(SPRINT_21_DECISIONS).filter((r) => r.faz === "D");
  for (const r of rows) {
    assert.equal(r.verdict, "NON_LCP", `Verdict drift on ${r.profileKey}`);
  }
});

test("Slow 3G profile carries 400ms RTT and 3200 kbps bandwidth", () => {
  assert.equal(NETWORK_PROFILES.slow3G.rttMs, 400);
  assert.equal(NETWORK_PROFILES.slow3G.bandwidthKbps, 3200);
});

test("No SHIP verdict regresses to REVERT under any row (regression guard)", () => {
  const rows = evaluate(SPRINT_21_DECISIONS);
  const reverts = rows.filter((r) => r.verdict === "REVERT");
  assert.equal(
    reverts.length,
    0,
    `unexpected REVERT verdict(s): ${JSON.stringify(reverts.map((r) => `${r.faz}/${r.route}/${r.profileKey}`))}`,
  );
});
