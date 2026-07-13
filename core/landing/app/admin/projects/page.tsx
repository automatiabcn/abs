// Copyright (c) 2026 Automatia BCN. All rights reserved.
// Licensed under the Business Source License 1.1.
"use client";

// MT Phase 1 (C1) — Projects + membership + per-owner provider keys.
// Projects scope RAG/GraphRAG; members get a per-project role; each owner
// (user/project/org) can store its own provider key (resolved project→user→
// org→global at request time). The selected project is persisted to
// localStorage as `abs_active_project` and sent as X-Project-Id by the RAG UI.

import { useCallback, useEffect, useState } from "react";

import { FolderKanban, KeyRound, Plus, Trash2, Users } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

interface Project {
  slug: string;
  name: string;
  owner: string;
}
interface Member {
  user_subject: string;
  role: string;
}
interface ProviderKeyRow {
  owner_type: string;
  owner_id: string;
  provider: string;
}

const ACTIVE_KEY = "abs_active_project";
const PROVIDERS = ["groq", "cerebras", "gemini", "cohere", "cloudflare", "anthropic"];

async function api(path: string, init?: RequestInit) {
  const res = await fetch(path, { credentials: "include", ...init });
  if (!res.ok) throw new Error(`${path} → ${res.status}: ${(await res.text()).slice(0, 200)}`);
  return res.json();
}

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [active, setActive] = useState<string>("");
  const [selected, setSelected] = useState<string>("");
  const [members, setMembers] = useState<Member[]>([]);
  const [keys, setKeys] = useState<ProviderKeyRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [newSlug, setNewSlug] = useState("");
  const [newName, setNewName] = useState("");
  const [memberEmail, setMemberEmail] = useState("");
  const [memberRole, setMemberRole] = useState("viewer");
  const [keyProvider, setKeyProvider] = useState("groq");
  const [keyValue, setKeyValue] = useState("");
  const [keyOwnerType, setKeyOwnerType] = useState("org");

  const loadProjects = useCallback(async () => {
    try {
      const d = await api("/v1/admin/projects");
      setProjects(d.projects ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "unknown");
    }
  }, []);

  const loadKeys = useCallback(async () => {
    try {
      const d = await api("/v1/admin/provider-keys");
      setKeys(d.keys ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "unknown");
    }
  }, []);

  useEffect(() => {
    setActive(localStorage.getItem(ACTIVE_KEY) || "");
    void loadProjects();
    void loadKeys();
  }, [loadProjects, loadKeys]);

  const loadMembers = useCallback(async (slug: string) => {
    setSelected(slug);
    try {
      const d = await api(`/v1/admin/projects/${encodeURIComponent(slug)}/members`);
      setMembers(d.members ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "unknown");
    }
  }, []);

  async function createProject() {
    if (!newSlug.trim()) return;
    setError(null);
    try {
      await api("/v1/admin/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slug: newSlug.trim(), name: newName.trim() }),
      });
      setNewSlug("");
      setNewName("");
      await loadProjects();
    } catch (e) {
      setError(e instanceof Error ? e.message : "unknown");
    }
  }

  async function archiveProject(slug: string) {
    setError(null);
    try {
      await api(`/v1/admin/projects/${encodeURIComponent(slug)}`, { method: "DELETE" });
      if (active === slug) setActiveProject("");
      if (selected === slug) {
        setSelected("");
        setMembers([]);
      }
      await loadProjects();
    } catch (e) {
      setError(e instanceof Error ? e.message : "unknown");
    }
  }

  function setActiveProject(slug: string) {
    setActive(slug);
    if (slug) localStorage.setItem(ACTIVE_KEY, slug);
    else localStorage.removeItem(ACTIVE_KEY);
  }

  async function addMember() {
    if (!selected || !memberEmail.trim()) return;
    setError(null);
    try {
      await api(`/v1/admin/projects/${encodeURIComponent(selected)}/members`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_subject: memberEmail.trim(), role: memberRole }),
      });
      setMemberEmail("");
      await loadMembers(selected);
    } catch (e) {
      setError(e instanceof Error ? e.message : "unknown");
    }
  }

  async function removeMember(sub: string) {
    setError(null);
    try {
      await api(
        `/v1/admin/projects/${encodeURIComponent(selected)}/members/${encodeURIComponent(sub)}`,
        { method: "DELETE" },
      );
      await loadMembers(selected);
    } catch (e) {
      setError(e instanceof Error ? e.message : "unknown");
    }
  }

  async function saveKey() {
    if (!keyValue.trim()) return;
    setError(null);
    const ownerId = keyOwnerType === "project" ? selected : undefined;
    if (keyOwnerType === "project" && !selected) {
      setError("Pick a project first — a project key needs one.");
      return;
    }
    try {
      await api("/v1/admin/provider-keys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: keyProvider,
          value: keyValue.trim(),
          owner_type: keyOwnerType,
          owner_id: ownerId,
        }),
      });
      setKeyValue("");
      await loadKeys();
    } catch (e) {
      setError(e instanceof Error ? e.message : "unknown");
    }
  }

  async function deleteKey(row: ProviderKeyRow) {
    setError(null);
    try {
      await api("/v1/admin/provider-keys", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: row.provider,
          owner_type: row.owner_type,
          owner_id: row.owner_id,
        }),
      });
      await loadKeys();
    } catch (e) {
      setError(e instanceof Error ? e.message : "unknown");
    }
  }

  return (
    <main className="mx-auto max-w-5xl space-y-4 p-4">
      <div className="flex items-center gap-2">
        <FolderKanban className="h-5 w-5 text-primary" />
        <h1 className="text-lg font-semibold">Projects &amp; keys</h1>
        {active && (
          <Badge variant="outline" className="ml-auto text-[10px]">
            Active project: {active}
          </Badge>
        )}
      </div>

      {error && (
        <div className="rounded-md border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-200">
          {error}
        </div>
      )}

      {/* Projects */}
      <Card className="bg-card/70">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Projects</CardTitle>
          <CardDescription>
            Each project is a separate workspace for your documents and graph.
            Set one active and every knowledge-base search is limited to it.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <input
              value={newSlug}
              onChange={(e) => setNewSlug(e.target.value)}
              placeholder="project-slug"
              data-test="project-slug"
              className="rounded-md border border-border bg-background p-2 text-sm"
            />
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Project name"
              className="flex-1 rounded-md border border-border bg-background p-2 text-sm"
            />
            <Button type="button" onClick={createProject} data-test="project-create">
              <Plus className="mr-1 h-4 w-4" /> Create
            </Button>
          </div>
          <ul className="space-y-1">
            {projects.map((p) => (
              <li
                key={p.slug}
                data-test="project-row"
                className="flex items-center justify-between rounded-md border border-border bg-background/40 px-3 py-2 text-xs"
              >
                <button
                  type="button"
                  onClick={() => void loadMembers(p.slug)}
                  className="flex items-center gap-2 truncate text-left hover:text-primary"
                >
                  <Users className="h-3 w-3 text-muted-foreground" />
                  <code className="font-mono">{p.slug}</code>
                  <span className="text-muted-foreground">{p.name}</span>
                </button>
                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    variant={active === p.slug ? "default" : "outline"}
                    className="h-6 px-2 text-[10px]"
                    onClick={() => setActiveProject(active === p.slug ? "" : p.slug)}
                  >
                    {active === p.slug ? "Active" : "Set active"}
                  </Button>
                  <button
                    type="button"
                    onClick={() => void archiveProject(p.slug)}
                    aria-label={`Archive ${p.slug}`}
                    className="rounded p-1 text-muted-foreground hover:text-rose-300"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </li>
            ))}
            {projects.length === 0 && (
              <li className="text-xs text-muted-foreground">No projects yet.</li>
            )}
          </ul>

          {selected && (
            <div className="mt-3 rounded-md border border-border p-3">
              <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Members — {selected}
              </h4>
              <div className="mb-2 flex flex-wrap gap-2">
                <input
                  value={memberEmail}
                  onChange={(e) => setMemberEmail(e.target.value)}
                  placeholder="name@company.com"
                  className="flex-1 rounded-md border border-border bg-background p-2 text-xs"
                />
                <select
                  value={memberRole}
                  onChange={(e) => setMemberRole(e.target.value)}
                  className="rounded-md border border-border bg-background p-2 text-xs"
                >
                  <option value="viewer">viewer</option>
                  <option value="editor">editor</option>
                  <option value="owner">owner</option>
                </select>
                <Button type="button" onClick={addMember} className="h-9 text-xs">
                  Add
                </Button>
              </div>
              <ul className="space-y-1">
                {members.map((m) => (
                  <li
                    key={m.user_subject}
                    className="flex items-center justify-between rounded bg-background/40 px-2 py-1 text-xs"
                  >
                    <span>
                      {m.user_subject} ·{" "}
                      <span className="text-muted-foreground">{m.role}</span>
                    </span>
                    <button
                      type="button"
                      onClick={() => void removeMember(m.user_subject)}
                      className="rounded p-1 text-muted-foreground hover:text-rose-300"
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Provider keys */}
      <Card className="bg-card/70">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <KeyRound className="h-4 w-4 text-primary" />
            Your own provider keys (BYOK)
          </CardTitle>
          <CardDescription>
            A user, a project or the whole organisation can bring its own API
            key. On each request we look for a key in that order — project,
            then user, then organisation, then the server default.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <select
              value={keyOwnerType}
              onChange={(e) => setKeyOwnerType(e.target.value)}
              className="rounded-md border border-border bg-background p-2 text-sm"
            >
              <option value="org">organisation</option>
              <option value="user">just me</option>
              <option value="project">selected project</option>
            </select>
            <select
              value={keyProvider}
              onChange={(e) => setKeyProvider(e.target.value)}
              className="rounded-md border border-border bg-background p-2 text-sm"
            >
              {PROVIDERS.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
            <input
              type="password"
              value={keyValue}
              onChange={(e) => setKeyValue(e.target.value)}
              placeholder="API key"
              data-test="provider-key-value"
              className="flex-1 rounded-md border border-border bg-background p-2 text-sm"
            />
            <Button type="button" onClick={saveKey} data-test="provider-key-save">
              Save
            </Button>
          </div>
          <ul className="space-y-1">
            {keys.map((k, i) => (
              <li
                key={`${k.owner_type}-${k.owner_id}-${k.provider}-${i}`}
                className="flex items-center justify-between rounded-md border border-border bg-background/40 px-3 py-2 text-xs"
              >
                <span>
                  <Badge variant="outline" className="mr-2 text-[10px]">
                    {k.owner_type}
                  </Badge>
                  <code className="font-mono">{k.provider}</code>
                  <span className="ml-2 text-muted-foreground">{k.owner_id}</span>
                </span>
                <button
                  type="button"
                  onClick={() => void deleteKey(k)}
                  className="rounded p-1 text-muted-foreground hover:text-rose-300"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </li>
            ))}
            {keys.length === 0 && (
              <li className="text-xs text-muted-foreground">No keys yet.</li>
            )}
          </ul>
        </CardContent>
      </Card>
    </main>
  );
}
