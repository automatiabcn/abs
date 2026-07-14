// Phase B / W1+W2 regression — estimateCostCents + isValidWorkflow
// must never throw on missing/empty/partial workflow shapes (root cause
// of the runtime crash captured in UX_BUGS_20260501.md W1).

import { describe, expect, it } from "vitest";

import {
  estimateCostCents,
  isValidWorkflow,
  SAMPLE_WORKFLOW,
  type WorkflowDefinition,
} from "@/lib/workflow";

describe("estimateCostCents — defensive", () => {
  it("returns 0 for null", () => {
    expect(estimateCostCents(null)).toBe(0);
  });

  it("returns 0 for undefined", () => {
    expect(estimateCostCents(undefined)).toBe(0);
  });

  it("returns 0 for partial workflow without nodes array", () => {
    expect(
      estimateCostCents({ id: "x", name: "x" } as unknown as WorkflowDefinition),
    ).toBe(0);
  });

  it("returns 0 for workflow with empty nodes array", () => {
    const empty: WorkflowDefinition = {
      ...SAMPLE_WORKFLOW,
      nodes: [],
      edges: [],
    };
    expect(estimateCostCents(empty)).toBe(0);
  });

  it("sums known node-kind costs from SAMPLE_WORKFLOW", () => {
    // SAMPLE_WORKFLOW = 3 abs_tool (1 each) + 1 output (0) = 3 cents
    expect(estimateCostCents(SAMPLE_WORKFLOW)).toBe(3);
  });

  it("ignores unknown node kinds without throwing", () => {
    const wf: WorkflowDefinition = {
      ...SAMPLE_WORKFLOW,
      nodes: [
        // @ts-expect-error — exercising the defensive ?? 0 branch
        { id: "x", kind: "made_up_kind", name: "weird" },
      ],
    };
    expect(estimateCostCents(wf)).toBe(0);
  });
});

describe("isValidWorkflow — schema gate", () => {
  it("accepts SAMPLE_WORKFLOW", () => {
    expect(isValidWorkflow(SAMPLE_WORKFLOW)).toBe(true);
  });

  it("rejects null/undefined/string/number/array", () => {
    expect(isValidWorkflow(null)).toBe(false);
    expect(isValidWorkflow(undefined)).toBe(false);
    expect(isValidWorkflow("oops")).toBe(false);
    expect(isValidWorkflow(42)).toBe(false);
    expect(isValidWorkflow([])).toBe(false);
  });

  it("rejects when trigger is missing", () => {
    const { trigger: _t, ...rest } = SAMPLE_WORKFLOW;
    expect(isValidWorkflow(rest)).toBe(false);
  });

  it("rejects when nodes is not an array", () => {
    const broken = { ...SAMPLE_WORKFLOW, nodes: "boom" };
    expect(isValidWorkflow(broken)).toBe(false);
  });

  it("rejects when edges is not an array", () => {
    const broken = { ...SAMPLE_WORKFLOW, edges: null };
    expect(isValidWorkflow(broken)).toBe(false);
  });

  it("rejects empty object (covers 'cascade returned {}' bug)", () => {
    expect(isValidWorkflow({})).toBe(false);
  });
});
