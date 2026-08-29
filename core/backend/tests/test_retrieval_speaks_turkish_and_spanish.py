# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""A question in Turkish or Spanish finds the English-named file.

Live 2026-08-28: "Kullanıcı modeli hangi alanları tutuyor?" sent two files
and not models.py — the term regex dropped every non-ASCII word, and
nothing mapped "kullanıcı" onto "user". The answer had to ask the
developer to paste the file the server had on disk.
"""

from __future__ import annotations

from pathlib import Path

from app.composer.runtime import _task_terms, relevant_files, workspace_files


def _project(tmp_path: Path) -> Path:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "models.py").write_text(
        "class User(db.Model):\n    email = db.Column(db.String)\n    password_hash = db.Column(db.String)\n"
    )
    (tmp_path / "app" / "routes.py").write_text("@bp.route('/market')\ndef market():\n    return render_template('market.html')\n")
    (tmp_path / "app" / "forms.py").write_text("class ProductForm(FlaskForm):\n    name = StringField()\n")
    (tmp_path / "README.md").write_text("# shop\n")
    return tmp_path


def test_non_ascii_words_survive_and_carry_their_english():
    terms = _task_terms("Kullanıcı modeli hangi alanları tutuyor?")
    assert "kullanıcı" in terms and "user" in terms and "models" in terms and "field" in terms
    terms = _task_terms("¿Qué campos tiene el modelo de usuario?")
    assert "usuario" in terms and "user" in terms and "campos" in terms and "fields" in terms
    # A stem meets its cousins: modeli / models / modelo all reach "mode".
    assert "mode" in _task_terms("modeli")


def test_a_turkish_or_spanish_question_ranks_the_right_file_first(tmp_path: Path):
    root = str(_project(tmp_path))
    for q in ("Kullanıcı modeli hangi alanları tutuyor?", "¿Qué campos tiene el modelo de usuario?", "What fields does the user model have?"):
        picked = relevant_files(root, q, workspace_files(root))
        assert picked and picked[0][0] == "app/models.py", (q, [r for r, _ in picked])
