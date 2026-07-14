# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

import os
import warnings
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


def _promote_legacy_license_key_env() -> None:
    """Accept the legacy un-prefixed LICENSE_KEY env var.

    The 023 settings model uses ``env_prefix='ABS_'``, so a customer
    whose ``.env`` carries the un-prefixed ``LICENSE_KEY=...`` (the
    name docs/quickstart-30min.md used to ship) would
    silently boot in demo mode. Detect the typo before pydantic
    parses, promote the value into ``ABS_LICENSE_KEY``, and emit a
    DeprecationWarning so the operator sees the rename in logs.

    Backwards compatibility window: one minor release. Customers who
    refresh their ``.env`` from ``.env.example`` (already ABS-prefixed)
    will never trip this branch.
    """
    legacy = os.environ.get("LICENSE_KEY")
    canonical = os.environ.get("ABS_LICENSE_KEY")
    if legacy and not canonical:
        os.environ["ABS_LICENSE_KEY"] = legacy
        warnings.warn(
            "LICENSE_KEY env var is deprecated; rename to ABS_LICENSE_KEY "
            "(see docs/quickstart-30min.md). Value was auto-promoted for "
            "this boot.",
            DeprecationWarning,
            stacklevel=2,
        )


_promote_legacy_license_key_env()


class Settings(BaseSettings):
    # General
    admin_email: str = ""
    domain: str = "abs.local"
    ssl_mode: str = "internal"  # "internal" | "acme"

    # License (set on the customer side)
    license_key: str = ""

    # License signing keys. Only the public key is needed to verify a license;
    # the private key stays with whoever issues them.
    private_key_path: str = "/app/data/private.pem"
    public_key_path: str = "/app/data/public.pem"

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    # SMTP — unset falls back to logging the mail to the console
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@automatiabcn.com"

    # Unsubscribe JWT secret (HS256, 1 year expiry)
    unsubscribe_jwt_secret: str = "dev-insecure-unsubscribe-change-in-prod"

    # Admin bearer token (demo reset, etc.)
    admin_token: str = "dev-insecure-admin-change-in-prod"

    # Discord webhook — unset is a no-op, never a boot failure
    discord_webhook_url: str = ""

    # Slack signing secret (HMAC SHA256)
    slack_signing_secret: str = ""

    # GitHub App (parallel to OAuth)
    github_app_id: str = ""
    github_app_private_key: str = ""  # PEM, multi-line OK
    github_app_webhook_secret: str = ""
    # GitHub OAuth App (smart-link connect + token refresh). These were read
    # via getattr() by app/api/smart_link.py and app/smart_link/oauth_refresh.py
    # but never declared, so ABS_GITHUB_CLIENT_ID / ABS_GITHUB_CLIENT_SECRET
    # were silently ignored and both the initial code exchange and the refresh
    # sent empty credentials (GitHub rejects → connect/refresh always failed).
    github_client_id: str = ""
    github_client_secret: str = ""

    # Rate limiting (slowapi)
    rate_limit_enabled: bool = True
    rate_limit_storage_uri: str = "memory://"  # Redis: redis://host:6379/0
    # Comma-separated proxy IPs whose X-Forwarded-For
    # header may be trusted. Anything outside this allowlist falls back
    # to request.client.host so a malicious origin cannot spoof its IP.
    trusted_proxies: str = "127.0.0.1,::1"

    # X-ABS-Audience header enforcement (caveat #11)
    audience_enforce: bool = False
    audience_value: str = "abs-mcp"

    # GDPR audit log IP hashing + delete confirmation JWT
    audit_ip_salt: str = "dev-insecure-audit-salt-change-in-prod"
    delete_confirm_jwt_secret: str = "dev-insecure-delete-jwt-secret"

    # Beta portal
    beta_auto_approve: bool = False
    beta_admin_token: str = "dev-insecure-beta-admin-change-in-prod"

    # Admin dashboard (separate from panel /auth)
    admin_password_hash: str = ""  # bcrypt hash; empty = login disabled
    admin_jwt_secret: str = "dev-insecure-admin-jwt-change-in-prod"
    admin_ip_whitelist: str = ""  # comma-separated; empty = no IP filter
    churn_threshold: float = 0.5

    # HMAC secret for magic-link token hashing.
    # Empty falls back to admin_jwt_secret (still per-install random in
    # prod) so existing customers don't have to set a new env var.
    magic_link_hmac_secret: str = ""

    # Public hostname used to build magic-link URLs in
    # invite emails. Defaults to the dev/local origin; customer compose
    # overrides via ABS_PUBLIC_HOSTNAME.
    public_hostname: str = "http://localhost:3000"

    # Demo readiness
    demo_mode: bool = False
    provider_mock: bool = False  # forces app.providers.mock for live calls
    demo_seed_version: str = "v1"

    # Release version — single source of truth surfaced by /v1/status,
    # /v1/admin/status/full and the panel footer. Overridable via ABS_VERSION.
    version: str = "1.0.6"

    # DB
    database_url: str = "sqlite:////app/data/abs.db"

    # Panel / Auth
    session_secret: str = "dev-insecure-change-in-prod"
    admin_password_bootstrap: str = "CHANGEME"
    # Signs minted `abs_mcp_*` delegation tokens. Empty means "reuse
    # session_secret", which keeps tokens minted before the split valid.
    # Set it to give MCP tokens a rotation lifetime of their own — panel
    # cookies and long-lived MCP tokens should not share one key.
    mcp_token_secret: str = ""

    # Provider API keys (encrypted at rest via the sops vault below)
    anthropic_api_key: str = ""
    # Claude API is opt-in (paid). Default off; set ABS_ANTHROPIC_ENABLED=true to enable.
    anthropic_enabled: bool = False
    claude_monthly_token_limit: int = 1_000_000
    # Mock mode for cascade fallback testing without a real API key.
    # Values: off | ok | rate_limit | timeout | provider_500 | random
    anthropic_mock_mode: str = "off"
    # RAGAS evaluator backend toggle: mock | groq
    ragas_backend: str = "mock"
    groq_api_key: str = ""
    groq_whisper_model: str = "whisper-large-v3"
    cerebras_api_key: str = ""
    gemini_api_key: str = ""
    cf_account_id: str = ""
    cf_api_token: str = ""
    cohere_api_key: str = ""
    openrouter_api_key: str = ""
    vllm_url: str = ""
    vllm_api_key: str = ""  # self-hosted vLLM ignores it; pass org token if needed
    ollama_url: str = ""

    # Ollama-first cascade (local $0 -> groq cloud -> anthropic).
    ollama_first_enabled: bool = False
    ollama_first_health_timeout_s: float = 1.5

    # MCP
    # Default ON. It was off, which meant the tools — which are the product —
    # were served to any caller with an access key, on a server with no
    # subscription and an expired trial. A customer's editor would have kept
    # working forever while the panel told them their trial had ended. Turn it
    # off only for an install whose licensing is handled another way (a site
    # agreement, an air-gapped deployment).
    mcp_require_license: bool = True
    # Enforce the minted abs_mcp_ bearer token on every /mcp transport request.
    # Default ON: without it the streamable-http endpoint serves all tools to
    # any caller that passes the host allowlist (no per-user auth). Set
    # ABS_MCP_AUTH_ENFORCE=false ONLY for a trusted, network-isolated dev box;
    # boot logs a loud warning when disabled.
    mcp_auth_enforce: bool = True
    # preview_patch/apply_patch read+write arbitrary existing files (no path
    # allowlist). Off the network /mcp surface by default — opt in only when an
    # operator drives their OWN deployment via Claude Code. NEVER enable when
    # delegation tokens are handed to team members / external clients.
    mcp_expose_patch_tools: bool = False

    # MCP rag_query store selection. Empty (default) → the operator Chroma KB
    # (app/rag/, single collection, no tenant scoping). When set to a tenant_id
    # the MCP rag_query tool instead searches the Qdrant document store for THAT
    # tenant — so docs uploaded through the panel (/v1/rag/ingest) become
    # answerable from Claude Code / Codex delegation. Single-tenant deployments
    # (e.g. one customer org) set this to their tenant_id; multi-tenant SaaS
    # leaves it empty so a shared delegation token cannot read another tenant's
    # documents through MCP.
    mcp_rag_tenant: str = ""

    # External MCP federation (ABS as MCP *client*). A tenant registers a
    # third-party MCP server from the panel; ABS connects out, discovers its
    # tools and (Slice 2) federates them. OFF by default — opt-in per
    # deployment. ``allow_private`` lets the outbound client reach loopback /
    # private IPs (needed for local dogfood tests); MUST stay False on any
    # internet-reachable deployment or it becomes an SSRF pivot.
    external_mcp_enabled: bool = False
    external_mcp_allow_private: bool = False
    external_mcp_timeout_seconds: float = 20.0
    external_mcp_max_tools: int = 200
    # Re-expose federated external tools through ABS's OWN /mcp transport so the
    # operator's connected Claude Code/Codex sees them (namespaced ext_<slug>__).
    # The /mcp server is a single shared FastMCP instance (tools are global), so
    # this is only tenant-safe on a SINGLE-TENANT deployment (a self-host box,
    # tenant=default). Leave OFF on multi-tenant SaaS until per-session tool
    # filtering lands; server-side agent federation stays tenant-scoped regardless.
    external_mcp_federate_to_mcp: bool = False

    # Hooks (007)
    hooks_enabled: bool = True
    hooks_mode: str = "middleware"  # "middleware" | "native" | "both"
    cache_dir: str = "/app/data/cache"
    artifacts_dir: str = "/app/data/artifacts"
    data_dir: str = "/app/data"  # workflow_state.db, judge_log.jsonl, rag_chroma/

    # Workflow durability + MLX
    workflow_durable: bool = False  # persist pipeline state to workflow_state.db
    mlx_url: str = ""  # Apple Silicon Neural Engine bridge (unset degrades gracefully)

    # Stripe Price IDs — copy them from setup_stripe_products.py output into .env
    # The product is a monthly subscription: both of these must be *recurring*
    # prices, and the team one is priced per seat (quantity = seats).
    abs_price_solo: str = ""  # Stripe Price ID — Solo, per month
    abs_price_team: str = ""  # Stripe Price ID — Team, per seat per month

    # Where a customer's server asks for next month's key. Empty means it never
    # asks — correct for an air-gapped install with a hand-delivered key, and the
    # gate's grace window still applies.
    license_renewal_url: str = "https://abs.automatiabcn.com/v1/license/renew"

    # Retired one-off SKUs. Kept so an existing .env with these set still loads
    # rather than crashing on an unknown field.
    abs_price_self_host: str = ""
    abs_price_team_5: str = ""
    abs_price_team_10: str = ""

    # List prices (USD per month). Default 0.0 = pricing not configured;
    # operators MUST set these in their own .env. Solo is per subscription; team
    # is per seat, per month.
    abs_seat_price_solo: float = 0.0
    abs_seat_price_team: float = 0.0

    # Retired one-off list prices. Kept so an existing .env still loads.
    abs_seat_price_self_host: float = 0.0
    abs_seat_price_team_5: float = 0.0
    abs_seat_price_team_10: float = 0.0
    # Admin dashboard widget multiplier (revenue extrapolation: licenses × X / mo).
    abs_revenue_widget_multiplier: float = 0.0
    # Maintenance add-on yearly fee + beta annual offer (used in email templates).
    abs_maintenance_price_yearly: float = 0.0
    abs_annual_offer_strike: float = 0.0
    abs_annual_offer_price: float = 0.0

    # Encrypted secrets vault (sops + age)
    vault_key_path: str = (
        "/app/vault-key/age.key"  # master key — mount on its own volume
    )
    vault_secrets_path: str = "/app/data/secrets.yaml"  # encrypted secrets file

    # Vault production hardening
    vault_require_sops: bool = False  # production=True; boot fail-fast if sops missing
    vault_audit_hmac_secret: str = "dev-insecure-vault-hmac-change-in-prod"
    vault_min_sops_version: str = "3.7.0"

    # Update channel + health monitor
    update_manifest_url: str = "https://abs.automatiabcn.com/releases/manifest.json"
    health_interval_seconds: int = 60

    # Manifest RS256 signature (production: True / dev/test: False)
    update_signature_required: bool = True

    # NATS JetStream event bus
    nats_url: str = "nats://nats:4222"
    nats_event_stream: str = "ABS_EVENTS"
    nats_event_subjects: str = "abs.events.>"  # comma-separated for multi-subject

    # OAuth 2.1 issuer (used in JWT iss + OIDC discovery)
    oauth_issuer: str = "https://abs.local"

    # Cerbos PDP host (HTTP transport; gRPC available via cerbos:3593)
    cerbos_host: str = "http://cerbos:3592"

    # Qdrant vector DB (multi-tenant via payload index)
    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: str = ""
    qdrant_default_collection: str = "abs_documents"
    qdrant_default_vector_size: int = 1024  # BGE-M3
    qdrant_snapshot_dir: str = "/qdrant/snapshots"

    # BGE-M3 embedding service.
    # `auto` picks the best real backend the box can run (ollama →
    # sentence_transformers → cohere), and only falls back to `mock` when there
    # is none. It used to default straight to `mock`, whose vectors are sha256 of
    # the text: document search still returned five chunks and the model still
    # answered from them, but the chunks were unrelated to the question. Real
    # backends by name: cohere | ollama | sentence_transformers | onnx_cuda |
    # onnx_cpu. `mock` is for tests.
    embedding_backend: str = "auto"
    embedding_model_path: str = ""  # ONNX backends only
    # `cohere` backend: real semantic embeddings via the customer's existing
    # Cohere key (bring-your-own-key), 1024-dim, zero local footprint.
    cohere_embed_model: str = "embed-multilingual-v3.0"  # 1024-dim, multilingual
    embedding_device: str = "cpu"  # SentenceTransformers backend only
    # Ollama embedding model (when embedding_backend=ollama). bge-m3 is 1024-dim
    # and multilingual — it matches qdrant_default_vector_size above, and the
    # product is used in more than one language. nomic-embed-text, the previous
    # default, is 768-dim and English-leaning: it disagreed with the collection
    # it was writing into. ABS_EMBEDDING_MODEL overrides.
    embedding_model: str = "bge-m3"
    embedding_batch_size: int = 32
    embedding_min_batch: int = 4

    # Reranker (Qwen3-Reranker-4B + Cohere fallback + mock)
    # "auto" resolves to what this server can actually do (cohere → onnx → none).
    # It was "mock" — Jaccard word overlap, behind an API field that says
    # "cross-encoder rerank", and measurably worse than not reranking at all.
    rerank_backend: str = "auto"  # auto | none | qwen3_onnx | cohere | mock (tests)
    rerank_model_path: str = ""  # ONNX path
    rerank_device: str = "cpu"  # cpu | cuda
    rerank_cache_ttl_seconds: int = 3600
    rerank_cache_max_entries: int = 4096

    # RAG cost + usage tracking (LangFuse-compatible JSONL)
    usage_log_path: str = "data/rag_usage.jsonl"
    usage_log_sample_rate: float = 1.0  # 0.0..1.0; production=1.0, dev=0.1

    # LangFuse client (no-op when disabled)
    langfuse_enabled: bool = False
    langfuse_host: str = "https://langfuse.abs.local"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""

    # Cosign signature verification (lands later)
    cosign_skip: bool = True  # dev default; prod must set ABS_COSIGN_SKIP=false
    cosign_public_key_path: str = "/etc/abs/cosign.pub"

    # Text2SQL guard-rails
    text2sql_backend: str = "mock"
    text2sql_model_name: str = ""
    text2sql_training_path: str = ""
    text2sql_sandbox_schema_path: str = ""
    text2sql_read_only_role: str = "abs_ro"
    cortex_api_key: str = ""
    cortex_endpoint: str = ""

    # Prompt management
    prompt_store_path: str = "data/prompts.jsonl"

    # RAGAS CI eval
    ragas_backend: str = "mock"
    ragas_baseline_path: str = "tests/fixtures/ragas_baseline.json"
    ragas_max_drop: float = 0.05

    # Meeting pipeline
    transcribe_backend: str = "mock"  # mock | whisperx | deepgram | groq
    transcribe_device: str = "cuda"
    deepgram_api_key: str = ""
    recall_backend: str = "mock"
    recall_ai_api_key: str = ""
    recall_ai_cost_cap_usd_per_day: float = 50.0
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    elevenlabs_budget_usd: float = 50.0
    # ElevenLabs is opt-in (paid SaaS). Free tier uses "coqui"/"piper".
    elevenlabs_enabled: bool = False
    tts_backend: str = "mock"  # "mock" | "coqui" | "piper" | "elevenlabs"
    tts_output_dir: str = "data/tts"
    tts_auto_fallback: bool = True
    coqui_model_path: str = "tts_models/multilingual/multi-dataset/xtts_v2"
    coqui_speaker_wav: str = ""
    piper_voice_path: str = "/opt/abs/voices/tr-female.onnx"
    meeting_retention_days: int = 90
    meeting_voice_consent_required: bool = True
    # When true, a finished meeting transcript is auto-indexed into the tenant's
    # Qdrant document store (settings.qdrant_default_collection) so it becomes
    # answerable from panel RAG search + MCP rag_query (see mcp_rag_tenant).
    # Best-effort: a RAG/embedder/Qdrant failure never fails the upload.
    meeting_rag_autoindex: bool = True

    # --- Agent mode (chat with tools) -------------------------------------
    # The panel chat can call tools on the operator's behalf. What it may reach
    # is decided here, and every default is the safe end of the choice: reading
    # facts is on, touching the machine is off until someone turns it on
    # deliberately. app/agentic/policy.py holds what each level covers.
    agent_mode_enabled: bool = True
    # Directories the agent may read from. Empty (the default) means the file
    # tools are not registered at all — absent, not "registered and refused".
    agent_fs_roots: List[str] = []
    # Writing files and running commands are separate switches on purpose: a
    # customer who lets the assistant draft into a folder has not thereby agreed
    # to let it run shell.
    agent_fs_write_enabled: bool = False
    agent_shell_enabled: bool = False
    # Where an approved command runs. Defaults to the first file root, so an
    # operator who opened one folder has not thereby handed over their home
    # directory as a working directory.
    agent_shell_cwd: str = ""
    # How many tool calls one question may cost before the agent must answer with
    # what it has — low enough that a confused model cannot spend a minute of
    # provider budget looping.
    agent_max_steps: int = 8

    # SaaS integration env vars (Gmail / Recall / Deepgram / WhisperX / ElevenLabs)
    gmail_oauth_client_id: str = ""
    gmail_oauth_client_secret: str = ""
    gmail_oauth_redirect: str = ""
    recall_backend: str = "mock"  # "mock" | "local" | "recall"
    recall_ai_api_key: str = ""
    recall_ai_cost_cap_usd_per_day: float = 50.0
    # Recall.ai is opt-in (paid SaaS). Free tier uses "local".
    recall_enabled: bool = False
    meeting_local_runner: str = "meetily"  # "meetily" | "jitsi"
    meeting_local_jobs_dir: str = "/tmp/abs-meetings"
    meeting_recordings_dir: str = "/tmp/abs-meetings/recordings"
    transcribe_backend: str = "mock"  # "mock" | "whisperx" | "deepgram" | "groq"
    transcribe_device: str = "cpu"
    deepgram_api_key: str = ""
    deepgram_model: str = "nova-2"
    whisperx_model: str = "small"
    elevenlabs_voice_id: str = ""
    elevenlabs_budget_usd: float = 50.0

    # Env
    env: str = "dev"  # "dev" | "prod"

    # Neo4j graph DB
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "AbsNeo2026!"

    # Multi-tenant Phase 1 — at-rest encryption for per-owner provider keys.
    # If set (urlsafe base64 32-byte or any string → sha256-derived), DB-stored
    # provider keys are Fernet-encrypted. Unset → dev fallback (base64 obfusc.,
    # logged as insecure). Production MUST set ABS_PROVIDER_KEY_ENCRYPTION_KEY.
    provider_key_encryption_key: str = ""

    # Multi-tenant strict isolation. OFF (default) = single-tenant self-host:
    # tenant derives from the operator's session and a few flows
    # accept a client-supplied tenant for backwards-compat. ON = real
    # multi-tenant SaaS (1 instance, N customers): tenant is ALWAYS derived
    # from the authenticated principal, never trusted from request input, and
    # surfaces that cannot be tenant-scoped safely (raw Cypher) are refused.
    # Closes two latent fail-open paths that are harmless on single-tenant but
    # would leak across tenants on shared SaaS:
    #   • marketplace install/uninstall/list — a claim-less admin can no longer
    #     install under an arbitrary `tenant=` body value (forced to its own).
    #   • graph /cypher + /nl-query — raw Cypher can RETURN scalar/aliased
    #     properties with no tenant_id key, slipping past the row filter; strict
    #     mode refuses raw Cypher (the templated graph endpoints stay open).
    #
    # Default ON. It was off, which meant a fresh install shipped with the
    # cross-tenant paths open and an operator had to know to close them — the
    # wrong way round for a setting whose failure mode is one customer reading
    # another's data. A single-tenant deployment loses nothing by it: the
    # claim-less admin resolves to its own canonical tenant, which is the tenant
    # it was asking about anyway.
    multi_tenant_strict: bool = True

    # GraphRAG — knowledge graph over the RAG corpus.
    # When enabled, ingest best-effort extracts entities/relations into Neo4j;
    # the /v1/graph-rag/build endpoint can (re)process the existing corpus.
    graphrag_enabled: bool = False
    # Max chunks processed per build call (LLM cost / 8GB-safe guardrail).
    graphrag_build_max_chunks: int = 500

    model_config = SettingsConfigDict(
        env_prefix="ABS_",
        env_file=".env",
        extra="ignore",
    )


# Production secret-leak guard.
# Listed defaults are intentionally `dev-insecure-*` / `CHANGEME` so the
# unit tests have a non-empty HMAC/JWT key. In production we must refuse
# to boot with any of them still in place.
_DEV_INSECURE_DEFAULTS: dict[str, str] = {
    "unsubscribe_jwt_secret": "dev-insecure-unsubscribe-change-in-prod",
    "admin_token": "dev-insecure-admin-change-in-prod",
    "audit_ip_salt": "dev-insecure-audit-salt-change-in-prod",
    "delete_confirm_jwt_secret": "dev-insecure-delete-jwt-secret",
    "beta_admin_token": "dev-insecure-beta-admin-change-in-prod",
    "admin_jwt_secret": "dev-insecure-admin-jwt-change-in-prod",
    "session_secret": "dev-insecure-change-in-prod",
    "admin_password_bootstrap": "CHANGEME",
    "vault_audit_hmac_secret": "dev-insecure-vault-hmac-change-in-prod",
    # Block production boot if the operator forgot to
    # override the Neo4j placeholder password.
    "neo4j_password": "AbsNeo2026!",
}


def validate_production_secrets(s: "Settings") -> list[str]:
    """Return the list of secret-bearing settings still equal to their dev
    placeholder. Empty list means the deployment is safe."""
    leaked: list[str] = []
    for name, dev_default in _DEV_INSECURE_DEFAULTS.items():
        if getattr(s, name, "") == dev_default:
            leaked.append(name)
    return leaked


def looks_like_production(s: "Settings") -> bool:
    """True when the deployment is publicly reachable, whatever `env` says.

    `env` defaults to "dev", so the secret guard below used to hinge on a
    single environment variable: an operator who deployed to a real domain
    but never set ABS_ENV=prod booted happily and signed session cookies
    with a placeholder secret that ships in the public repo — forgeable by
    anyone. A public hostname served over Let's Encrypt is not something a
    dev or test box has, so we treat it as production regardless of `env`.
    """
    if s.ssl_mode != "acme":
        return False
    domain = (s.domain or "").strip().lower()
    if not domain:
        return False
    # RFC 6761 special-use names never get a public certificate.
    local_suffixes = (".local", ".test", ".example", ".invalid", ".localhost")
    if domain.endswith(local_suffixes) or domain in ("localhost", "127.0.0.1"):
        return False
    return True


# Secrets that key an HMAC or authenticate a caller. The guard above only
# catches an operator who changed *nothing*; it says nothing about one who
# changed the session secret to "hunter2". Every one of these signs or
# authorises something a stranger would like to forge, and SHA-256 HMAC keys
# below 32 bytes weaken the construction (RFC 7518 §3.2 — PyJWT warns on it).
_MIN_SECRET_BYTES = 32

_SIGNING_SECRETS: tuple[str, ...] = (
    "session_secret",
    "admin_jwt_secret",
    "admin_token",
    "beta_admin_token",
    "unsubscribe_jwt_secret",
    "delete_confirm_jwt_secret",
    "vault_audit_hmac_secret",
    "audit_ip_salt",
    "mcp_token_secret",
    "magic_link_hmac_secret",
)


# Signing secrets with no working "off" position: something in the request path
# always needs to HMAC with them. `.env.example` ships them blank, so an operator
# who copies it and fills in only what they recognise leaves these empty — and an
# empty string is not the placeholder, so the guard above waved it through. The
# server then booted and PyJWT raised `InvalidKeyError: HMAC key must not be
# empty` on the first sign-in. A deployment that cannot log anyone in is not a
# deployment; refuse it at the door, where the message can still be read.
_REQUIRED_SECRETS: tuple[str, ...] = (
    "session_secret",
    "admin_jwt_secret",
    "unsubscribe_jwt_secret",
    "delete_confirm_jwt_secret",
    "vault_audit_hmac_secret",
    "audit_ip_salt",
)


def validate_secret_strength(s: "Settings") -> list[str]:
    """Return the signing secrets that are unusable: empty when required, or set
    but too short to be worth signing with.

    A secret that is empty *and* optional (`mcp_token_secret`,
    `magic_link_hmac_secret`, the admin bearers) is not reported — there the
    empty value means the feature is off, which is a legitimate choice."""
    weak: list[str] = []
    for name in _SIGNING_SECRETS:
        value = str(getattr(s, name, "") or "")
        if not value:
            if name in _REQUIRED_SECRETS:
                weak.append(f"{name} (empty — nothing can be signed with it)")
            continue
        if len(value.encode("utf-8")) < _MIN_SECRET_BYTES:
            weak.append(f"{name} ({len(value.encode('utf-8'))} bytes)")
    return weak


def assert_production_safe(s: "Settings") -> None:
    """Fail fast if a production deployment still carries dev-insecure defaults."""
    if s.env != "prod" and not looks_like_production(s):
        return
    leaked = validate_production_secrets(s)
    if leaked:
        bullet = "\n  - ".join(leaked)
        raise RuntimeError(
            "ABS refusing to boot with dev-insecure defaults still in place "
            f"(env={s.env!r}, domain={s.domain!r}, ssl_mode={s.ssl_mode!r}). "
            "Set the following ABS_* environment variables to real production "
            f"values:\n  - {bullet}"
        )
    weak = validate_secret_strength(s)
    if weak:
        bullet = "\n  - ".join(weak)
        raise RuntimeError(
            "ABS refusing to boot: these secrets are set, but too short to sign "
            f"with (minimum {_MIN_SECRET_BYTES} bytes). Generate each one with "
            "`openssl rand -hex 32`:\n  - " + bullet
        )


settings = Settings()
assert_production_safe(settings)
