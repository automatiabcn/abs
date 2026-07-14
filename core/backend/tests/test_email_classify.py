"""Email classifier tests."""

from __future__ import annotations

from app.email_v10.classify import classify_email


def test_urgent_subject_classifies_urgent() -> None:
    c = classify_email(
        subject="URGENT: production down",
        body="API returning 500 errors since 14:00",
    )
    assert c.category == "urgent"
    assert c.confidence > 0.4


def test_billing_keyword_classifies_billing() -> None:
    c = classify_email(
        subject="Invoice attached",
        body="Please find your monthly invoice for Stripe.",
    )
    assert c.category == "billing"


def test_spam_pattern_classifies_spam() -> None:
    c = classify_email(
        subject="You won bitcoin",
        body="Congratulations winner click here to claim",
    )
    assert c.category == "spam"


def test_sales_pattern_classifies_sales() -> None:
    c = classify_email(
        subject="Pricing for ABS",
        body="Could you share a proposal and a demo?",
    )
    assert c.category == "sales"


def test_no_pattern_defaults_to_tech_with_low_confidence() -> None:
    c = classify_email(subject="random thought", body="hello world")
    assert c.category == "tech"
    assert c.confidence < 0.3


def test_turkish_billing_pattern() -> None:
    c = classify_email(
        subject="Fatura sorusu",
        body="Bu ay fatura tutarı yanlış görünüyor.",
    )
    assert c.category == "billing"


def test_priority_picks_highest_score() -> None:
    c = classify_email(
        subject="URGENT billing question",
        body="Need invoice URGENTLY for stripe payment refund.",
    )
    assert c.category in {"urgent", "billing"}
    assert c.priority >= 60
