import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const STATIC_DIR = resolve(__dirname, "../../backend/app/static/panel");

const TOOLS_HTML = readFileSync(`${STATIC_DIR}/tools.html`, "utf-8");
const CASCADE_HTML = readFileSync(`${STATIC_DIR}/cascade.html`, "utf-8");
const PIPELINE_HTML = readFileSync(`${STATIC_DIR}/pipeline.html`, "utf-8");

describe("Tool Browser HTML — 033 Modul E", () => {
  it("declares the tool grid + modal testids", () => {
    expect(TOOLS_HTML).toContain('data-testid="tool-grid"');
    expect(TOOLS_HTML).toContain('data-testid="tool-modal"');
  });

  it("fetches /v1/panel/tools and supports search + category chips", () => {
    expect(TOOLS_HTML).toContain("/v1/panel/tools");
    expect(TOOLS_HTML).toContain('id="search"');
    expect(TOOLS_HTML).toContain('id="chips"');
  });
});

describe("Cascade Visualiser HTML — 033 Modul F", () => {
  it("declares the cascade table testid", () => {
    expect(CASCADE_HTML).toContain('data-testid="cascade-table"');
  });

  it("calls /v1/panel/cascade/recent with limit=100 and offers CSV export", () => {
    expect(CASCADE_HTML).toContain("/v1/panel/cascade/recent?limit=100");
    expect(CASCADE_HTML).toContain("Export CSV");
  });
});

describe("Quality Pipeline HTML — 033 Modul H", () => {
  it("declares the pipeline list testid", () => {
    expect(PIPELINE_HTML).toContain('data-testid="pipeline-list"');
  });

  it("calls /v1/panel/pipeline/recent and renders empty state hint", () => {
    expect(PIPELINE_HTML).toContain("/v1/panel/pipeline/recent");
    expect(PIPELINE_HTML).toMatch(/no qual_\* invocations/i);
  });
});
