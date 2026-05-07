import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import MarketplacePanel from "@/components/MarketplacePanel";
import type { PluginManifest } from "@/lib/marketplace";

const mockPlugins: PluginManifest[] = [
  {
    id: "plugin-llm",
    name: "Test LLM Provider",
    version: "1.2.3",
    type: "llm-provider",
    entry_point: "test.llm",
    description: "Provides LLM capabilities.",
    author: "Tester",
    license: "MIT",
    permissions: {
      network_egress: ["llm.example.com"],
      filesystem_read: ["/app/config"],
      filesystem_write: ["/tmp"],
      secrets: ["LLM_KEY"],
      tenant_scoped: true,
      cpu_quota: 0.5,
      memory_mb: 256,
    },
  },
  {
    id: "plugin-rag",
    name: "Test RAG Source",
    version: "0.9.0",
    type: "rag-source",
    entry_point: "test.rag",
    description: "RAG source for testing.",
    author: "Tester",
    license: "MIT",
    permissions: {
      network_egress: ["rag.example.com"],
      filesystem_read: ["/app/config"],
      filesystem_write: ["/tmp"],
      secrets: [],
      tenant_scoped: true,
      cpu_quota: 1,
      memory_mb: 512,
    },
  },
  {
    id: "plugin-mcp",
    name: "Test MCP Tool",
    version: "2.0.0",
    type: "mcp-tool",
    entry_point: "test.mcp",
    description: "MCP tool for testing.",
    author: "Tester",
    license: "MIT",
    permissions: {
      network_egress: ["mcp.example.com"],
      filesystem_read: ["/app/config"],
      filesystem_write: ["/tmp"],
      secrets: ["MCP_TOKEN"],
      tenant_scoped: false,
      cpu_quota: 0.2,
      memory_mb: 128,
    },
  },
];

describe("MarketplacePanel", () => {
  it("renders search box and all 5 filter chips", () => {
    render(<MarketplacePanel initialPlugins={mockPlugins} isAdmin={true} />);
    expect(screen.getByTestId("marketplace-search")).toBeInTheDocument();
    expect(screen.getByTestId("filter-chip-all")).toBeInTheDocument();
    expect(screen.getByTestId("filter-chip-llm-provider")).toBeInTheDocument();
    expect(screen.getByTestId("filter-chip-rag-source")).toBeInTheDocument();
    expect(screen.getByTestId("filter-chip-mcp-tool")).toBeInTheDocument();
    expect(screen.getByTestId("filter-chip-workflow-template")).toBeInTheDocument();
  });

  it("filters cards by search query", () => {
    render(<MarketplacePanel initialPlugins={mockPlugins} isAdmin={true} />);
    fireEvent.change(screen.getByTestId("marketplace-search"), {
      target: { value: "LLM" },
    });
    expect(screen.getByTestId("plugin-card-plugin-llm")).toBeInTheDocument();
    expect(screen.queryByTestId("plugin-card-plugin-rag")).not.toBeInTheDocument();
    expect(screen.queryByTestId("plugin-card-plugin-mcp")).not.toBeInTheDocument();
  });

  it("rag-source filter chip hides non-RAG cards", () => {
    render(<MarketplacePanel initialPlugins={mockPlugins} isAdmin={true} />);
    fireEvent.click(screen.getByTestId("filter-chip-rag-source"));
    expect(screen.getByTestId("plugin-card-plugin-rag")).toBeInTheDocument();
    expect(screen.queryByTestId("plugin-card-plugin-llm")).not.toBeInTheDocument();
    expect(screen.queryByTestId("plugin-card-plugin-mcp")).not.toBeInTheDocument();
  });

  it("disables Install button when isAdmin=false", () => {
    render(<MarketplacePanel initialPlugins={mockPlugins} isAdmin={false} />);
    expect(screen.getByTestId("install-button-plugin-llm")).toBeDisabled();
  });

  it("enables Install button when isAdmin=true", () => {
    render(<MarketplacePanel initialPlugins={mockPlugins} isAdmin={true} />);
    expect(screen.getByTestId("install-button-plugin-llm")).not.toBeDisabled();
  });

  it("opens permission modal with network egress hosts and secrets on Install", () => {
    render(<MarketplacePanel initialPlugins={mockPlugins} isAdmin={true} />);
    fireEvent.click(screen.getByTestId("install-button-plugin-llm"));
    const modal = screen.getByTestId("permission-modal");
    expect(modal).toBeInTheDocument();
    expect(modal).toHaveTextContent("llm.example.com");
    expect(modal).toHaveTextContent("LLM_KEY");
    expect(modal).toHaveTextContent("0.5 cores");
    expect(modal).toHaveTextContent("256 MB");
  });

  it("Cancel button closes the modal", async () => {
    render(<MarketplacePanel initialPlugins={mockPlugins} isAdmin={true} />);
    fireEvent.click(screen.getByTestId("install-button-plugin-llm"));
    fireEvent.click(screen.getByTestId("permission-cancel"));
    await waitFor(() => {
      expect(screen.queryByTestId("permission-modal")).not.toBeInTheDocument();
    });
  });

  it("Approve invokes onInstall with the selected manifest and closes the modal", async () => {
    const onInstall = vi.fn();
    render(
      <MarketplacePanel
        initialPlugins={mockPlugins}
        isAdmin={true}
        onInstall={onInstall}
      />,
    );
    fireEvent.click(screen.getByTestId("install-button-plugin-llm"));
    // Q9 / MP4 — Approve is gated behind an explicit acknowledgement
    // checkbox so admins can't blind-install. Tick it before clicking
    // approve, otherwise the button stays `disabled` and onInstall
    // never fires.
    fireEvent.click(screen.getByTestId("permission-acknowledge"));
    fireEvent.click(screen.getByTestId("permission-approve"));
    await waitFor(() => {
      expect(onInstall).toHaveBeenCalledTimes(1);
      expect(onInstall).toHaveBeenCalledWith(
        expect.objectContaining({ id: "plugin-llm", version: "1.2.3" }),
      );
      expect(screen.queryByTestId("permission-modal")).not.toBeInTheDocument();
    });
  });

  it("admin-banner toggles based on isAdmin flag", () => {
    const { rerender } = render(
      <MarketplacePanel initialPlugins={mockPlugins} isAdmin={false} />,
    );
    expect(screen.getByTestId("admin-banner")).toBeInTheDocument();

    rerender(<MarketplacePanel initialPlugins={mockPlugins} isAdmin={true} />);
    expect(screen.queryByTestId("admin-banner")).not.toBeInTheDocument();
  });
});
