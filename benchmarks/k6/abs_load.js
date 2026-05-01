// T-059 — k6 load test for ABS Server (5 scenarios: rag/meeting/status/news/email).
// Targets: p99 <500ms overall, 100 RPS sustained 5min, 1000 concurrent ramp,
// error rate <0.1%. Run via:
//   k6 run -e ABS_BASE_URL=https://staging.abs-server.example.com \
//          -e ABS_TOKEN=<bearer> -e ABS_AUDIENCE=abs-mcp benchmarks/k6/abs_load.js

import http from "k6/http";
import { check, sleep } from "k6";
import { Trend, Rate, Counter } from "k6/metrics";

export const ragQueryTrend = new Trend("rag_query_p99");
export const meetingUploadTrend = new Trend("meeting_upload");
export const statusReportTrend = new Trend("status_report");
export const newsDigestTrend = new Trend("news_digest");
export const emailDraftTrend = new Trend("email_draft");
export const errorRate = new Rate("errors");
export const totalRequests = new Counter("total_requests");

export const options = {
  thresholds: {
    http_req_failed: ["rate<0.001"],
    http_req_duration: ["p(99)<500"],
    rag_query_p99: ["p(99)<500"],
    meeting_upload: ["p(99)<2000"],
    status_report: ["p(99)<1500"],
    news_digest: ["p(99)<1000"],
    email_draft: ["p(99)<800"],
    errors: ["rate<0.001"],
  },
  scenarios: {
    smoke: {
      executor: "constant-vus",
      vus: 1,
      duration: "30s",
      tags: { scenario: "smoke" },
    },
    rps_100: {
      executor: "constant-arrival-rate",
      rate: 100,
      timeUnit: "1s",
      duration: "5m",
      preAllocatedVUs: 100,
      maxVUs: 200,
      tags: { scenario: "rps_100" },
      startTime: "30s",
    },
    concurrent_1000: {
      executor: "ramping-vus",
      stages: [
        { duration: "1m", target: 1000 },
        { duration: "2m", target: 1000 },
        { duration: "30s", target: 0 },
      ],
      tags: { scenario: "concurrent_1000" },
      startTime: "5m30s",
    },
  },
  summaryTrendStats: ["min", "avg", "med", "p(95)", "p(99)", "max"],
};

const BASE_URL = __ENV.ABS_BASE_URL || "https://staging.abs-server.example.com";
const AUTH = __ENV.ABS_TOKEN ? `Bearer ${__ENV.ABS_TOKEN}` : "";
const AUDIENCE = __ENV.ABS_AUDIENCE || "abs-mcp";

const HEADERS = {
  ...(AUTH && { Authorization: AUTH }),
  "X-ABS-Audience": AUDIENCE,
  "Content-Type": "application/json",
};

export default function () {
  const rnd = Math.random();
  let res;
  let ok = false;

  if (rnd < 0.4) {
    const body = { query: "What is multi-tenant Cerbos policy?", top_k: 5 };
    res = http.post(`${BASE_URL}/v1/rag/query`, JSON.stringify(body), { headers: HEADERS });
    ok = check(res, { "rag 200": (r) => r.status === 200 });
    ragQueryTrend.add(res.timings.duration);
  } else if (rnd < 0.55) {
    const body = { audio_url: "https://example/audio.wav", language: "en" };
    res = http.post(`${BASE_URL}/v1/meeting/upload`, JSON.stringify(body), { headers: HEADERS });
    ok = check(res, { "meeting 200": (r) => r.status === 200 });
    meetingUploadTrend.add(res.timings.duration);
  } else if (rnd < 0.7) {
    res = http.post(`${BASE_URL}/v1/status-report`, JSON.stringify({}), { headers: HEADERS });
    ok = check(res, { "status 200": (r) => r.status === 200 });
    statusReportTrend.add(res.timings.duration);
  } else if (rnd < 0.85) {
    res = http.post(`${BASE_URL}/v1/news-watcher/digest`, JSON.stringify({}), { headers: HEADERS });
    ok = check(res, { "news 200": (r) => r.status === 200 });
    newsDigestTrend.add(res.timings.duration);
  } else {
    const body = { thread_id: "thr_001", instructions: "polite reply" };
    res = http.post(`${BASE_URL}/v1/email/draft`, JSON.stringify(body), { headers: HEADERS });
    ok = check(res, { "email 200": (r) => r.status === 200 });
    emailDraftTrend.add(res.timings.duration);
  }

  errorRate.add(!ok);
  totalRequests.add(1);
  sleep(0.05 + Math.random() * 0.1);
}

export function handleSummary(data) {
  return {
    stdout: JSON.stringify(data.metrics, null, 2),
    "benchmarks/results/k6_summary.json": JSON.stringify(data, null, 2),
  };
}
