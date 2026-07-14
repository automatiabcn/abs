#!/usr/bin/env node
/**
 * Bundle code-split BREAK-EVEN VALIDATOR
 *
 * Re-evaluates each `next/dynamic` decision under throttled-network
 * conditions. Slow 3G (RTT 400ms / 400 KB/s) makes added round trips
 * dominate byte savings — this script reports per-profile delta.
 *
 *   delta_t = -savedBytes / throughput  +  extraRTTs * RTT
 *
 * Usage:
 *   node scripts/validate_bundle_split.js                # full audit
 *   node scripts/validate_bundle_split.js --json         # machine-readable
 */

const NETWORK_PROFILES = {
  slow3G: { label: 'Slow 3G',     rttMs: 400, bandwidthKbps: 3200  },
  lte4g:  { label: 'LTE 4G',      rttMs: 100, bandwidthKbps: 12288 },
  fiber:  { label: 'Office fiber',rttMs: 50,  bandwidthKbps: 51200 },
};

const SHIP_THRESHOLD_MS = -50;
const REVERT_THRESHOLD_MS = 50;

function rttBreakEven(savedBytes, bandwidthKbps, extraRTTs, rttMs) {
  const downloadMs = -(savedBytes * 8) / bandwidthKbps;
  const rttPenaltyMs = extraRTTs * rttMs;
  return {
    downloadMs: Number(downloadMs.toFixed(2)),
    rttPenaltyMs,
    totalMs: Number((downloadMs + rttPenaltyMs).toFixed(2)),
  };
}

function verdict(totalMs) {
  if (totalMs < SHIP_THRESHOLD_MS) return 'SHIP';
  if (totalMs > REVERT_THRESHOLD_MS) return 'REVERT';
  return 'NEUTRAL';
}

const SPRINT_21_DECISIONS = [
  {
    commit: '22b47ea',
    faz: 'B',
    label: 'Tremor + Recharts dynamic',
    routes: [
      { route: '/panel',       savedKB: 404, extraRTTs: 1, lcpRelevant: true  },
      { route: '/panel/quota', savedKB: 202, extraRTTs: 1, lcpRelevant: true  },
    ],
  },
  {
    commit: '03f1ca2',
    faz: 'C',
    label: 'Chat client + react-markdown lazy (cascade)',
    routes: [
      { route: '/panel/chat',  savedKB: 487, extraRTTs: 2, lcpRelevant: true  },
    ],
  },
  {
    commit: '4829122',
    faz: 'D',
    label: 'NeuralGraph + CommandPalette ssr:false',
    routes: [
      { route: '/panel (NG)',  savedKB: 0,   extraRTTs: 1, lcpRelevant: false },
    ],
  },
];

function evaluate(decisions = SPRINT_21_DECISIONS) {
  const rows = [];
  for (const d of decisions) {
    for (const r of d.routes) {
      const savedBytes = r.savedKB * 1024;
      for (const [profileKey, profile] of Object.entries(NETWORK_PROFILES)) {
        const m = rttBreakEven(savedBytes, profile.bandwidthKbps, r.extraRTTs, profile.rttMs);
        rows.push({
          commit: d.commit,
          faz: d.faz,
          label: d.label,
          route: r.route,
          profile: profile.label,
          profileKey,
          savedKB: r.savedKB,
          extraRTTs: r.extraRTTs,
          lcpRelevant: r.lcpRelevant,
          ...m,
          verdict: r.lcpRelevant ? verdict(m.totalMs) : 'NON_LCP',
        });
      }
    }
  }
  return rows;
}

function renderMarkdown(rows) {
  const lines = [];
  lines.push('| Commit | Faz | Route | Profile | Saved KB | RTT+ | δ_dl ms | δ_rtt ms | δ_total ms | Verdict |');
  lines.push('|--------|-----|-------|---------|---------:|-----:|--------:|---------:|-----------:|---------|');
  for (const r of rows) {
    lines.push(
      `| ${r.commit} | ${r.faz} | \`${r.route}\` | ${r.profile} | ${r.savedKB} | ${r.extraRTTs} ` +
      `| ${r.downloadMs} | ${r.rttPenaltyMs} | ${r.totalMs} | **${r.verdict}** |`
    );
  }
  return lines.join('\n');
}

function summarize(rows) {
  const perCommit = new Map();
  for (const r of rows) {
    const key = `${r.commit}|${r.faz}|${r.label}`;
    if (!perCommit.has(key)) perCommit.set(key, { ship: 0, revert: 0, neutral: 0, nonLcp: 0 });
    const bucket = perCommit.get(key);
    if (r.verdict === 'SHIP') bucket.ship += 1;
    else if (r.verdict === 'REVERT') bucket.revert += 1;
    else if (r.verdict === 'NEUTRAL') bucket.neutral += 1;
    else bucket.nonLcp += 1;
  }
  return [...perCommit.entries()].map(([k, v]) => {
    const [commit, faz, label] = k.split('|');
    return { commit, faz, label, ...v };
  });
}

if (require.main === module) {
  const args = process.argv.slice(2);
  const rows = evaluate();
  if (args.includes('--json')) {
    console.log(JSON.stringify({ rows, summary: summarize(rows) }, null, 2));
  } else {
    console.log('Bundle code-split break-even decision matrix');
    console.log('');
    console.log(renderMarkdown(rows));
    console.log('');
    console.log('Per-commit roll-up:');
    for (const s of summarize(rows)) {
      console.log(`  Faz ${s.faz} (${s.commit}) ${s.label}: ` +
        `ship=${s.ship} neutral=${s.neutral} revert=${s.revert} non-lcp=${s.nonLcp}`);
    }
  }
}

module.exports = { rttBreakEven, evaluate, NETWORK_PROFILES, SPRINT_21_DECISIONS };
