import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import WorkflowChatPanel from "@/components/WorkflowChatPanel";
import { SAMPLE_WORKFLOW, type WorkflowDefinition } from "@/lib/workflow";

const MUTATED_WORKFLOW: WorkflowDefinition = {
  ...SAMPLE_WORKFLOW,
  id: "mutated",
  name: "Mutated workflow",
  nodes: [
    ...SAMPLE_WORKFLOW.nodes,
    {
      id: "node-5",
      kind: "abs_tool",
      name: "Notify ops",
      config: { tool_name: "abs.gmail_send" },
    },
  ],
  edges: [
    ...SAMPLE_WORKFLOW.edges,
    { source: "node-4", target: "node-5", kind: "success" },
  ],
};

describe("WorkflowChatPanel", () => {
  it("renders the canvas title and 4 sample nodes", () => {
    render(<WorkflowChatPanel initialWorkflow={SAMPLE_WORKFLOW} isAdmin={true} />);
    expect(screen.getByTestId("workflow-canvas-title")).toHaveTextContent(
      "RAG-grounded customer chat",
    );
    for (const id of ["node-1", "node-2", "node-3", "node-4"]) {
      expect(screen.getByTestId(`workflow-node-${id}`)).toBeInTheDocument();
    }
  });

  it("renders intent textarea and synthesize button", () => {
    render(<WorkflowChatPanel initialWorkflow={SAMPLE_WORKFLOW} isAdmin={true} />);
    expect(screen.getByTestId("intent-textarea")).toBeInTheDocument();
    expect(screen.getByTestId("synthesize-button")).toBeInTheDocument();
  });

  it("cost preview renders a $ amount", () => {
    render(<WorkflowChatPanel initialWorkflow={SAMPLE_WORKFLOW} isAdmin={true} />);
    expect(screen.getByTestId("cost-preview").textContent).toMatch(/\$\d+\.\d{2}/);
  });

  it("synthesize is disabled while intent is empty", () => {
    render(<WorkflowChatPanel initialWorkflow={SAMPLE_WORKFLOW} isAdmin={true} />);
    expect(screen.getByTestId("synthesize-button")).toBeDisabled();
  });

  it("synthesize calls synthesizeFn and updates the canvas", async () => {
    const synth = vi.fn(async (_intent: string, _current?: unknown) => MUTATED_WORKFLOW);
    render(
      <WorkflowChatPanel
        initialWorkflow={SAMPLE_WORKFLOW}
        isAdmin={true}
        synthesizeFn={synth}
      />,
    );
    fireEvent.change(screen.getByTestId("intent-textarea"), {
      target: { value: "Add a notify-ops step" },
    });
    fireEvent.click(screen.getByTestId("synthesize-button"));
    await waitFor(() => {
      expect(synth).toHaveBeenCalledTimes(1);
      expect(screen.getByTestId("workflow-node-node-5")).toBeInTheDocument();
      expect(screen.getByTestId("workflow-canvas-title")).toHaveTextContent(
        "Mutated workflow",
      );
    });
  });

  it("surfaces synthesize error in the banner", async () => {
    const synth = vi.fn(async () => {
      throw new Error("boom");
    });
    render(
      <WorkflowChatPanel
        initialWorkflow={SAMPLE_WORKFLOW}
        isAdmin={true}
        synthesizeFn={synth}
      />,
    );
    fireEvent.change(screen.getByTestId("intent-textarea"), {
      target: { value: "fail me on purpose please" },
    });
    fireEvent.click(screen.getByTestId("synthesize-button"));
    await waitFor(() => {
      expect(screen.getByTestId("synthesize-error")).toHaveTextContent("boom");
    });
  });

  it("dry-run sets status to Success when onDryRun resolves ok", async () => {
    const onDryRun = vi.fn(async () => ({ ok: true }));
    render(
      <WorkflowChatPanel
        initialWorkflow={SAMPLE_WORKFLOW}
        isAdmin={true}
        onDryRun={onDryRun}
      />,
    );
    fireEvent.click(screen.getByTestId("dry-run-button"));
    await waitFor(() => {
      // Polish round R4 — admin console is Turkish-first.
      expect(screen.getByTestId("dry-run-status")).toHaveTextContent("Başarılı");
    });
    expect(onDryRun).toHaveBeenCalled();
  });

  it("save button fires onSave with the current workflow", () => {
    const onSave = vi.fn();
    render(
      <WorkflowChatPanel
        initialWorkflow={SAMPLE_WORKFLOW}
        isAdmin={true}
        onSave={onSave}
      />,
    );
    fireEvent.click(screen.getByTestId("save-button"));
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({ id: SAMPLE_WORKFLOW.id }),
    );
  });

  it("refine button calls synthesizeFn with the refine text", async () => {
    const synth = vi.fn(async (_intent: string, _current?: unknown) => MUTATED_WORKFLOW);
    render(
      <WorkflowChatPanel
        initialWorkflow={SAMPLE_WORKFLOW}
        isAdmin={true}
        synthesizeFn={synth}
      />,
    );
    fireEvent.change(screen.getByTestId("refine-textarea"), {
      target: { value: "Add an HITL step before sending" },
    });
    fireEvent.click(screen.getByTestId("refine-button"));
    await waitFor(() => {
      expect(synth).toHaveBeenCalledTimes(1);
      expect(synth.mock.calls[0][0]).toContain("HITL step");
    });
  });

  it("save and dry-run are disabled when isAdmin=false", () => {
    render(<WorkflowChatPanel initialWorkflow={SAMPLE_WORKFLOW} isAdmin={false} />);
    expect(screen.getByTestId("save-button")).toBeDisabled();
    expect(screen.getByTestId("dry-run-button")).toBeDisabled();
  });

  it("default synthesize unwraps the {workflow} envelope (no false 'load sample')", async () => {
    // Regression: defaultSynthesize used to cast the whole SynthesizeResponse
    // envelope as the workflow, so isValidWorkflow always failed and the panel
    // showed the "örnek şablon yükle" CTA even on a good synthesis.
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        workflow: MUTATED_WORKFLOW,
        explanation: "LLM-synthesised",
        warnings: [],
        revisions: 0,
        source: "llm",
      }),
    }));
    vi.stubGlobal("fetch", fetchMock as unknown as typeof fetch);
    try {
      // No synthesizeFn → exercises the real defaultSynthesize fetch path.
      render(<WorkflowChatPanel initialWorkflow={SAMPLE_WORKFLOW} isAdmin={true} />);
      fireEvent.change(screen.getByTestId("intent-textarea"), {
        target: { value: "Add a notify-ops step to the workflow" },
      });
      fireEvent.click(screen.getByTestId("synthesize-button"));
      await waitFor(() => {
        expect(screen.getByTestId("workflow-canvas-title")).toHaveTextContent(
          "Mutated workflow",
        );
      });
      expect(screen.queryByTestId("synthesize-error")).not.toBeInTheDocument();
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("run button is present and dry-run hits the backend execute endpoint", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (typeof url === "string" && url.includes("/v1/workflows/definitions")) {
        return { ok: true, status: 200, json: async () => ({ workflows: [] }) };
      }
      // /v1/workflows/execute (dry_run)
      return {
        ok: true,
        status: 200,
        json: async () => ({
          status: "dry_run_ok",
          steps: [
            { step: 1, node_id: "node-1", kind: "abs_tool", name: "Policy", estimate_s: 0.6 },
            { step: 2, node_id: "node-2", kind: "abs_tool", name: "RAG", estimate_s: 0.6 },
          ],
          estimate_s: 1.2,
          estimated_cost_usd: 0,
        }),
      };
    });
    vi.stubGlobal("fetch", fetchMock as unknown as typeof fetch);
    try {
      render(<WorkflowChatPanel initialWorkflow={SAMPLE_WORKFLOW} isAdmin={true} />);
      expect(screen.getByTestId("run-button")).toBeInTheDocument();
      fireEvent.click(screen.getByTestId("dry-run-button"));
      await waitFor(() => {
        expect(screen.getByTestId("dry-run-status")).toHaveTextContent("Başarılı");
        expect(screen.getByTestId("run-result")).toHaveTextContent("2 adım");
      });
      expect(
        fetchMock.mock.calls.some(
          (c) =>
            typeof c[0] === "string" && (c[0] as string).includes("/v1/workflows/execute"),
        ),
      ).toBe(true);
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
