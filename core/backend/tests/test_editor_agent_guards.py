# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""The editor agent's pure parts: language, cleanup, protocol, prompt.

Each test here is one line of the 2026-09-01 RobotMarket transcript, the
day the chat asked for `app/routes.py` four times, drifted into English,
invented a `cart` route, leaked "We need to request the file list." and
delivered a blank answer. The pieces below are what make each of those
impossible or visible; the tests say which.
"""

from __future__ import annotations

from app.chat import language as lang
from app.chat.cleanup import strip_leaked_reasoning, verify_references
from app.editor_agent import tools as toolbox
from app.editor_agent.context import (
    EditorState,
    StepRecord,
    Todo,
    build_prompt,
    detect_intent,
    render_run,
)
from app.editor_agent.protocol import looks_like_json_start, parse_reply

# --- language ----------------------------------------------------------------


def test_turkish_is_detected_with_and_without_diacritics():
    assert lang.detect("Kullanıcı modeli hangi alanları tutuyor? Kısaca.") == "tr"
    assert lang.detect("evet yaptim kontrol et ve devam edelim") == "tr"
    assert lang.detect("sen siralamayi secebilirsin") == "tr"


def test_english_and_spanish_are_detected_and_code_is_ignored():
    assert lang.detect("Which files define the User model and where is login_view configured?") == "en"
    assert lang.detect("¿Dónde está la función que calcula el total del carrito?") == "es"
    # A bare path or identifier says nothing about the language.
    assert lang.detect("app/routes.py") == ""


def test_an_english_answer_to_a_turkish_developer_is_a_drift():
    """Live: 'Sure! Which page or feature would you like to tackle next?
    (For example: profile edit, login/logout, product detail, etc.)'"""
    answer = (
        "Sure! Which page or feature would you like to tackle next? "
        "(For example: profile edit, login/logout, product detail, etc.) "
        "Let me know and I will continue with the change you want."
    )
    drifted, got = lang.drifted("tr", answer)
    assert drifted and got == "en"


def test_a_turkish_answer_quoting_english_code_is_not_a_drift():
    answer = (
        "`market()` rotasına `q` parametresiyle arama eklemek için `app/routes.py:65` "
        "adresindeki fonksiyonu şu şekilde değiştirebilirsiniz; sorgu boşsa tüm ürünler "
        "listelenir, doluysa `Product.name.ilike` ile filtrelenir.\n"
        "```python\nquery = request.args.get('q', type=str)\n```"
    )
    assert lang.drifted("tr", answer) == (False, "tr")


def test_short_or_codey_answers_never_trip_the_drift_check():
    assert lang.drifted("tr", "app/models.py:12") == (False, "")
    assert lang.drifted("tr", "OK.") == (False, "")


# --- cleanup -----------------------------------------------------------------


def test_the_leaked_reasoning_sentence_is_stripped():
    """Live: the answer began 'We need to request the file list.**Proje…'"""
    raw = "We need to request the file list.**Proje Genel Bakışı**\n\n`RobotMarket` bir Flask..."
    out = strip_leaked_reasoning(raw)
    assert out.startswith("**Proje Genel Bakışı**")
    assert "We need to" not in out


def test_think_blocks_and_harmony_tokens_are_stripped():
    raw = "<think>the user wants the model fields</think>\nUser has id, email."
    assert strip_leaked_reasoning(raw) == "User has id, email."
    raw = (
        "<|channel|>analysis<|message|>Let me look.<|end|>"
        "<|start|>assistant<|channel|>final<|message|>The answer."
    )
    assert strip_leaked_reasoning(raw) == "The answer."


def test_an_answer_that_merely_starts_with_we_need_keeps_its_meaning():
    """Only a lead-in *followed by the answer* is a leak. A sentence that is
    the answer stays, second sentence and all."""
    raw = "We need to add a migration for the new column. Run `flask db migrate` after."
    assert strip_leaked_reasoning(raw) == raw


def test_placeholder_line_numbers_are_removed_and_unknown_paths_marked():
    """Live: 'app/models.py:LINE' and a `cart` route in a project without one."""
    listing = ["app/models.py", "app/routes.py", "app/templates/market.html"]
    text = (
        "User fields are in app/models.py:LINE. The total is computed in "
        "`app/cart.py` and shown by app/routes.py:88."
    )
    fixed, unverified = verify_references(text, listing)
    assert "app/models.py:LINE" not in fixed and "app/models.py" in fixed
    assert unverified == ["app/cart.py"]


def test_nothing_is_marked_without_a_listing_or_inside_code_blocks():
    text = "See `app/ghost.py` and\n```python\nopen('app/other.py')\n```"
    assert verify_references(text, [])[1] == []
    assert verify_references(text, ["app/routes.py"])[1] == ["app/ghost.py"]


# --- protocol ----------------------------------------------------------------


def test_tool_calls_in_every_habitual_shape_are_read():
    for text in (
        '{"tool": "read_file", "args": {"path": "app/routes.py"}}',
        '```json\n{"tool":"read_file","args":{"path":"app/routes.py"}}\n```',
        '{"action":"tool","name":"read_file","args":{"path":"app/routes.py"}}',
        '{"name":"read_file","arguments":{"path":"app/routes.py"}}',
        '{"name":"read_file","arguments":"{\\"path\\": \\"app/routes.py\\"}"}',
        'I will read it first: {"tool":"read_file","args":{"path":"app/routes.py"}}',
    ):
        p = parse_reply(text)
        assert p.kind == "tool", text
        assert p.name == "read_file" and p.args == {"path": "app/routes.py"}, text


def test_prose_is_the_answer_even_when_it_mentions_a_dict():
    p = parse_reply("The config is a dict like {'debug': True}; set it in app/config.py:12.")
    assert p.kind == "final"
    assert "app/config.py:12" in p.text


def test_a_broken_json_start_is_invalid_not_an_answer():
    p = parse_reply('{"tool": "read_file", "args": {"path": ')
    assert p.kind == "invalid"
    assert looks_like_json_start('  {"tool"')
    assert looks_like_json_start("```json\n{")
    assert not looks_like_json_start("The `{}` literal")


def test_a_final_wrapped_in_json_is_unwrapped():
    p = parse_reply('{"action":"final","answer":"Login is in app/routes.py:34."}')
    assert p.kind == "final" and p.text == "Login is in app/routes.py:34."


# --- tools & modes -----------------------------------------------------------


def test_ask_mode_has_no_writing_tools_and_agent_mode_has_all():
    ask = {t["name"] for t in toolbox.catalogue("ask")}
    agent = {t["name"] for t in toolbox.catalogue("agent")}
    assert {"read_file", "grep", "semantic_search", "git_diff", "get_diagnostics"} <= ask
    assert not ({"propose_edit", "create_file", "run_command", "run_tests"} & ask)
    assert {"propose_edit", "create_file", "run_command", "run_tests", "update_plan", "ask_user"} <= agent
    assert not toolbox.allowed("propose_edit", "ask")
    assert toolbox.allowed("propose_edit", "agent")


def test_undeclared_arguments_are_dropped_and_required_ones_insisted_on():
    t = toolbox.get("read_file")
    assert toolbox.validate_args(t, {"path": "a.py", "project": "x"}) == {"path": "a.py"}
    try:
        toolbox.validate_args(t, {"start_line": 1})
    except ValueError as exc:
        assert "path" in str(exc)
    else:
        raise AssertionError("missing required argument accepted")


# --- intent & prompt ---------------------------------------------------------


def test_intents_from_the_transcript():
    assert detect_intent("evet yaptim kontrol et ve devam edelim") == "verify"
    assert detect_intent("degisiklikleri kontrol et lutfen dikkatlice") == "verify"
    assert detect_intent("ilk dosyayi sen yaz lutfen") == "write"
    assert detect_intent("dosyayida sen olusturmalisin icini yazmalisin") == "write"
    assert detect_intent("evet devam edelim projenin kalan isleri ile") == "continue"
    assert detect_intent("Kullanıcı modeli hangi alanları tutuyor?") == "ask"


def test_the_prompt_names_the_language_and_forbids_asking_for_files():
    out = build_prompt(
        message="Kullanıcı modeli hangi alanları tutuyor?",
        mode="agent",
        lang_code="tr",
        intent="ask",
        project_name="RobotMarket",
        rules="",
        rules_from="",
        listing=["app/models.py", "app/routes.py"],
        files=[("app/models.py", "class User:\n    id = 1\n")],
        history="",
        editor=EditorState(active_file="app/routes.py", cursor_line=61, diagnostics=["app/routes.py:70: error: x"]),
        plan=[Todo(id="1", text="market route", status="doing")],
        steps=[],
    )
    assert "Answer in Turkish" in out
    assert "Never ask the developer to paste or share a file" in out
    assert "Open file: app/routes.py (cursor at line 61)" in out
    assert "[~] 1: market route" in out
    assert "1: class User:" in out  # numbered lines
    assert out.rstrip().endswith("the answer in Turkish):")
    assert "- propose_edit(path: string, " in out


def test_ask_mode_prompt_says_it_cannot_change_files_and_hides_write_tools():
    out = build_prompt(
        message="add a route", mode="ask", lang_code="en", intent="write",
        project_name="", rules="", rules_from="", listing=[], files=[], history="",
        editor=None, plan=[], steps=[],
    )
    assert "Mode: Ask" in out
    assert "- propose_edit(" not in out


def test_the_run_keeps_the_latest_results_whole_and_clips_the_oldest():
    steps = [StepRecord(name="read_file", args={"path": f"f{i}.py"}, result="x" * 20_000) for i in range(20)]
    out = render_run(steps)
    assert "[Step 20]" in out and "[Step 19]" in out
    assert "earlier step(s) not shown" in out
    assert len(out) < 40_000
