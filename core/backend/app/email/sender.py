"""Email gönderici — SMTP yapılandırılmamışsa console log fallback."""

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
    """Template'i render eder, (subject, html) döner.

    023 — lang parametresi: önce `<base>_<lang>.html`, yoksa `<base>_en.html`,
    yoksa orijinal `<base>.html` dosyasına fallback.

    Template'in ilk satırlarında '<!-- subject: ... -->' aranır.
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
            subject = stripped[len("<!-- subject:"):-3].strip()
            break
    return subject, html


def send_license_email(
    *, to: str, license_key: str, refund_url: str, lang: str = "en"
) -> None:
    """023 — Lisans email'ini lang-aware gönder. SMTP_HOST boşsa console fallback."""
    subject, html = _render(
        "license_delivery.html",
        lang=lang,
        license_key=license_key,
        refund_url=refund_url,
        customer_email=to,
    )

    if not settings.smtp_host:
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
    msg.set_content("Your email client does not display HTML. Please use an HTML-capable client.")
    msg.add_alternative(html, subtype="html")

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)

    logger.info("[email:sent] to=%s subject=%r", to, subject)


def _send_html(*, to: str, subject: str, html: str, kind: str) -> None:
    """SMTP veya console fallback (012)."""
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
        "Email istemciniz HTML göremedi. Lütfen HTML destekli bir istemci kullanın."
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
    """012 — İade onay maili. SMTP yoksa console fallback (exception fırlatmaz)."""
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


def send_expiration_email(*, to: str, license_jti: str, expired_at: str) -> None:
    """012 — Lisans süresi doldu maili. SMTP yoksa console fallback."""
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
