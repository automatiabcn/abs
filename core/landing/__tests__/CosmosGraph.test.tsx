// The system map draws this server, or it draws nothing.
//
// It used to draw a fixed constellation: seven providers, four workflows, three
// RAG collections — on every install, with no fetch behind any of it, captioned
// "live, and moving as the server works". This test agreed with it: `it("ships
// all seven providers")` asserted the fabrication was intact.
//
// The graph is built from a `CosmosWorld` now — what the server reported — so the
// tests check that, and that an empty world draws an empty map.

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CosmosGraph } from "@/components/CosmosGraph";
import {
  EMPTY_WORLD,
  buildCosmosGraph,
  type CosmosWorld,
} from "@/components/CosmosGraph/buildGraph";
import { PALETTE, colourFor } from "@/components/CosmosGraph/colors";

vi.mock("react-force-graph-3d", () => ({ default: () => null }));
vi.mock("@/components/ui/skeleton", () => ({ Skeleton: () => null }));

const WORLD: CosmosWorld = {
  providers: ["groq", "ollama"],
  toolCategories: [
    { name: "rag", count: 5 },
    { name: "workflow", count: 3 },
  ],
  workflows: ["lead-triage"],
  documents: ["handbook.pdf"],
};

describe("CosmosGraph — palette contract", () => {
  it("uses the single brand palette (no rainbow per provider)", () => {
    expect(colourFor("active")).toBe(PALETTE.highlight);
    expect(colourFor("idle")).toBe(PALETTE.primary);
  });
});

describe("CosmosGraph — the map is the server", () => {
  it("draws the providers the server has, and no others", () => {
    const { nodes } = buildCosmosGraph(WORLD);
    const providers = nodes.filter((n) => n.group === "provider").map((n) => n.id);
    expect(providers.sort()).toEqual(["p:groq", "p:ollama"]);
    // The seven that used to appear on every install, whatever was configured.
    expect(providers).not.toContain("p:anthropic");
    expect(providers).not.toContain("p:cerebras");
  });

  it("draws the workflows and documents the server has", () => {
    const { nodes } = buildCosmosGraph(WORLD);
    const labels = nodes.map((n) => n.label);
    expect(labels).toContain("lead-triage");
    expect(labels).toContain("handbook.pdf");
    // The invented ones.
    expect(labels).not.toContain("onboarding");
    expect(labels).not.toContain("guvenlik");
  });

  it("draws nothing for a server with nothing on it", () => {
    const { nodes, links } = buildCosmosGraph(EMPTY_WORLD);
    expect(nodes).toHaveLength(0);
    expect(links).toHaveLength(0);
  });

  it("marks the highlighted provider as `active`", () => {
    const { nodes } = buildCosmosGraph(WORLD, "groq");
    expect(nodes.find((n) => n.id === "p:groq")?.state).toBe("active");
    expect(nodes.find((n) => n.id === "p:ollama")?.state).toBe("idle");
  });
});

describe("CosmosGraph — what it renders", () => {
  it("says so, rather than drawing a system, when there is nothing to draw", () => {
    render(<CosmosGraph world={EMPTY_WORLD} />);
    expect(document.querySelector('[data-test="cosmos-empty"]')).not.toBeNull();
    expect(document.querySelector('[data-test="cosmos-fallback"]')).toBeNull();
  });

  it("renders the iso-grid fallback for reduced motion, with the real providers", () => {
    render(<CosmosGraph world={WORLD} forceStatic highlightProvider="groq" />);
    expect(screen.getByTestId("cosmos-fallback")).toBeInTheDocument();
    expect(screen.getByLabelText(/groq provider, status: active/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/ollama provider, status: configured/i)).toBeInTheDocument();
  });
});
