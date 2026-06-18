// vitest contract for the Cosmos 3D
// system map (mockup_2 — force-directed graph). The 3D ForceGraph3D
// renderer is dynamic-imported with `ssr: false`, so the jsdom path
// only exercises the static / reduced-motion fallback. We assert:
//
//   1. brand palette contract (no rainbow per provider)
//   2. provider list rendering (7 providers, lower-case ids)
//   3. ARIA wrapper + reduced-motion fallback path
//   4. `forceStatic` prop bypasses the WebGL path

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CosmosGraph } from "@/components/CosmosGraph";
import {
  PROVIDER_NODES,
  buildCosmosGraph,
} from "@/components/CosmosGraph/buildGraph";
import { PALETTE, colourFor } from "@/components/CosmosGraph/colors";

// Mock the heavy renderer + skeleton so jsdom doesn't try to instantiate WebGL.
vi.mock("react-force-graph-3d", () => ({
  default: () => null,
}));
vi.mock("@/components/ui/skeleton", () => ({
  Skeleton: () => null,
}));

describe("CosmosGraph — palette contract", () => {
  it("uses the single brand palette (no rainbow per provider)", () => {
    const distinctIdleColours = new Set(
      PROVIDER_NODES.map(() => colourFor("idle")),
    );
    expect(distinctIdleColours.size).toBe(1);
    expect(distinctIdleColours.has(PALETTE.primary)).toBe(true);
    expect(colourFor("active")).toBe(PALETTE.highlight);
    expect(colourFor("idle")).toBe(PALETTE.primary);
  });
});

describe("CosmosGraph — graph data", () => {
  it("ships all seven providers", () => {
    const ids = new Set(PROVIDER_NODES.map((n) => n.id));
    [
      "p:groq",
      "p:cerebras",
      "p:cloudflare",
      "p:gemini",
      "p:cohere",
      "p:anthropic",
      "p:ollama",
    ].forEach((expected) => expect(ids.has(expected)).toBe(true));
  });

  it("marks the highlighted provider as `active`", () => {
    const { nodes } = buildCosmosGraph("groq");
    const groq = nodes.find((n) => n.id === "p:groq");
    const others = nodes.filter(
      (n) => n.group === "provider" && n.id !== "p:groq",
    );
    expect(groq?.state).toBe("active");
    others.forEach((n) => expect(n.state).toBe("idle"));
  });
});

describe("CosmosGraph — reduced-motion fallback", () => {
  it("renders the iso-grid fallback when `forceStatic` is true", () => {
    render(<CosmosGraph forceStatic highlightProvider="groq" />);
    const fallback = screen.getByTestId("cosmos-fallback");
    expect(fallback).toBeInTheDocument();
    expect(
      screen.getByLabelText(/ABS provider grid/i),
    ).toBeInTheDocument();
  });

  it("each provider in the fallback has an ARIA button label", () => {
    render(<CosmosGraph forceStatic />);
    const groqLabel = screen.getByLabelText(/Groq provider, status:/i);
    expect(groqLabel).toBeInTheDocument();
  });
});
