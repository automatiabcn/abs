import "@testing-library/jest-dom/vitest";
import React from "react";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

// Q8 Phase B — @xyflow/react pulls zustand which mis-resolves React when
// jsdom runs from the monorepo root. Stub the canvas surface so panel
// tests don't blow up on the optional graph dependency.
vi.mock("@xyflow/react", () => {
  // Stub renders each node as data-testid="workflow-node-{id}" so legacy
  // canvas tests written against the pre-Q8 component keep passing.
  const NodeStub = ({ nodes }: { nodes?: Array<{ id: string }> }) =>
    React.createElement(
      "div",
      { "data-test-stub": "react-flow" },
      (nodes ?? []).map((n) =>
        React.createElement("div", {
          key: n.id,
          "data-testid": `workflow-node-${n.id}`,
        }),
      ),
    );
  return {
    ReactFlow: NodeStub,
    ReactFlowProvider: ({ children }: { children?: React.ReactNode }) =>
      React.createElement(React.Fragment, null, children),
    Background: () => null,
    Controls: () => null,
    MiniMap: () => null,
    addEdge: (e: unknown, eds: unknown[]) => [...eds, e],
    useNodesState: <T,>(initial: T) => [initial, () => {}, () => {}],
    useEdgesState: <T,>(initial: T) => [initial, () => {}, () => {}],
  };
});
vi.mock("@xyflow/react/dist/style.css", () => ({}));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
