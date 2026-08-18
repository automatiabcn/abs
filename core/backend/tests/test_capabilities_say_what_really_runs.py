"""A capability is 'available' only if it would actually run here.

Audit 2026-08-18: the judge showed available with any chat provider while it
only runs on groq/cerebras (a gemini-only install: judge on, every score
None); 'checks' was always on regardless of the OS sandbox; cohere was left
out of the chat count although it answers chat in the cascade.
"""

from __future__ import annotations

from app.capabilities import assess


def _state(states, key):
    return next(s for s in states if s.capability.key == key)


def test_a_gemini_only_install_has_no_judge_and_is_told_where_to_get_one():
    st = _state(assess(["gemini"]), "judge")
    assert st.available is False
    assert "groq" in st.unlock_with and "cerebras" in st.unlock_with
    assert st.unlock_is_free is True
    assert "gpt-oss-120b" in st.blocked_by


def test_a_groq_install_has_the_judge():
    assert _state(assess(["groq"]), "judge").available is True


def test_a_resting_judge_provider_is_wait_not_buy():
    st = _state(assess(["groq"], unusable_now={"groq": "hit its per-minute limit"}), "judge")
    assert st.available is False
    assert "Not right now" in st.blocked_by
    assert st.unlock_with == []


def test_checks_follow_the_os_sandbox():
    assert _state(assess(["groq"], sandbox_available=True), "checks").available is True
    off = _state(assess(["groq"], sandbox_available=False), "checks")
    assert off.available is False and "sandbox" in off.blocked_by
    # unknown is not "no"
    assert _state(assess(["groq"], sandbox_available=None), "checks").available is True


def test_cohere_counts_as_a_chat_provider_for_failover():
    assert _state(assess(["groq", "cohere"]), "failover").available is True
    assert _state(assess(["groq"]), "failover").available is False
