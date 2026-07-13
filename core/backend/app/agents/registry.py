# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Agent Registry — the canonical definition of every agent.

Each agent is purpose-scoped with an explicit allow-list of tools, data sources
and a model preference, plus a risk level that decides whether its proposed
actions need human approval. The API (`/v1/agents`) serves this registry to the
Agent Registry UI; the runtime (`app.agents.runtime`) executes against it.

`provider_hint` is a Model-Gateway provider name (see
`app.providers.cascade.PROVIDER_ORDER_*`) used as the cascade `prefer`; the
cascade still falls through on rate-limit/outage so an agent never hard-fails on
one provider. `model_label` is for display only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# Risk → approval: medium/high actions route to the Approval Center; low-risk
# (read / analyse / internal report) auto-complete.
RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"

CAT_DISCOVERY = "discovery_scoring"
CAT_INTELLIGENCE = "intelligence"
CAT_ENGAGEMENT = "engagement"
CAT_DATA_OPS = "data_ops"

CATEGORY_LABELS = {
    CAT_DISCOVERY: "Discovery & Scoring",
    CAT_INTELLIGENCE: "Intelligence",
    CAT_ENGAGEMENT: "Engagement",
    CAT_DATA_OPS: "Data Ops · Knowledge · Compliance",
}


@dataclass(frozen=True)
class Agent:
    id: str
    name: str
    purpose: str
    category: str
    icon: str
    tools: Tuple[str, ...]
    data_sources: Tuple[str, ...]
    provider_hint: str  # cascade provider (prefer)
    model_label: str  # display
    risk: str
    output_kind: str  # structured output contract key
    success_metric: str
    requires_approval: bool = field(default=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "purpose": self.purpose,
            "category": self.category,
            "category_label": CATEGORY_LABELS.get(self.category, self.category),
            "icon": self.icon,
            "tools": list(self.tools),
            "data_sources": list(self.data_sources),
            "model": self.model_label,
            "provider_hint": self.provider_hint,
            "risk": self.risk,
            "requires_approval": self.requires_approval,
            "output_kind": self.output_kind,
            "success_metric": self.success_metric,
        }


def _a(**kw) -> Agent:
    # default: engagement (medium/high risk) requires approval
    kw.setdefault("requires_approval", kw.get("risk") in (RISK_MEDIUM, RISK_HIGH))
    return Agent(**kw)


# ── the 20 agents (+ workflow planner) — mirrors the Agent Registry screen ──
_LIST: List[Agent] = [
    # Discovery & Scoring
    _a(
        id="lead_discovery",
        name="Lead Discovery Agent",
        icon="🔍",
        purpose="find companies that look like your best customers",
        category=CAT_DISCOVERY,
        tools=("web_crawl", "crm", "enrichment"),
        data_sources=("web", "crm"),
        provider_hint="groq",
        model_label="gpt-oss-120b",
        risk=RISK_LOW,
        output_kind="lead_list",
        success_metric="ICP-match rate",
    ),
    _a(
        id="lead_enrichment",
        name="Lead Enrichment Agent",
        icon="✛",
        purpose="fill in what you don't know about a company",
        category=CAT_DISCOVERY,
        tools=("connector", "rag", "consent"),
        data_sources=("connector", "web"),
        provider_hint="groq",
        model_label="qwen3-32b",
        risk=RISK_LOW,
        output_kind="enrichment",
        success_metric="enrichment confidence",
    ),
    _a(
        id="lead_scoring",
        name="Lead Scoring Agent",
        icon="⚖",
        purpose="rank a lead, and show the evidence for the rank",
        category=CAT_DISCOVERY,
        tools=("graph", "rag", "erp"),
        data_sources=("graph", "crm", "erp"),
        provider_hint="groq",
        model_label="gpt-oss-120b",
        risk=RISK_MEDIUM,
        output_kind="lead_score",
        success_metric="SAL conversion",
    ),
    _a(
        id="buying_signal",
        name="Buying Signal Agent",
        icon="📡",
        purpose="spot the signs a company is ready to buy",
        category=CAT_DISCOVERY,
        tools=("events", "crm", "web"),
        data_sources=("events", "crm", "web"),
        provider_hint="groq",
        model_label="llama-3.3-70b",
        risk=RISK_LOW,
        output_kind="signals",
        success_metric="signal precision",
    ),
    _a(
        id="company_analyst",
        name="Company Analyst Agent",
        icon="🏢",
        purpose="everything worth knowing about one company",
        category=CAT_DISCOVERY,
        tools=("rag", "web", "crm"),
        data_sources=("rag", "web", "crm"),
        provider_hint="gemini",
        model_label="gemini-pro",
        risk=RISK_LOW,
        output_kind="company_profile",
        success_metric="profile completeness",
    ),
    _a(
        id="market_research",
        name="Market Research Agent",
        icon="🌐",
        purpose="size up a market and its segments",
        category=CAT_DISCOVERY,
        tools=("web_search", "rag"),
        data_sources=("web",),
        provider_hint="gemini",
        model_label="gemini-search",
        risk=RISK_LOW,
        output_kind="research",
        success_metric="insight usefulness",
    ),
    # Intelligence
    _a(
        id="competitive_intel",
        name="Competitive Intel Agent",
        icon="⚔",
        purpose="keep watch on the competition",
        category=CAT_INTELLIGENCE,
        tools=("crawl", "rag", "graph"),
        data_sources=("web", "rag", "graph"),
        provider_hint="groq",
        model_label="gpt-oss-120b",
        risk=RISK_LOW,
        output_kind="competitor_intel",
        success_metric="signal recall",
    ),
    _a(
        id="battlecard",
        name="Battlecard Agent",
        icon="▤",
        purpose="how you win against a named rival, and what to say",
        category=CAT_INTELLIGENCE,
        tools=("rag", "graph"),
        data_sources=("rag", "graph"),
        provider_hint="cloudflare",
        model_label="kimi-k2",
        risk=RISK_LOW,
        output_kind="battlecard",
        success_metric="battlecard usefulness",
    ),
    _a(
        id="campaign_attribution",
        name="Campaign Attribution Agent",
        icon="◷",
        purpose="tie the money you spent to the money you made",
        category=CAT_INTELLIGENCE,
        tools=("ads", "crm", "erp"),
        data_sources=("ads", "crm", "erp"),
        provider_hint="groq",
        model_label="gpt-oss-120b",
        risk=RISK_MEDIUM,
        output_kind="attribution",
        success_metric="attribution accuracy",
    ),
    _a(
        id="social_strategy",
        name="Social Media Strategy Agent",
        icon="◐",
        purpose="where to post, and what to post there",
        category=CAT_INTELLIGENCE,
        tools=("social", "rag"),
        data_sources=("social", "rag"),
        provider_hint="gemini",
        model_label="gemini-pro",
        risk=RISK_LOW,
        output_kind="social_strategy",
        success_metric="engagement lift",
    ),
    _a(
        id="aeo_visibility",
        name="AEO Visibility Agent",
        icon="✦",
        purpose="whether AI assistants mention you at all",
        category=CAT_INTELLIGENCE,
        tools=("web_search", "rag"),
        data_sources=("web",),
        provider_hint="gemini",
        model_label="gemini-search",
        risk=RISK_LOW,
        output_kind="aeo_report",
        success_metric="AI-answer presence",
    ),
    _a(
        id="event_intelligence",
        name="Event Intelligence Agent",
        icon="⌖",
        purpose="events worth showing up to",
        category=CAT_INTELLIGENCE,
        tools=("web", "graph"),
        data_sources=("web", "graph"),
        provider_hint="groq",
        model_label="llama-3.3-70b",
        risk=RISK_LOW,
        output_kind="event_opportunities",
        success_metric="event ROI",
    ),
    # Engagement (approval-gated)
    _a(
        id="inbound_triage",
        name="Inbound Triage Agent",
        icon="⇄",
        purpose="sort incoming requests and draft the reply",
        category=CAT_ENGAGEMENT,
        tools=("rag", "crm", "cite"),
        data_sources=("rag", "crm"),
        provider_hint="groq",
        model_label="gpt-oss-120b",
        risk=RISK_MEDIUM,
        output_kind="inbound_triage",
        success_metric="response time",
    ),
    _a(
        id="outbound_draft",
        name="Outbound Draft Agent",
        icon="✉",
        purpose="write the first email, for one person in particular",
        category=CAT_ENGAGEMENT,
        tools=("graph", "consent", "deliverability"),
        data_sources=("graph", "crm"),
        provider_hint="cloudflare",
        model_label="kimi-k2",
        risk=RISK_HIGH,
        output_kind="outbound_draft",
        success_metric="reply rate",
    ),
    _a(
        id="voice_call",
        name="Voice Call Agent",
        icon="☎",
        purpose="take the call, and remember what was said",
        category=CAT_ENGAGEMENT,
        tools=("speech", "crm", "consent"),
        data_sources=("speech", "crm"),
        provider_hint="groq",
        model_label="realtime-speech",
        risk=RISK_HIGH,
        output_kind="call_result",
        success_metric="qualification rate",
    ),
    # Data Ops · Knowledge · Compliance
    _a(
        id="knowledge_base",
        name="Knowledge Base Agent",
        icon="▥",
        purpose="answer from your own documents, and cite them",
        category=CAT_DATA_OPS,
        tools=("rag", "cite"),
        data_sources=("rag",),
        provider_hint="groq",
        model_label="gpt-oss-120b",
        risk=RISK_LOW,
        output_kind="knowledge_answer",
        success_metric="citation correctness",
    ),
    _a(
        id="crm_hygiene",
        name="CRM Hygiene Agent",
        icon="◉",
        purpose="find the duplicates and the blank fields",
        category=CAT_DATA_OPS,
        tools=("crm", "graph"),
        data_sources=("crm", "graph"),
        provider_hint="groq",
        model_label="qwen3-32b",
        risk=RISK_MEDIUM,
        output_kind="hygiene_report",
        success_metric="CRM completeness",
    ),
    _a(
        id="erp_insight",
        name="ERP Insight Agent",
        icon="▣",
        purpose="what your products, customers and revenue are doing",
        category=CAT_DATA_OPS,
        tools=("erp", "graph"),
        data_sources=("erp", "graph"),
        provider_hint="groq",
        model_label="gpt-oss-120b",
        risk=RISK_LOW,
        output_kind="erp_insight",
        success_metric="insight accuracy",
    ),
    _a(
        id="compliance_review",
        name="Compliance Review Agent",
        icon="⛨",
        purpose="check it against consent, policy and the terms you agreed to",
        category=CAT_DATA_OPS,
        tools=("consent", "policy", "audit"),
        data_sources=("consent", "policy"),
        provider_hint="cohere",
        model_label="granite-3.1",
        risk=RISK_LOW,
        output_kind="compliance_verdict",
        success_metric="violation catch rate",
    ),
    _a(
        id="executive_report",
        name="Executive Report Agent",
        icon="▦",
        purpose="the week, summed up for whoever is busy",
        category=CAT_DATA_OPS,
        tools=("graph", "rag", "erp"),
        data_sources=("graph", "rag", "erp"),
        provider_hint="gemini",
        model_label="gemini-pro",
        risk=RISK_LOW,
        output_kind="exec_report",
        success_metric="report usage",
    ),
    _a(
        id="workflow_planner",
        name="Workflow Planner Agent",
        icon="⟿",
        purpose="break a job into steps and hand them to the right agents",
        category=CAT_DATA_OPS,
        tools=("orchestrate", "langgraph"),
        data_sources=(),
        provider_hint="groq",
        model_label="gpt-oss-120b",
        risk=RISK_MEDIUM,
        output_kind="workflow_plan",
        success_metric="workflow success rate",
    ),
]

AGENTS: Dict[str, Agent] = {a.id: a for a in _LIST}


def get_agent(agent_id: str) -> Agent | None:
    return AGENTS.get((agent_id or "").strip())


def agents_by_category() -> Dict[str, List[Agent]]:
    out: Dict[str, List[Agent]] = {c: [] for c in CATEGORY_LABELS}
    for a in _LIST:
        out.setdefault(a.category, []).append(a)
    return out
