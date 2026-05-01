"""T-057 — Initial baseline of pre-OAuth ABS tables (caveat clear).

This revision formalises the legacy ABS schema (licenses, email_queue,
oauth_states, connected_secrets, vault audit, GDPR consents, beta requests,
wizard events, webhook idempotency) so a clean alembic-managed install no
longer relies on SQLModel.metadata.create_all().

For existing deployments that were already running on `create_all()`,
stamp this revision after upgrading: `alembic stamp 0000_init_baseline`.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0000_init_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. licenses
    op.create_table(
        "licenses",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("jti", sa.String(64), nullable=False),
        sa.Column(
            "customer_email",
            sa.String(256),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column(
            "customer_id_stripe",
            sa.String(128),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column(
            "tier",
            sa.String(32),
            nullable=False,
            server_default=sa.text("'self-host'"),
        ),
        sa.Column(
            "seat_count",
            sa.Integer,
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(512), nullable=True),
        sa.Column("first_tool_call_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "preferred_lang",
            sa.String(8),
            nullable=False,
            server_default=sa.text("'en'"),
        ),
        sa.Column("scheduled_delete_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f("ix_licenses_jti"), "licenses", ["jti"], unique=True)
    op.create_index(op.f("ix_licenses_customer_email"), "licenses", ["customer_email"])
    op.create_index(
        op.f("ix_licenses_customer_id_stripe"), "licenses", ["customer_id_stripe"]
    )

    # 2. email_queue
    op.create_table(
        "email_queue",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("license_jti", sa.String(64), nullable=False),
        sa.Column("customer_email", sa.String(256), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "attempts",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("error", sa.String(512), nullable=True),
        sa.Column(
            "unsubscribed",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index(
        op.f("ix_email_queue_license_jti"), "email_queue", ["license_jti"]
    )
    op.create_index(op.f("ix_email_queue_kind"), "email_queue", ["kind"])
    op.create_index(
        op.f("ix_email_queue_scheduled_at"), "email_queue", ["scheduled_at"]
    )

    # 3. oauth_states
    op.create_table(
        "oauth_states",
        sa.Column("state", sa.String(64), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("redirect_url", sa.String(512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_oauth_states_provider"), "oauth_states", ["provider"])

    # 4. connected_secrets
    op.create_table(
        "connected_secrets",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("key_name", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("encrypted_value", sa.String(8192), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_validated_ok", sa.Boolean, nullable=True),
        sa.Column("last_validated_error", sa.String(512), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refresh_token_encrypted", sa.String(8192), nullable=True),
    )
    op.create_index(
        op.f("ix_connected_secrets_key_name"),
        "connected_secrets",
        ["key_name"],
        unique=True,
    )
    op.create_index(
        op.f("ix_connected_secrets_provider"), "connected_secrets", ["provider"]
    )

    # 5. vault_audit_entries
    op.create_table(
        "vault_audit_entries",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column(
            "actor",
            sa.String(64),
            nullable=False,
            server_default=sa.text("'system'"),
        ),
        sa.Column("target_key", sa.String(128), nullable=True),
        sa.Column("detail", sa.String(512), nullable=True),
        sa.Column("hmac", sa.String(64), nullable=False),
        sa.Column(
            "prev_hmac",
            sa.String(64),
            nullable=False,
            server_default=sa.text("''"),
        ),
    )
    op.create_index(
        op.f("ix_vault_audit_entries_ts"), "vault_audit_entries", ["ts"]
    )
    op.create_index(
        op.f("ix_vault_audit_entries_action"), "vault_audit_entries", ["action"]
    )

    # 6. customer_audit_entries
    op.create_table(
        "customer_audit_entries",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("license_jti", sa.String(64), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("resource", sa.String(128), nullable=True),
        sa.Column("detail", sa.String(512), nullable=True),
        sa.Column("ip_hash", sa.String(32), nullable=True),
        sa.Column("user_agent_short", sa.String(128), nullable=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        op.f("ix_customer_audit_entries_license_jti"),
        "customer_audit_entries",
        ["license_jti"],
    )
    op.create_index(
        op.f("ix_customer_audit_entries_action"),
        "customer_audit_entries",
        ["action"],
    )
    op.create_index(
        op.f("ix_customer_audit_entries_ts"), "customer_audit_entries", ["ts"]
    )

    # 7. consents
    op.create_table(
        "consents",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("license_jti", sa.String(64), nullable=False),
        sa.Column("consent_type", sa.String(64), nullable=False),
        sa.Column(
            "version",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'1.0'"),
        ),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "source",
            sa.String(32),
            nullable=False,
            server_default=sa.text("'setup_wizard'"),
        ),
    )
    op.create_index(op.f("ix_consents_license_jti"), "consents", ["license_jti"])
    op.create_index(op.f("ix_consents_consent_type"), "consents", ["consent_type"])

    # 8. data_export_jobs
    op.create_table(
        "data_export_jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("job_id", sa.String(48), nullable=False),
        sa.Column("license_jti", sa.String(64), nullable=False),
        sa.Column("customer_email", sa.String(256), nullable=False),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'queued'"),
        ),
        sa.Column("output_path", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_data_export_jobs_job_id"),
        "data_export_jobs",
        ["job_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_data_export_jobs_license_jti"),
        "data_export_jobs",
        ["license_jti"],
    )

    # 9. beta_requests
    op.create_table(
        "beta_requests",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(256), nullable=False),
        sa.Column(
            "name",
            sa.String(128),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column(
            "company",
            sa.String(128),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column(
            "use_case",
            sa.String(1024),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column(
            "lang",
            sa.String(8),
            nullable=False,
            server_default=sa.text("'en'"),
        ),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_reason", sa.String(512), nullable=True),
        sa.Column("license_jti", sa.String(64), nullable=True),
    )
    op.create_index(op.f("ix_beta_requests_email"), "beta_requests", ["email"])
    op.create_index(op.f("ix_beta_requests_status"), "beta_requests", ["status"])
    op.create_index(
        op.f("ix_beta_requests_created_at"), "beta_requests", ["created_at"]
    )

    # 10. wizard_events
    op.create_table(
        "wizard_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("step_num", sa.Integer, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_wizard_events_session_id"), "wizard_events", ["session_id"]
    )
    op.create_index(op.f("ix_wizard_events_step_num"), "wizard_events", ["step_num"])

    # 11. webhook_events
    op.create_table(
        "webhook_events",
        sa.Column("event_id", sa.String(64), primary_key=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("license_jti", sa.String(64), nullable=True),
        sa.Column("error", sa.String(512), nullable=True),
    )
    op.create_index(
        op.f("ix_webhook_events_event_type"), "webhook_events", ["event_type"]
    )
    op.create_index(
        op.f("ix_webhook_events_license_jti"), "webhook_events", ["license_jti"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_webhook_events_license_jti"), table_name="webhook_events")
    op.drop_index(op.f("ix_webhook_events_event_type"), table_name="webhook_events")
    op.drop_table("webhook_events")

    op.drop_index(op.f("ix_wizard_events_step_num"), table_name="wizard_events")
    op.drop_index(op.f("ix_wizard_events_session_id"), table_name="wizard_events")
    op.drop_table("wizard_events")

    op.drop_index(op.f("ix_beta_requests_created_at"), table_name="beta_requests")
    op.drop_index(op.f("ix_beta_requests_status"), table_name="beta_requests")
    op.drop_index(op.f("ix_beta_requests_email"), table_name="beta_requests")
    op.drop_table("beta_requests")

    op.drop_index(
        op.f("ix_data_export_jobs_license_jti"), table_name="data_export_jobs"
    )
    op.drop_index(op.f("ix_data_export_jobs_job_id"), table_name="data_export_jobs")
    op.drop_table("data_export_jobs")

    op.drop_index(op.f("ix_consents_consent_type"), table_name="consents")
    op.drop_index(op.f("ix_consents_license_jti"), table_name="consents")
    op.drop_table("consents")

    op.drop_index(
        op.f("ix_customer_audit_entries_ts"), table_name="customer_audit_entries"
    )
    op.drop_index(
        op.f("ix_customer_audit_entries_action"), table_name="customer_audit_entries"
    )
    op.drop_index(
        op.f("ix_customer_audit_entries_license_jti"),
        table_name="customer_audit_entries",
    )
    op.drop_table("customer_audit_entries")

    op.drop_index(
        op.f("ix_vault_audit_entries_action"), table_name="vault_audit_entries"
    )
    op.drop_index(op.f("ix_vault_audit_entries_ts"), table_name="vault_audit_entries")
    op.drop_table("vault_audit_entries")

    op.drop_index(
        op.f("ix_connected_secrets_provider"), table_name="connected_secrets"
    )
    op.drop_index(
        op.f("ix_connected_secrets_key_name"), table_name="connected_secrets"
    )
    op.drop_table("connected_secrets")

    op.drop_index(op.f("ix_oauth_states_provider"), table_name="oauth_states")
    op.drop_table("oauth_states")

    op.drop_index(op.f("ix_email_queue_scheduled_at"), table_name="email_queue")
    op.drop_index(op.f("ix_email_queue_kind"), table_name="email_queue")
    op.drop_index(op.f("ix_email_queue_license_jti"), table_name="email_queue")
    op.drop_table("email_queue")

    op.drop_index(op.f("ix_licenses_customer_id_stripe"), table_name="licenses")
    op.drop_index(op.f("ix_licenses_customer_email"), table_name="licenses")
    op.drop_index(op.f("ix_licenses_jti"), table_name="licenses")
    op.drop_table("licenses")
