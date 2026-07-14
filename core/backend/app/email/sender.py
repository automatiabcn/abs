# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Email sender — logs to the console when SMTP is not configured, so a missing
mail server degrades an install rather than breaking it."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import settings

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIR),
    autoescape=select_autoescape(["html"]),
)


def _render(template_name: str, lang: str = "en", **context) -> tuple[str, str]:
    """Render a template → (subject, html).

    Language resolution falls back `<base>_<lang>.html` → `<base>_en.html` →
    `<base>.html`, so a locale with no translation still gets a mail.

    The subject is read from a leading '<!-- subject: ... -->' comment.
    """
    base = template_name[:-5] if template_name.endswith(".html") else template_name
    candidates = [f"{base}_{lang}.html", f"{base}_en.html", f"{base}.html"]
    template = None
    for name in candidates:
        try:
            template = _env.get_template(name)
            break
        except Exception:
            continue
    if template is None:
        # Last fallback: raise the original error so caller gets a clear msg
        template = _env.get_template(candidates[-1])
    html = template.render(**context)

    subject = "Automatia ABS"
    for line in html.splitlines():
        stripped = line.strip()
        if stripped.startswith("<!-- subject:") and stripped.endswith("-->"):
            subject = stripped[len("<!-- subject:") : -3].strip()
            break
    return subject, html


def send_license_email(
    *, to: str, license_key: str, refund_url: str, lang: str = "en"
) -> None:
    """Send the license delivery mail in the customer's language."""
    subject, html = _render(
        "license_delivery.html",
        lang=lang,
        license_key=license_key,
        refund_url=refund_url,
        customer_email=to,
    )

    if not settings.smtp_host:
        # In development, printing the mail to the log is a convenience.
        #
        # In production it is the product going missing. This one email carries
        # the licence key — for a self-hosted customer it *is* what they bought —
        # and a server with no SMTP host was writing it to a log file, returning
        # cleanly, and letting the webhook answer Stripe with a 200. Money in, key
        # nowhere, no error anywhere.
        if str(getattr(settings, "env", "")).lower() in ("prod", "production"):
            raise RuntimeError(
                "no SMTP server is configured (ABS_SMTP_HOST) — the licence key "
                "cannot be delivered"
            )
        logger.info(
            "[email:console-fallback] to=%s subject=%r length=%d",
            to,
            subject,
            len(html),
        )
        return

    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(
        "Your email client does not display HTML. Please use an HTML-capable client."
    )
    msg.add_alternative(html, subtype="html")

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)

    logger.info("[email:sent] to=%s subject=%r", to, subject)


def _send_html(*, to: str, subject: str, html: str, kind: str) -> None:
    """Send HTML mail; a send failure is logged, never raised at the caller."""
    if not settings.smtp_host:
        logger.info(
            "[email:console-fallback] %s to=%s subject=%r length=%d",
            kind,
            to,
            subject,
            len(html),
        )
        return
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(
        "Your email client does not display HTML. Please use an HTML-capable client."
    )
    msg.add_alternative(html, subtype="html")
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
        logger.info("[email:sent] %s to=%s subject=%r", kind, to, subject)
    except Exception as exc:
        logger.exception("[email:fail] %s to=%s err=%s", kind, to, exc)


def send_refund_email(*, to: str, license_jti: str, refund_date: str) -> None:
    """Refund confirmation mail. A render or send failure is logged, not raised."""
    try:
        subject, html = _render(
            "license_refund.html",
            customer_email=to,
            license_jti=license_jti,
            refund_date=refund_date,
        )
    except Exception as exc:
        logger.exception("refund email render fail: %s", exc)
        return
    _send_html(to=to, subject=subject, html=html, kind="refund")


_ROLE_LABELS = {
    "en": {
        "admin": "Administrator",
        "operator": "Operator",
        "viewer": "Viewer",
        "member": "Member",
    },
    # Non-ASCII escaped so the source stays ASCII; the rendered label is unchanged.
    "tr": {
        "admin": "Admin",
        "operator": "Operat\u00f6r",
        "viewer": "Okur",
        "member": "\u00dcye",
    },
    "es": {
        "admin": "Administrador",
        "operator": "Operador",
        "viewer": "Lector",
        "member": "Miembro",
    },
}


def send_invite_email(
    *,
    to: str,
    tenant_name: str,
    role: str,
    magic_url: str,
    invited_by: str,
    lang: str = "en",
) -> None:
    """Admin invite email.

    The inline HTML was extracted to per-locale templates
    (invite_en.html / invite_tr.html / invite_es.html). Default locale
    is English to honour the global-first product stance; ``lang`` can
    be set per-call when the recipient's preference is known.
    """
    role_label = _ROLE_LABELS.get(lang, _ROLE_LABELS["en"]).get(role, role.capitalize())
    try:
        subject, html = _render(
            "invite.html",
            lang=lang,
            tenant_name=tenant_name,
            role=role,
            role_label=role_label,
            magic_url=magic_url,
            invited_by=invited_by,
        )
    except Exception as exc:
        logger.exception("invite email render fail: %s", exc)
        return
    _send_html(to=to, subject=subject, html=html, kind="invite")


def send_account_delete_email(
    *,
    to: str,
    license_jti: str,
    confirm_url: str,
    expires_at: str,
    lang: str = "en",
) -> None:
    """KVKK/GDPR account deletion confirmation email.

    The confirmation token leaves the backend only via this email path.
    It must not appear in any HTTP response body so it cannot be
    captured by access logs or support-ticket clipboards.
    """
    try:
        subject, html = _render(
            "account_delete_confirm.html",
            lang=lang,
            jti=license_jti,
            confirm_url=confirm_url,
            expires_at=expires_at,
        )
    except Exception as exc:
        logger.exception("account_delete email render fail: %s", exc)
        return
    _send_html(to=to, subject=subject, html=html, kind="account_delete")


def send_expiration_email(*, to: str, license_jti: str, expired_at: str) -> None:
    """License expiry mail. A render or send failure is logged, not raised."""
    try:
        subject, html = _render(
            "license_expired.html",
            customer_email=to,
            license_jti=license_jti,
            expired_at=expired_at,
        )
    except Exception as exc:
        logger.exception("expiration email render fail: %s", exc)
        return
    _send_html(to=to, subject=subject, html=html, kind="expiration")
