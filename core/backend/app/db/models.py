# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class License(SQLModel, table=True):
    """Durable record of every license minted."""

    __tablename__ = "licenses"

    id: Optional[int] = Field(default=None, primary_key=True)
    jti: str = Field(index=True, unique=True, description="Unique JWT id")
    customer_email: str = Field(default="", index=True)
    customer_id_stripe: str = Field(default="", index=True)
    tier: str = Field(default="self-host")
    seat_count: int = Field(default=1)

    issued_at: datetime
    expires_at: datetime

    revoked_at: Optional[datetime] = Field(default=None)
    revoked_reason: Optional[str] = Field(default=None)

    # first_success trigger
    first_tool_call_at: Optional[datetime] = Field(default=None)

    # Preferred email language (en|tr|es), parsed from the billing customer locale.
    preferred_lang: str = Field(default="en", max_length=8)

    # GDPR Article 17 (right to erasure)
    scheduled_delete_at: Optional[datetime] = Field(default=None)
    purged_at: Optional[datetime] = Field(default=None)


class EmailQueue(SQLModel, table=True):
    """Queue for the onboarding email series.

    `kind`: welcome|walkthrough|first_success|expiry_warning|recovery

    The scheduler ticks every 5 minutes and sends rows whose `scheduled_at` has
    passed and whose `sent_at` is NULL. Rows with `sent_at` set are skipped, so
    a repeated tick cannot send the same mail twice.
    """

    __tablename__ = "email_queue"

    id: Optional[int] = Field(default=None, primary_key=True)
    license_jti: str = Field(index=True, max_length=64)
    customer_email: str = Field(max_length=256)
    kind: str = Field(max_length=32, index=True)
    scheduled_at: datetime = Field(index=True)
    sent_at: Optional[datetime] = Field(default=None)
    attempts: int = Field(default=0)
    error: Optional[str] = Field(default=None, max_length=512)
    unsubscribed: bool = Field(default=False)


class OAuthState(SQLModel, table=True):
    """026 — OAuth state CSRF token cache (10-min TTL)."""

    __tablename__ = "oauth_states"

    state: str = Field(primary_key=True, max_length=64)
    provider: str = Field(max_length=32, index=True)
    redirect_url: str = Field(max_length=512)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class ConnectedSecret(SQLModel, table=True):
    """026 — Encrypted API keys / OAuth tokens for smart link integrations."""

    __tablename__ = "connected_secrets"

    id: Optional[int] = Field(default=None, primary_key=True)
    key_name: str = Field(index=True, unique=True, max_length=64)
    provider: str = Field(max_length=32, index=True)
    encrypted_value: str = Field(max_length=8192)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    last_validated_at: Optional[datetime] = Field(default=None)
    last_validated_ok: Optional[bool] = Field(default=None)
    last_validated_error: Optional[str] = Field(default=None, max_length=512)
    # 028 — OAuth refresh tracking
    expires_at: Optional[datetime] = Field(default=None)
    refresh_token_encrypted: Optional[str] = Field(default=None, max_length=8192)


class VaultAuditEntry(SQLModel, table=True):
    """027 — Vault audit log with HMAC chain (tamper-evident).

    Each row has hmac = HMAC-SHA256(secret, canonical_entry + prev_hmac).
    `verify_chain()` re-computes and detects any modification.
    """

    __tablename__ = "vault_audit_entries"

    id: Optional[int] = Field(default=None, primary_key=True)
    ts: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), index=True
    )
    action: str = Field(max_length=32, index=True)
    actor: str = Field(default="system", max_length=64)
    target_key: Optional[str] = Field(default=None, max_length=128)
    detail: Optional[str] = Field(default=None, max_length=512)
    hmac: str = Field(max_length=64)
    prev_hmac: str = Field(default="", max_length=64)
    # Postgres RLS tenant column. Rows seeded before the backfill migration
    # keep "_unknown"; runtime writes populate it from the request context
    # (see app.db.session).
    tenant_id: str = Field(default="_unknown", max_length=64, index=True)


class CustomerAuditEntry(SQLModel, table=True):
    """Per-customer audit log (GDPR Article 15, right of access)."""

    __tablename__ = "customer_audit_entries"

    id: Optional[int] = Field(default=None, primary_key=True)
    license_jti: str = Field(index=True, max_length=64)
    action: str = Field(max_length=64, index=True)
    resource: Optional[str] = Field(default=None, max_length=128)
    detail: Optional[str] = Field(default=None, max_length=512)
    ip_hash: Optional[str] = Field(default=None, max_length=32)
    user_agent_short: Optional[str] = Field(default=None, max_length=128)
    ts: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), index=True
    )
    # Postgres RLS tenant column (see VaultAuditEntry).
    tenant_id: str = Field(default="_unknown", max_length=64, index=True)


class Consent(SQLModel, table=True):
    """User consent tracking (GDPR Article 7)."""

    __tablename__ = "consents"

    id: Optional[int] = Field(default=None, primary_key=True)
    license_jti: str = Field(index=True, max_length=64)
    consent_type: str = Field(max_length=64, index=True)
    version: str = Field(default="1.0", max_length=16)
    granted_at: Optional[datetime] = Field(default=None)
    withdrawn_at: Optional[datetime] = Field(default=None)
    source: str = Field(default="setup_wizard", max_length=32)


class DataExportJob(SQLModel, table=True):
    """GDPR data-export async job tracker."""

    __tablename__ = "data_export_jobs"

    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: str = Field(unique=True, index=True, max_length=48)
    license_jti: str = Field(index=True, max_length=64)
    customer_email: str = Field(max_length=256)
    status: str = Field(default="queued", max_length=16)
    output_path: Optional[str] = Field(default=None, max_length=512)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    completed_at: Optional[datetime] = Field(default=None)
    expires_at: Optional[datetime] = Field(default=None)


class BetaRequest(SQLModel, table=True):
    """031 — Beta access waitlist + auto/manual approval queue."""

    __tablename__ = "beta_requests"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, max_length=256)
    name: str = Field(default="", max_length=128)
    company: str = Field(default="", max_length=128)
    use_case: str = Field(default="", max_length=1024)
    lang: str = Field(default="en", max_length=8)
    status: str = Field(default="pending", index=True, max_length=16)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), index=True
    )
    approved_at: Optional[datetime] = Field(default=None)
    rejected_at: Optional[datetime] = Field(default=None)
    rejected_reason: Optional[str] = Field(default=None, max_length=512)
    license_jti: Optional[str] = Field(default=None, max_length=64)


class WizardEvent(SQLModel, table=True):
    """Per-step drop-off metrics for the setup wizard.

    One row per step transition. A repeated (session_id, step_num) pair updates
    `completed_at` instead of inserting again.
    """

    __tablename__ = "wizard_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(index=True, max_length=64)
    step_num: int = Field(index=True)
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    completed_at: Optional[datetime] = Field(default=None)


class WebhookEvent(SQLModel, table=True):
    """Webhook idempotency: an event_id is processed exactly once.

    Payment providers retry the same event. The handler inserts first; a UNIQUE
    violation means the event was already handled, and it answers 200 without
    doing the work twice.
    """

    __tablename__ = "webhook_events"

    event_id: str = Field(primary_key=True, max_length=64)
    event_type: str = Field(max_length=64, index=True)
    received_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    processed_at: Optional[datetime] = Field(default=None)
    license_jti: Optional[str] = Field(default=None, max_length=64, index=True)
    error: Optional[str] = Field(default=None, max_length=512)
    # Postgres RLS tenant column (see VaultAuditEntry).
    tenant_id: str = Field(default="_unknown", max_length=64, index=True)


# ───── feature_usage + meetings ─────────────────────────────────────────


class FeatureUsageLog(SQLModel, table=True):
    """Append-only feature usage events.

    Aggregation done at query time via GROUP BY (SQLite has no materialized
    views; rows expected to stay under 1M for a self-host single-tenant
    deployment, which is well within SQLite's comfort zone).
    """

    __tablename__ = "feature_usage_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_slug: str = Field(max_length=64, index=True, default="default")
    feature_id: str = Field(max_length=64, index=True)
    actor_email: Optional[str] = Field(default=None, max_length=254)
    ts: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), index=True
    )


class Meeting(SQLModel, table=True):
    """S20.4 — uploaded meeting recording metadata + WhisperX result."""

    __tablename__ = "meetings"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_slug: str = Field(max_length=64, index=True, default="default")
    uploader_email: str = Field(max_length=254, index=True)
    filename: str = Field(max_length=256)
    duration_sec: float = Field(default=0.0)
    speaker_count: int = Field(default=0)
    status: str = Field(max_length=32, default="pending")  # pending|done|error
    summary: str = Field(default="", max_length=4096)
    error_message: Optional[str] = Field(default=None, max_length=512)
    # SHA-256 of the audio bytes — the same recording uploaded twice is one
    # meeting, one transcription bill, and one copy in the vector store.
    audio_sha256: str = Field(default="", max_length=64, index=True)
    # Set when the recording transcribed without failing but holds no usable
    # speech. Non-empty means it was deliberately kept out of the knowledge
    # base, and this sentence is what the operator is shown.
    quality_note: str = Field(default="", max_length=512)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), index=True
    )
    completed_at: Optional[datetime] = Field(default=None)


class MeetingSegment(SQLModel, table=True):
    """S20.4 — single transcript segment for a meeting (1:N to Meeting)."""

    __tablename__ = "meeting_segments"

    id: Optional[int] = Field(default=None, primary_key=True)
    meeting_id: int = Field(index=True)
    speaker_id: str = Field(max_length=32)
    start_sec: float
    end_sec: float
    text: str


class UsageLog(SQLModel, table=True):
    """Phase 4 / Q2.CO1 — append-only provider usage log.

    One row per cascade provider call. Aggregated at query time by
    `quota_monitor._query_usage_sum` to drive 80%/95% threshold warnings.
    """

    __tablename__ = "usage_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    provider: str = Field(max_length=32, index=True)
    tenant_slug: str = Field(max_length=64, default="default", index=True)
    tokens: int = Field(default=0)
    cost_usd: float = Field(default=0.0)
    request_id: Optional[str] = Field(default=None, max_length=64)
    ts: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), index=True
    )


# ───── chat sessions + messages ─────────────────────────────────────────


class ChatSession(SQLModel, table=True):
    """Multi-tenant chat session header.

    Four columns exist for the sidebar rather than for the chat itself:
    `pinned`, `archived_at`, `last_activity_at` (sort key, denormalised from
    chat_messages.created_at) and `message_count` (a counter cache that spares
    the sidebar a per-row COUNT()).
    """

    __tablename__ = "chat_sessions"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_slug: str = Field(
        max_length=64, index=True, default="default"
    )
    user_email: str = Field(max_length=254, index=True)
    title: str = Field(max_length=200, default="New chat")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), index=True
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    # Threading metadata
    pinned: bool = Field(default=False)
    archived_at: Optional[datetime] = Field(default=None, index=True)
    last_activity_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), index=True
    )
    message_count: int = Field(default=0)


class ChatMessage(SQLModel, table=True):
    """A single chat message (1:N to ChatSession)."""

    __tablename__ = "chat_messages"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="chat_sessions.id", index=True)
    role: str = Field(max_length=16)  # user|assistant|system|tool
    content: str = Field(max_length=16384)
    provider: Optional[str] = Field(default=None, max_length=64)
    tool_calls: Optional[str] = Field(default=None, max_length=8192)
    tokens_used: Optional[int] = Field(default=None)
    latency_ms: Optional[int] = Field(default=None)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), index=True
    )


class User(SQLModel, table=True):
    """Phase 2 / Q3 / Q2.CO5 — multi-admin user table.

    Replaces the single-row `admin_credentials.json` long-term. For
    backward-compat the magic-link claim flow ALSO writes
    `admin_credentials.json` so the existing `/auth/login` panel session
    code path keeps working without coupled changes.

    `status`:
      pending  — signup recorded, magic-link not yet claimed
      active   — claim completed, can log in
      revoked  — admin disabled the account
    """

    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(max_length=254, index=True, unique=True)
    password_hash: str = Field(max_length=128)
    tenant_slug: str = Field(max_length=64, index=True, default="default")
    role: str = Field(max_length=32, default="admin")
    status: str = Field(max_length=32, default="pending", index=True)
    magic_token: Optional[str] = Field(
        default=None, max_length=128, index=True
    )
    magic_expires_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    claimed_at: Optional[datetime] = Field(default=None)


class TenantInvite(SQLModel, table=True):
    """Pending tenant invite plus the magic-link hash.

    The plaintext magic-link token is mailed to the recipient; only the
    HMAC-SHA256 digest is stored here so a database read cannot recover
    a usable token. ``status`` transitions:
        pending  → invite created, awaiting consume
        accepted → magic_claim succeeded; ``accepted_at`` populated
        revoked  → admin revoked; ``revoked_at`` populated
        expired  → consume attempt past ``expires_at`` (lazy update)
    """

    __tablename__ = "tenant_invites"

    id: Optional[int] = Field(default=None, primary_key=True)
    invite_id: str = Field(index=True, unique=True, max_length=24)
    email: str = Field(index=True, max_length=255)
    role: str = Field(max_length=20)
    tenant_id: str = Field(index=True, max_length=64)
    invited_by: str = Field(max_length=255)
    magic_token_hash: str = Field(unique=True, max_length=64)
    expires_at: datetime
    accepted_at: Optional[datetime] = Field(default=None)
    revoked_at: Optional[datetime] = Field(default=None)
    status: str = Field(max_length=20, default="pending")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class TenantInstalledPlugin(SQLModel, table=True):
    """Durable record of a tenant's plugin install.

    Marketplace install handler writes one row per ``(tenant, plugin)``
    pair. ``uninstalled_at`` is set on /uninstall instead of deleting the
    row so audit history stays intact.
    """

    __tablename__ = "tenant_installed_plugins"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(index=True, max_length=64)
    plugin_id: str = Field(index=True, max_length=64)
    version: str = Field(max_length=32)
    sandbox_container_id: Optional[str] = Field(default=None, max_length=64)
    installed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    uninstalled_at: Optional[datetime] = Field(default=None)


class MintedTokenBlacklist(SQLModel, table=True):
    """Q10-L6-002 — revoked MCP integration tokens.

    Issued tokens are HMAC-only (no DB row at mint), so revocation is
    handled by adding the token's payload digest here. `verify_token`
    consults this table on every call; if the digest is present, auth
    fails before downstream tool/hook routing.

    Stored digest (not the raw token) so leaking the table itself does
    not disclose live bearer credentials. `expires_at` mirrors the
    token's `exp` claim — rows can be GC'd after that point because an
    expired token is already rejected on its own.
    """

    __tablename__ = "minted_token_blacklist"

    id: Optional[int] = Field(default=None, primary_key=True)
    token_digest: str = Field(max_length=64, index=True, unique=True)
    tenant_slug: str = Field(max_length=64, index=True, default="default")
    label: str = Field(max_length=64, default="")
    revoked_by: str = Field(max_length=254, default="")
    revoked_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), index=True
    )
    expires_at: Optional[datetime] = Field(default=None, index=True)
    reason: Optional[str] = Field(default=None, max_length=256)


class MintedTokenRecord(SQLModel, table=True):
    """Issuance ledger for MCP integration tokens — metadata only (digest, never
    the raw token). Tokens stay HMAC-stateless for verification; this table lets
    the panel LIST and individually revoke MULTIPLE active tokens. Revocation
    status is derived by joining ``minted_token_blacklist`` on ``token_digest``.
    """

    __tablename__ = "minted_token_record"

    id: Optional[int] = Field(default=None, primary_key=True)
    token_digest: str = Field(max_length=64, index=True, unique=True)
    tenant_slug: str = Field(max_length=64, index=True, default="default")
    label: str = Field(max_length=64, default="")
    scope: str = Field(max_length=64, default="all")
    issued_by: str = Field(max_length=254, default="")
    issued_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), index=True
    )
    expires_at: Optional[datetime] = Field(default=None, index=True)


class FailedLoginAttempt(SQLModel, table=True):
    """Per-email backoff state for /auth/login.

    Each unsuccessful login increments ``attempts_count`` for the
    submitted email; the exponential-backoff helper extends
    ``locked_until`` so subsequent attempts within the window are
    rejected with HTTP 429 before the password is even verified.

    On a successful login the row is deleted (back to zero). The
    @limiter.limit("5/minute") decorator on the route guards against IP
    fan-out brute force; this table guards against patient single-IP
    credential stuffing.
    """

    __tablename__ = "failed_login_attempts"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(max_length=256, index=True, unique=True)
    tenant_slug: Optional[str] = Field(default=None, max_length=64)
    attempts_count: int = Field(default=0)
    last_attempt_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    locked_until: Optional[datetime] = Field(default=None, index=True)


class AgentRun(SQLModel, table=True):
    """Agentic Growth — one agent execution (audit + activity feed source).

    Every `run_agent` call is logged here so the dashboard activity feed, the
    Agent Registry "running" state and the audit trail share one record.
    Tenant-scoped (RLS-enrolled in 0020).
    """

    __tablename__ = "agent_runs"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_slug: str = Field(max_length=64, index=True, default="default")
    agent_id: str = Field(max_length=64, index=True)
    task: str = Field(max_length=8000)
    summary: str = Field(default="", max_length=4096)
    confidence: float = Field(default=0.0)
    risk: str = Field(max_length=16, default="low")
    requires_approval: bool = Field(default=False)
    provider: str = Field(default="", max_length=64)
    evidence_json: str = Field(default="[]")
    payload_json: str = Field(default="{}")
    elapsed_ms: int = Field(default=0)
    actor: str = Field(default="", max_length=254)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), index=True
    )


class ApprovalItem(SQLModel, table=True):
    """Agentic Growth — a risky agent action awaiting human approval.

    Replaces the in-memory ledger (`workflow_v10/approval.py`) for the
    Approval Center. Carries the agent's rationale + evidence + risk + consent +
    policy result so the reviewer decides with full context. Tenant-scoped.
    """

    __tablename__ = "approval_items"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_slug: str = Field(max_length=64, index=True, default="default")
    agent_id: str = Field(default="", max_length=64, index=True)
    agent_run_id: Optional[int] = Field(default=None, index=True)
    action: str = Field(max_length=1024)
    target_company: str = Field(default="", max_length=256)
    target_person: str = Field(default="", max_length=256)
    channel: str = Field(default="", max_length=64)
    rationale: str = Field(default="", max_length=4096)
    evidence_json: str = Field(default="[]")
    proposed_message: str = Field(default="", max_length=8192)
    risk: str = Field(default="medium", max_length=16)
    consent_status: str = Field(default="", max_length=32)
    policy_result: str = Field(default="requires_approval", max_length=64)
    # pending | approved | rejected | edited
    status: str = Field(default="pending", max_length=16, index=True)
    decided_by: str = Field(default="", max_length=254)
    decided_at: Optional[datetime] = Field(default=None)
    outcome: str = Field(default="", max_length=512)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), index=True
    )
    escalate_at: Optional[datetime] = Field(default=None)


class SavedWorkflow(SQLModel, table=True):
    """A reusable, named workflow definition saved by an operator.

    The synthesize/execute endpoints handle ad-hoc runs + job tracking, but a
    workflow built in the Workflow Builder could not be PERSISTED for reuse
    (the panel "Save" button was a no-op). This table stores the workflow JSON
    definition, tenant-scoped, so it can be listed + reloaded later.
    """

    __tablename__ = "saved_workflow"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_slug: str = Field(max_length=64, index=True, default="default")
    name: str = Field(max_length=200)
    # The full WorkflowDefinition JSON (nodes/edges/trigger) as a string.
    definition_json: str = Field(default="{}")
    created_by: str = Field(max_length=254, default="")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
