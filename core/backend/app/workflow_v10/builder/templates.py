# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Natural-language workflow builder — 50 small-business templates.

Every template carries an English `title` and a localized `title_tr`. Both are
product content: template search matches against either one.
"""

from __future__ import annotations

from typing import Any

from .ontology import (
    Node,
    NodeConfig,
    NodeKind,
    Trigger,
    TriggerKind,
    WorkflowTemplate,
    build_simple_chain,
)


_NODE_KIND_MAP: dict[str, NodeKind] = {
    "llm_call": NodeKind.LLM_CALL,
    "api_request": NodeKind.API_REQUEST,
    "conditional": NodeKind.CONDITIONAL,
    "loop": NodeKind.LOOP,
    "hitl": NodeKind.HITL,
    "abs_tool": NodeKind.ABS_TOOL,
    "transform": NodeKind.TRANSFORM,
    "output": NodeKind.OUTPUT,
}


def _trigger(template_id: str, kind: str, arg: str | None) -> Trigger:
    tid = f"trg-{template_id}"
    if kind == "webhook":
        return Trigger(
            kind=TriggerKind.WEBHOOK,
            id=tid,
            webhook_path=arg or "/hook",
            description="Webhook",
        )
    if kind == "cron":
        return Trigger(
            kind=TriggerKind.CRON,
            id=tid,
            cron_expr=arg or "0 9 * * 1",
            description="Cron",
        )
    if kind == "event":
        return Trigger(
            kind=TriggerKind.EVENT,
            id=tid,
            event_topic=arg or "abs.event",
            description="Event",
        )
    return Trigger(kind=TriggerKind.MANUAL, id=tid, description="Manual")


def _build(d: dict[str, Any]) -> WorkflowTemplate:
    nodes: list[Node] = []
    for i, (kind_str, name, cfg) in enumerate(d["nodes"], 1):
        nodes.append(
            Node(
                id=f"{d['id']}-n{i}",
                kind=_NODE_KIND_MAP[kind_str],
                name=name,
                config=NodeConfig(**(cfg or {})),
            )
        )
    return build_simple_chain(
        template_id=d["id"],
        title_en=d["title_en"],
        title_tr=d["title_tr"],
        title_es=d["title_es"],
        trigger=_trigger(d["id"], d["trigger_kind"], d.get("trigger_arg")),
        nodes=nodes,
        tags=d.get("tags", []),
    )


_TEMPLATE_DEFS: list[dict[str, Any]] = [
    {
        "id": "email-classify-draft",
        "title_en": "Email classify and draft reply",
        "title_tr": "E-postayı sınıflandır ve taslak yanıt oluştur",
        "title_es": "Clasificar correo y redactar respuesta",
        "trigger_kind": "event",
        "trigger_arg": "abs.gmail.message_received",
        "nodes": [
            (
                "abs_tool",
                "Classify intent",
                {
                    "tool_name": "abs.gmail_classify",
                    "tool_args": {"label_set": ["sales", "support", "billing", "spam"]},
                },
            ),
            (
                "abs_tool",
                "Draft reply",
                {
                    "tool_name": "abs.gmail_draft",
                    "prompt": "Reply professionally based on classification.",
                },
            ),
            ("hitl", "Manager approval", {"approval_role": "tenant_owner"}),
            ("abs_tool", "Send email", {"tool_name": "abs.gmail_send"}),
        ],
        "tags": ["email", "gmail", "approval"],
    },
    {
        "id": "meeting-to-ticket",
        "title_en": "Meeting transcript → action items → tickets",
        "title_tr": "Toplantı dökümünden aksiyon ve ticket çıkar",
        "title_es": "De acta de reunión a tickets accionables",
        "trigger_kind": "event",
        "trigger_arg": "abs.meeting.recording_ready",
        "nodes": [
            ("abs_tool", "Transcribe", {"tool_name": "abs.meeting_transcribe"}),
            ("abs_tool", "Extract action items", {"tool_name": "abs.action_extract"}),
            (
                "abs_tool",
                "Create Linear tickets",
                {"tool_name": "abs.linear_create_ticket"},
            ),
            ("abs_tool", "Log to Notion", {"tool_name": "abs.notion_log"}),
        ],
        "tags": ["meeting", "linear", "notion"],
    },
    {
        "id": "status-report-friday",
        "title_en": "Friday status report",
        "title_tr": "Cuma durum raporu",
        "title_es": "Informe de estado del viernes",
        "trigger_kind": "cron",
        "trigger_arg": "0 16 * * 5",
        "nodes": [
            (
                "abs_tool",
                "Pull Linear updates",
                {
                    "tool_name": "abs.linear_create_ticket",
                    "tool_args": {"mode": "list_recent"},
                },
            ),
            ("abs_tool", "Summarise progress", {"tool_name": "abs.qual_analysis"}),
            ("abs_tool", "Send report email", {"tool_name": "abs.gmail_send"}),
        ],
        "tags": ["status", "weekly"],
    },
    {
        "id": "rag-query-chat",
        "title_en": "RAG-grounded customer chat",
        "title_tr": "RAG temelli müşteri sohbeti",
        "title_es": "Chat con clientes apoyado en RAG",
        "trigger_kind": "webhook",
        "trigger_arg": "/hook/chat",
        "nodes": [
            ("abs_tool", "Tenant policy check", {"tool_name": "abs.cerbos_check"}),
            ("abs_tool", "RAG query", {"tool_name": "abs.rag_query"}),
            (
                "abs_tool",
                "Compose answer",
                {"tool_name": "abs.qual_code", "prompt": "Answer with citations."},
            ),
            ("output", "Return JSON", {"output_template": "{{result}}"}),
        ],
        "tags": ["rag", "chat", "tenant"],
    },
    {
        "id": "news-digest",
        "title_en": "Daily news digest",
        "title_tr": "Günlük haber özeti",
        "title_es": "Resumen diario de noticias",
        "trigger_kind": "cron",
        "trigger_arg": "0 7 * * *",
        "nodes": [
            (
                "api_request",
                "Fetch RSS",
                {"method": "GET", "url": "https://news.example/feed.xml"},
            ),
            ("abs_tool", "Summarise", {"tool_name": "abs.qual_analysis"}),
            ("abs_tool", "Send digest", {"tool_name": "abs.gmail_send"}),
        ],
        "tags": ["news", "digest"],
    },
    {
        "id": "customer-onboarding",
        "title_en": "Customer onboarding pack",
        "title_tr": "Müşteri başlangıç paketi",
        "title_es": "Paquete de bienvenida del cliente",
        "trigger_kind": "event",
        "trigger_arg": "abs.billing.subscription_created",
        "nodes": [
            ("abs_tool", "Personalise welcome", {"tool_name": "abs.qual_tr"}),
            ("abs_tool", "Provision workspace", {"tool_name": "abs.rag_ingest"}),
            ("abs_tool", "Send welcome", {"tool_name": "abs.gmail_send"}),
            ("abs_tool", "Notify CSM", {"tool_name": "abs.notion_log"}),
        ],
        "tags": ["onboarding", "stripe"],
    },
    {
        "id": "lead-scoring",
        "title_en": "Inbound lead scoring",
        "title_tr": "Gelen müşteri adayı puanlama",
        "title_es": "Puntuación de leads entrantes",
        "trigger_kind": "webhook",
        "trigger_arg": "/hook/lead",
        "nodes": [
            ("abs_tool", "Enrich lead", {"tool_name": "abs.rag_query"}),
            (
                "llm_call",
                "Score 0–100",
                {"model": "groq", "prompt": "Score 0-100 with JSON {score, reason}."},
            ),
            ("conditional", "High value?", {"condition_expr": "{{score}} >= 70"}),
            ("abs_tool", "Notify sales", {"tool_name": "abs.gmail_send"}),
        ],
        "tags": ["sales", "lead"],
    },
    {
        "id": "invoice-followup",
        "title_en": "Overdue invoice follow-up",
        "title_tr": "Vadesi geçmiş fatura takibi",
        "title_es": "Seguimiento de facturas vencidas",
        "trigger_kind": "cron",
        "trigger_arg": "0 9 * * *",
        "nodes": [
            (
                "api_request",
                "Fetch overdue",
                {"method": "GET", "url": "https://billing.internal/api/overdue"},
            ),
            ("abs_tool", "Draft reminder", {"tool_name": "abs.qual_tr"}),
            ("hitl", "Finance approval", {"approval_role": "tenant_owner"}),
            ("abs_tool", "Send reminder", {"tool_name": "abs.gmail_send"}),
        ],
        "tags": ["billing", "finance", "approval"],
    },
    {
        "id": "support-triage",
        "title_en": "Support ticket triage",
        "title_tr": "Destek talebi triyajı",
        "title_es": "Clasificación de tickets de soporte",
        "trigger_kind": "event",
        "trigger_arg": "abs.support.ticket_created",
        "nodes": [
            ("abs_tool", "Classify ticket", {"tool_name": "abs.gmail_classify"}),
            ("abs_tool", "RAG resolution", {"tool_name": "abs.rag_query"}),
            ("conditional", "Urgent?", {"condition_expr": "{{priority}} == 'P0'"}),
            ("abs_tool", "Page on-call", {"tool_name": "abs.gmail_send"}),
        ],
        "tags": ["support", "triage"],
    },
    {
        "id": "hr-resume-screen",
        "title_en": "HR resume screening",
        "title_tr": "İK özgeçmiş tarama",
        "title_es": "Selección de currículums por RR. HH.",
        "trigger_kind": "webhook",
        "trigger_arg": "/hook/resume",
        "nodes": [
            ("abs_tool", "Parse resume", {"tool_name": "abs.qual_analysis"}),
            (
                "llm_call",
                "Score fit",
                {"model": "groq", "prompt": "Return JSON {fit, rationale}."},
            ),
            ("hitl", "Recruiter review", {"approval_role": "tenant_owner"}),
            ("abs_tool", "Notify candidate", {"tool_name": "abs.gmail_send"}),
        ],
        "tags": ["hr", "hiring"],
    },
    {
        "id": "expense-report",
        "title_en": "Expense report submission",
        "title_tr": "Gider raporu gönderimi",
        "title_es": "Envío de informe de gastos",
        "trigger_kind": "manual",
        "trigger_arg": None,
        "nodes": [
            ("abs_tool", "OCR receipt", {"tool_name": "abs.qual_analysis"}),
            ("abs_tool", "Categorise", {"tool_name": "abs.qual_code"}),
            ("hitl", "Manager approval", {"approval_role": "tenant_owner"}),
            (
                "api_request",
                "Post to ERP",
                {"method": "POST", "url": "https://erp.internal/api/expense"},
            ),
        ],
        "tags": ["finance", "approval"],
    },
    {
        "id": "weekly-newsletter-draft",
        "title_en": "Weekly newsletter draft",
        "title_tr": "Haftalık bülten taslağı",
        "title_es": "Borrador del boletín semanal",
        "trigger_kind": "cron",
        "trigger_arg": "0 10 * * 4",
        "nodes": [
            ("abs_tool", "Pull highlights", {"tool_name": "abs.rag_query"}),
            ("abs_tool", "Compose draft", {"tool_name": "abs.qual_tr"}),
            ("hitl", "Editor approval", {"approval_role": "tenant_owner"}),
        ],
        "tags": ["marketing", "newsletter"],
    },
    {
        "id": "crm-data-cleanup",
        "title_en": "CRM data hygiene",
        "title_tr": "CRM veri temizliği",
        "title_es": "Higiene de datos del CRM",
        "trigger_kind": "cron",
        "trigger_arg": "0 2 * * 0",
        "nodes": [
            (
                "api_request",
                "Fetch contacts",
                {"method": "GET", "url": "https://crm.internal/api/contacts"},
            ),
            ("abs_tool", "Detect duplicates", {"tool_name": "abs.qual_analysis"}),
            ("hitl", "Confirm merges", {"approval_role": "tenant_owner"}),
            (
                "api_request",
                "Apply merges",
                {"method": "POST", "url": "https://crm.internal/api/merge"},
            ),
        ],
        "tags": ["crm", "hygiene", "approval"],
    },
    {
        "id": "inventory-low-stock-alert",
        "title_en": "Inventory low-stock alert",
        "title_tr": "Düşük stok uyarısı",
        "title_es": "Alerta de inventario bajo",
        "trigger_kind": "cron",
        "trigger_arg": "*/30 * * * *",
        "nodes": [
            (
                "api_request",
                "Check stock",
                {"method": "GET", "url": "https://erp.internal/api/inventory"},
            ),
            ("conditional", "Below threshold?", {"condition_expr": "{{stock}} < 10"}),
            ("abs_tool", "Notify ops", {"tool_name": "abs.gmail_send"}),
        ],
        "tags": ["ops", "inventory"],
    },
    {
        "id": "customer-feedback-summary",
        "title_en": "Customer feedback summary",
        "title_tr": "Müşteri geri bildirim özeti",
        "title_es": "Resumen de comentarios de clientes",
        "trigger_kind": "cron",
        "trigger_arg": "0 9 * * 1",
        "nodes": [
            ("abs_tool", "Pull feedback", {"tool_name": "abs.rag_query"}),
            ("abs_tool", "Theme analysis", {"tool_name": "abs.qual_analysis"}),
            ("abs_tool", "Email leadership", {"tool_name": "abs.gmail_send"}),
        ],
        "tags": ["cx", "voc"],
    },
    {
        "id": "social-media-post-draft",
        "title_en": "Social media post draft",
        "title_tr": "Sosyal medya gönderi taslağı",
        "title_es": "Borrador de publicación social",
        "trigger_kind": "manual",
        "trigger_arg": None,
        "nodes": [
            (
                "llm_call",
                "Generate variants",
                {"model": "groq", "prompt": "Three short variants under 240 chars."},
            ),
            ("hitl", "Marketing approval", {"approval_role": "tenant_owner"}),
            ("output", "Return chosen", {"output_template": "{{chosen}}"}),
        ],
        "tags": ["marketing", "social"],
    },
    {
        "id": "seo-content-brief",
        "title_en": "SEO content brief",
        "title_tr": "SEO içerik brifi",
        "title_es": "Brief de contenido SEO",
        "trigger_kind": "manual",
        "trigger_arg": None,
        "nodes": [
            ("abs_tool", "Keyword research", {"tool_name": "abs.qual_analysis"}),
            ("abs_tool", "Outline draft", {"tool_name": "abs.qual_tr"}),
            ("output", "Return brief", {"output_template": "{{brief}}"}),
        ],
        "tags": ["seo", "marketing"],
    },
    {
        "id": "price-monitor-competitor",
        "title_en": "Competitor price monitor",
        "title_tr": "Rakip fiyat izleme",
        "title_es": "Monitor de precios de la competencia",
        "trigger_kind": "cron",
        "trigger_arg": "0 6 * * *",
        "nodes": [
            (
                "api_request",
                "Fetch competitor pages",
                {"method": "GET", "url": "https://compete.example/api/list"},
            ),
            ("abs_tool", "Detect changes", {"tool_name": "abs.qual_analysis"}),
            ("conditional", "Significant?", {"condition_expr": "{{delta_pct}} > 5"}),
            ("abs_tool", "Notify pricing team", {"tool_name": "abs.gmail_send"}),
        ],
        "tags": ["pricing", "competitive"],
    },
    {
        "id": "legal-contract-summary",
        "title_en": "Legal contract summary",
        "title_tr": "Hukuki sözleşme özeti",
        "title_es": "Resumen de contrato legal",
        "trigger_kind": "webhook",
        "trigger_arg": "/hook/contract",
        "nodes": [
            ("abs_tool", "Extract obligations", {"tool_name": "abs.qual_analysis"}),
            ("abs_tool", "Risk score", {"tool_name": "abs.qual_code"}),
            ("hitl", "Legal review", {"approval_role": "tenant_owner"}),
            ("abs_tool", "Log to vault", {"tool_name": "abs.notion_log"}),
        ],
        "tags": ["legal", "compliance"],
    },
    {
        "id": "tax-deadline-reminder",
        "title_en": "Tax deadline reminder",
        "title_tr": "Vergi son tarih hatırlatıcısı",
        "title_es": "Recordatorio de fecha límite fiscal",
        "trigger_kind": "cron",
        "trigger_arg": "0 9 1 * *",
        "nodes": [
            ("abs_tool", "Pull deadlines", {"tool_name": "abs.rag_query"}),
            ("abs_tool", "Email finance", {"tool_name": "abs.gmail_send"}),
        ],
        "tags": ["finance", "tax"],
    },
    {
        "id": "employee-onboarding-pack",
        "title_en": "Employee onboarding pack",
        "title_tr": "Çalışan başlangıç paketi",
        "title_es": "Paquete de incorporación del empleado",
        "trigger_kind": "event",
        "trigger_arg": "abs.hr.employee_added",
        "nodes": [
            ("abs_tool", "Generate accounts", {"tool_name": "abs.qual_code"}),
            ("abs_tool", "Provision Slack/Notion", {"tool_name": "abs.notion_log"}),
            ("abs_tool", "Welcome email", {"tool_name": "abs.gmail_send"}),
        ],
        "tags": ["hr", "onboarding"],
    },
    {
        "id": "shipping-status-notify",
        "title_en": "Shipping status notification",
        "title_tr": "Kargo durumu bildirimi",
        "title_es": "Notificación de estado de envío",
        "trigger_kind": "event",
        "trigger_arg": "abs.shipping.status_changed",
        "nodes": [
            ("abs_tool", "Compose update", {"tool_name": "abs.qual_tr"}),
            ("abs_tool", "Notify customer", {"tool_name": "abs.gmail_send"}),
        ],
        "tags": ["ecommerce", "shipping"],
    },
    {
        "id": "b2b-cold-email-personalize",
        "title_en": "B2B cold email personalisation",
        "title_tr": "B2B soğuk e-posta kişiselleştirme",
        "title_es": "Personalización de correo en frío B2B",
        "trigger_kind": "manual",
        "trigger_arg": None,
        "nodes": [
            ("abs_tool", "Enrich account", {"tool_name": "abs.rag_query"}),
            ("abs_tool", "Personalise pitch", {"tool_name": "abs.qual_tr"}),
            ("hitl", "AE approval", {"approval_role": "tenant_owner"}),
            ("abs_tool", "Send email", {"tool_name": "abs.gmail_send"}),
        ],
        "tags": ["sales", "outbound"],
    },
    {
        "id": "abandoned-cart-recovery",
        "title_en": "Abandoned cart recovery",
        "title_tr": "Terk edilmiş sepet kurtarma",
        "title_es": "Recuperación de carritos abandonados",
        "trigger_kind": "event",
        "trigger_arg": "abs.shop.cart_abandoned",
        "nodes": [
            ("abs_tool", "Compose nudge", {"tool_name": "abs.qual_tr"}),
            ("abs_tool", "Send email", {"tool_name": "abs.gmail_send"}),
        ],
        "tags": ["ecommerce", "retention"],
    },
    {
        "id": "churn-risk-detect",
        "title_en": "Churn risk detection",
        "title_tr": "Kayıp risk tespiti",
        "title_es": "Detección de riesgo de churn",
        "trigger_kind": "cron",
        "trigger_arg": "0 3 * * *",
        "nodes": [
            (
                "api_request",
                "Pull usage",
                {"method": "GET", "url": "https://analytics.internal/api/usage"},
            ),
            (
                "llm_call",
                "Score churn",
                {"model": "groq", "prompt": "Return JSON {risk}."},
            ),
            ("conditional", "High risk?", {"condition_expr": "{{risk}} > 0.7"}),
            ("abs_tool", "Notify CSM", {"tool_name": "abs.gmail_send"}),
        ],
        "tags": ["cs", "retention"],
    },
    {
        "id": "supplier-rfq-fanout",
        "title_en": "Supplier RFQ fan-out",
        "title_tr": "Tedarikçi RFQ dağıtımı",
        "title_es": "Difusión de RFQ a proveedores",
        "trigger_kind": "manual",
        "trigger_arg": None,
        "nodes": [
            ("abs_tool", "Compose RFQ", {"tool_name": "abs.qual_translate"}),
            ("loop", "Each supplier", {"script": "for supplier in suppliers: send"}),
            ("abs_tool", "Send emails", {"tool_name": "abs.gmail_send"}),
        ],
        "tags": ["procurement", "rfq"],
    },
    {
        "id": "customer-renewal-reminder",
        "title_en": "Customer renewal reminder",
        "title_tr": "Müşteri yenileme hatırlatıcısı",
        "title_es": "Recordatorio de renovación de cliente",
        "trigger_kind": "cron",
        "trigger_arg": "0 9 * * *",
        "nodes": [
            (
                "api_request",
                "Fetch upcoming renewals",
                {"method": "GET", "url": "https://billing.internal/api/renewals"},
            ),
            ("abs_tool", "Compose reminder", {"tool_name": "abs.qual_tr"}),
            ("abs_tool", "Send email", {"tool_name": "abs.gmail_send"}),
        ],
        "tags": ["renewal", "billing"],
    },
    {
        "id": "ticket-sla-breach-warn",
        "title_en": "Ticket SLA breach warning",
        "title_tr": "SLA ihlal uyarısı",
        "title_es": "Aviso de incumplimiento de SLA",
        "trigger_kind": "cron",
        "trigger_arg": "*/15 * * * *",
        "nodes": [
            (
                "api_request",
                "Fetch open tickets",
                {"method": "GET", "url": "https://support.internal/api/tickets/open"},
            ),
            (
                "conditional",
                "SLA breached?",
                {"condition_expr": "{{age_hours}} > {{sla_hours}}"},
            ),
            ("abs_tool", "Page manager", {"tool_name": "abs.gmail_send"}),
        ],
        "tags": ["support", "sla"],
    },
    {
        "id": "rag-document-ingest",
        "title_en": "RAG document ingest",
        "title_tr": "RAG belge alımı",
        "title_es": "Ingesta de documentos RAG",
        "trigger_kind": "webhook",
        "trigger_arg": "/hook/ingest",
        "nodes": [
            ("abs_tool", "Tenant policy check", {"tool_name": "abs.cerbos_check"}),
            ("abs_tool", "Ingest", {"tool_name": "abs.rag_ingest"}),
            ("abs_tool", "Trace", {"tool_name": "abs.langfuse_trace"}),
            ("output", "Return id", {"output_template": "{{doc_id}}"}),
        ],
        "tags": ["rag", "ingest"],
    },
    {
        "id": "board-prep-monthly",
        "title_en": "Monthly board prep",
        "title_tr": "Aylık yönetim kurulu hazırlığı",
        "title_es": "Preparación mensual del consejo",
        "trigger_kind": "cron",
        "trigger_arg": "0 8 1 * *",
        "nodes": [
            ("abs_tool", "Pull metrics", {"tool_name": "abs.rag_query"}),
            ("abs_tool", "Draft narrative", {"tool_name": "abs.qual_translate"}),
            ("hitl", "Founder review", {"approval_role": "tenant_owner"}),
        ],
        "tags": ["exec", "board"],
    },
    {
        "id": "press-mention-summary",
        "title_en": "Press mention summary",
        "title_tr": "Basın söz konusu özeti",
        "title_es": "Resumen de menciones en prensa",
        "trigger_kind": "cron",
        "trigger_arg": "0 8 * * *",
        "nodes": [
            (
                "api_request",
                "Fetch mentions",
                {"method": "GET", "url": "https://news.example/api/mentions"},
            ),
            ("abs_tool", "Summarise", {"tool_name": "abs.qual_analysis"}),
            ("abs_tool", "Email PR", {"tool_name": "abs.gmail_send"}),
        ],
        "tags": ["pr", "comms"],
    },
    {
        "id": "payroll-prep-monthly",
        "title_en": "Monthly payroll prep",
        "title_tr": "Aylık bordro hazırlığı",
        "title_es": "Preparación mensual de nómina",
        "trigger_kind": "cron",
        "trigger_arg": "0 9 25 * *",
        "nodes": [
            (
                "api_request",
                "Pull hours",
                {"method": "GET", "url": "https://hr.internal/api/hours"},
            ),
            ("abs_tool", "Validate", {"tool_name": "abs.qual_code"}),
            ("hitl", "Finance approval", {"approval_role": "tenant_owner"}),
            (
                "api_request",
                "Submit payroll",
                {"method": "POST", "url": "https://hr.internal/api/payroll"},
            ),
        ],
        "tags": ["finance", "hr"],
    },
    {
        "id": "content-moderation-flag",
        "title_en": "Content moderation flag",
        "title_tr": "İçerik moderasyon işareti",
        "title_es": "Marcado de moderación de contenido",
        "trigger_kind": "event",
        "trigger_arg": "abs.content.user_post",
        "nodes": [
            ("abs_tool", "Classify", {"tool_name": "abs.gmail_classify"}),
            ("conditional", "Flagged?", {"condition_expr": "{{label}} == 'flag'"}),
            ("abs_tool", "Notify trust", {"tool_name": "abs.gmail_send"}),
        ],
        "tags": ["trust", "safety"],
    },
    {
        "id": "interview-scheduler",
        "title_en": "Interview scheduler",
        "title_tr": "Mülakat planlayıcı",
        "title_es": "Planificador de entrevistas",
        "trigger_kind": "event",
        "trigger_arg": "abs.hr.candidate_progress",
        "nodes": [
            ("abs_tool", "Find slots", {"tool_name": "abs.qual_analysis"}),
            ("abs_tool", "Email candidate", {"tool_name": "abs.gmail_send"}),
        ],
        "tags": ["hr", "scheduling"],
    },
    {
        "id": "quality-issue-rca",
        "title_en": "Quality issue RCA",
        "title_tr": "Kalite olayı kök neden analizi",
        "title_es": "Análisis de causa raíz de calidad",
        "trigger_kind": "webhook",
        "trigger_arg": "/hook/quality",
        "nodes": [
            ("abs_tool", "Pull related events", {"tool_name": "abs.rag_query"}),
            ("abs_tool", "Run RCA", {"tool_name": "abs.qual_analysis"}),
            ("abs_tool", "Linear ticket", {"tool_name": "abs.linear_create_ticket"}),
        ],
        "tags": ["quality", "rca"],
    },
    {
        "id": "trade-show-leads-import",
        "title_en": "Trade show leads import",
        "title_tr": "Fuar müşteri adayları içe aktarımı",
        "title_es": "Importación de leads de feria",
        "trigger_kind": "manual",
        "trigger_arg": None,
        "nodes": [
            (
                "api_request",
                "Upload CSV",
                {"method": "POST", "url": "https://crm.internal/api/import"},
            ),
            ("abs_tool", "Enrich", {"tool_name": "abs.rag_query"}),
            ("abs_tool", "Notify sales", {"tool_name": "abs.gmail_send"}),
        ],
        "tags": ["sales", "events"],
    },
    {
        "id": "webinar-followup-email",
        "title_en": "Webinar follow-up email",
        "title_tr": "Web semineri takip e-postası",
        "title_es": "Correo de seguimiento de webinar",
        "trigger_kind": "event",
        "trigger_arg": "abs.event.webinar_ended",
        "nodes": [
            ("abs_tool", "Compose follow-up", {"tool_name": "abs.qual_tr"}),
            ("hitl", "Marketing review", {"approval_role": "tenant_owner"}),
            ("abs_tool", "Send", {"tool_name": "abs.gmail_send"}),
        ],
        "tags": ["marketing", "webinar"],
    },
    {
        "id": "shopify-order-summary",
        "title_en": "Shopify order summary",
        "title_tr": "Shopify sipariş özeti",
        "title_es": "Resumen de pedidos Shopify",
        "trigger_kind": "cron",
        "trigger_arg": "0 18 * * *",
        "nodes": [
            (
                "api_request",
                "Pull orders",
                {"method": "GET", "url": "https://shop.internal/api/orders"},
            ),
            ("abs_tool", "Summarise", {"tool_name": "abs.qual_analysis"}),
            ("abs_tool", "Send digest", {"tool_name": "abs.gmail_send"}),
        ],
        "tags": ["ecommerce", "ops"],
    },
    {
        "id": "nps-survey-trigger",
        "title_en": "NPS survey trigger",
        "title_tr": "NPS anket tetikleyicisi",
        "title_es": "Disparador de encuesta NPS",
        "trigger_kind": "event",
        "trigger_arg": "abs.cs.milestone_reached",
        "nodes": [
            ("abs_tool", "Compose survey", {"tool_name": "abs.qual_tr"}),
            ("abs_tool", "Send to user", {"tool_name": "abs.gmail_send"}),
        ],
        "tags": ["cs", "nps"],
    },
    {
        "id": "crm-deal-update-slack",
        "title_en": "CRM deal update to Slack",
        "title_tr": "CRM anlaşma güncelleme Slack'e",
        "title_es": "Actualización de oportunidad a Slack",
        "trigger_kind": "event",
        "trigger_arg": "abs.crm.deal_updated",
        "nodes": [
            ("abs_tool", "Format message", {"tool_name": "abs.qual_tr"}),
            (
                "api_request",
                "Post to Slack",
                {"method": "POST", "url": "https://slack.com/api/chat.postMessage"},
            ),
        ],
        "tags": ["crm", "slack"],
    },
    {
        "id": "gdpr-data-export",
        "title_en": "GDPR data export",
        "title_tr": "KVKK veri ihracı",
        "title_es": "Exportación de datos GDPR",
        "trigger_kind": "webhook",
        "trigger_arg": "/hook/gdpr-export",
        "nodes": [
            ("abs_tool", "Tenant policy check", {"tool_name": "abs.cerbos_check"}),
            (
                "api_request",
                "Bundle data",
                {"method": "POST", "url": "https://gdpr.internal/api/export"},
            ),
            ("abs_tool", "Email user", {"tool_name": "abs.gmail_send"}),
        ],
        "tags": ["gdpr", "compliance"],
    },
    {
        "id": "accounting-month-close",
        "title_en": "Accounting month close",
        "title_tr": "Aylık muhasebe kapanışı",
        "title_es": "Cierre contable mensual",
        "trigger_kind": "cron",
        "trigger_arg": "0 8 1 * *",
        "nodes": [
            (
                "api_request",
                "Reconcile",
                {"method": "POST", "url": "https://accounting.internal/api/close"},
            ),
            ("abs_tool", "Summarise variances", {"tool_name": "abs.qual_analysis"}),
            ("hitl", "CFO sign-off", {"approval_role": "tenant_owner"}),
        ],
        "tags": ["finance", "approval"],
    },
    {
        "id": "backup-status-digest",
        "title_en": "Backup status digest",
        "title_tr": "Yedekleme durumu özeti",
        "title_es": "Resumen del estado de respaldos",
        "trigger_kind": "cron",
        "trigger_arg": "0 7 * * *",
        "nodes": [
            (
                "api_request",
                "Pull backup logs",
                {"method": "GET", "url": "https://infra.internal/api/backups"},
            ),
            ("abs_tool", "Summarise", {"tool_name": "abs.qual_analysis"}),
            ("abs_tool", "Email ops", {"tool_name": "abs.gmail_send"}),
        ],
        "tags": ["ops", "backups"],
    },
    {
        "id": "translation-multi-locale",
        "title_en": "Multi-locale translation",
        "title_tr": "Çoklu dil çevirisi",
        "title_es": "Traducción multilenguaje",
        "trigger_kind": "manual",
        "trigger_arg": None,
        "nodes": [
            (
                "abs_tool",
                "Translate EN→TR",
                {"tool_name": "abs.qual_translate", "tool_args": {"target": "tr"}},
            ),
            (
                "abs_tool",
                "Translate EN→ES",
                {"tool_name": "abs.qual_translate", "tool_args": {"target": "es"}},
            ),
            ("output", "Return bundle", {"output_template": "{{translations}}"}),
        ],
        "tags": ["i18n"],
    },
    {
        "id": "competitive-watch",
        "title_en": "Competitive watch",
        "title_tr": "Rekabet izleme",
        "title_es": "Vigilancia competitiva",
        "trigger_kind": "cron",
        "trigger_arg": "0 7 * * 1",
        "nodes": [
            (
                "api_request",
                "Fetch competitor news",
                {"method": "GET", "url": "https://news.example/api/competitors"},
            ),
            ("abs_tool", "Summarise", {"tool_name": "abs.qual_analysis"}),
            ("abs_tool", "Notion log", {"tool_name": "abs.notion_log"}),
        ],
        "tags": ["strategy"],
    },
    {
        "id": "customer-success-checkin",
        "title_en": "Customer success check-in",
        "title_tr": "Müşteri başarı toplantısı",
        "title_es": "Check-in de éxito del cliente",
        "trigger_kind": "cron",
        "trigger_arg": "0 9 * * 2",
        "nodes": [
            ("abs_tool", "Pull usage", {"tool_name": "abs.rag_query"}),
            ("abs_tool", "Compose check-in", {"tool_name": "abs.qual_tr"}),
            ("abs_tool", "Email CSM", {"tool_name": "abs.gmail_send"}),
        ],
        "tags": ["cs"],
    },
    {
        "id": "partner-onboarding",
        "title_en": "Partner onboarding",
        "title_tr": "İş ortağı başlangıcı",
        "title_es": "Incorporación de partners",
        "trigger_kind": "event",
        "trigger_arg": "abs.partner.contract_signed",
        "nodes": [
            ("abs_tool", "Provision portal", {"tool_name": "abs.rag_ingest"}),
            ("abs_tool", "Welcome email", {"tool_name": "abs.gmail_send"}),
            ("abs_tool", "Notion log", {"tool_name": "abs.notion_log"}),
        ],
        "tags": ["partnerships"],
    },
    {
        "id": "policy-violation-alert",
        "title_en": "Policy violation alert",
        "title_tr": "Politika ihlal uyarısı",
        "title_es": "Alerta de violación de política",
        "trigger_kind": "event",
        "trigger_arg": "abs.audit.policy_violation",
        "nodes": [
            ("abs_tool", "Tenant policy check", {"tool_name": "abs.cerbos_check"}),
            ("abs_tool", "Notify security", {"tool_name": "abs.gmail_send"}),
            ("abs_tool", "Audit trace", {"tool_name": "abs.langfuse_trace"}),
        ],
        "tags": ["security", "compliance"],
    },
    {
        "id": "forecast-revenue-weekly",
        "title_en": "Weekly revenue forecast",
        "title_tr": "Haftalık gelir tahmini",
        "title_es": "Pronóstico semanal de ingresos",
        "trigger_kind": "cron",
        "trigger_arg": "0 10 * * 1",
        "nodes": [
            (
                "api_request",
                "Pull pipeline",
                {"method": "GET", "url": "https://crm.internal/api/pipeline"},
            ),
            ("abs_tool", "Forecast", {"tool_name": "abs.qual_analysis"}),
            ("abs_tool", "Email leadership", {"tool_name": "abs.gmail_send"}),
        ],
        "tags": ["finance", "forecast"],
    },
    {
        "id": "founder-update-investor",
        "title_en": "Founder investor update",
        "title_tr": "Kurucu yatırımcı güncellemesi",
        "title_es": "Actualización del fundador a inversores",
        "trigger_kind": "cron",
        "trigger_arg": "0 18 25 * *",
        "nodes": [
            ("abs_tool", "Pull KPIs", {"tool_name": "abs.rag_query"}),
            ("abs_tool", "Draft update", {"tool_name": "abs.qual_translate"}),
            ("hitl", "Founder review", {"approval_role": "tenant_owner"}),
            ("abs_tool", "Send to investors", {"tool_name": "abs.gmail_send"}),
        ],
        "tags": ["exec", "investors"],
    },
]


TEMPLATES: dict[str, WorkflowTemplate] = {d["id"]: _build(d) for d in _TEMPLATE_DEFS}


def get_template(template_id: str) -> WorkflowTemplate:
    if template_id not in TEMPLATES:
        raise KeyError(f"unknown workflow template: {template_id!r}")
    return TEMPLATES[template_id]


def list_templates() -> list[WorkflowTemplate]:
    return list(TEMPLATES.values())


__all__ = ["TEMPLATES", "get_template", "list_templates"]
