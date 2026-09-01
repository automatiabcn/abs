# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""propose_edit and semantic_search against a real folder.

The edit tool is the one place the agent's words become a change on disk
— except that it never touches the disk. These tests pin the contract:
an exact block becomes a diff that dry-runs clean; a block the model got
slightly wrong (indentation, trailing spaces) still lands; a block that is
not there comes back with the closest lines; an ambiguous block is refused;
and a whole-file rewrite that lost most of the file is refused as
truncation, not applied as a deletion.
"""

from __future__ import annotations

import os

import pytest

from app.editor_agent import edits, search

ROUTES = '''from flask import render_template, request

from app import db
from app.models import Product


@main.route("/market")
def market():
    products = Product.query.order_by(Product.created_at.desc()).all()
    return render_template("market.html", title="Market", products=products)


@main.route("/about")
def about():
    return render_template("about.html", title="About")
'''


@pytest.fixture()
def project(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "routes.py").write_text(ROUTES, encoding="utf-8")
    (tmp_path / "app" / "models.py").write_text(
        "class Product:\n    name = ''\n    price = 0\n", encoding="utf-8"
    )
    (tmp_path / "app" / "templates").mkdir()
    (tmp_path / "app" / "templates" / "market.html").write_text(
        "<h1>Market</h1>{% for p in products %}{{ p.name }}{% endfor %}", encoding="utf-8"
    )
    return str(tmp_path)


async def _no_judge(*_a, **_k):
    return {"combined_score": 8.5, "teaching": ["fine"]}


@pytest.fixture(autouse=True)
def quiet_judge(monkeypatch):
    import app.judge.senior as senior

    monkeypatch.setattr(senior, "judge_diff", _no_judge)


@pytest.mark.asyncio
async def test_an_exact_block_becomes_a_diff_that_dry_runs_clean(project):
    out = await edits.propose_edit(
        root=project,
        path="app/routes.py",
        search='    products = Product.query.order_by(Product.created_at.desc()).all()\n',
        replace=(
            '    q = request.args.get("q", "").strip()\n'
            "    query = Product.query\n"
            "    if q:\n"
            '        query = query.filter(Product.name.ilike(f"%{q}%"))\n'
            "    products = query.order_by(Product.created_at.desc()).all()\n"
        ),
        rationale="search by name",
    )
    assert out["ok"], out
    assert out["path"] == "app/routes.py"
    assert out["added"] == 5 and out["removed"] == 1
    assert out["dry_run_ok"] and out["validation"]["valid"]
    assert out["judge_score"] == 8.5
    assert "+    if q:" in out["unified_diff"]
    assert "Edit prepared for app/routes.py (+5/-1, judge 8.5/10)" in out["model_note"]
    # Never written.
    assert "if q:" not in open(os.path.join(project, "app/routes.py"), encoding="utf-8").read()


@pytest.mark.asyncio
async def test_a_block_with_wrong_indentation_still_lands_in_place(project):
    out = await edits.propose_edit(
        root=project,
        path="app/routes.py",
        search='products = Product.query.order_by(Product.created_at.desc()).all()',
        replace="products = Product.query.all()",
    )
    assert out["ok"], out
    assert "+    products = Product.query.all()" in out["unified_diff"]
    # A block whose lines are all dedented is placed at the file's indentation.
    out = await edits.propose_edit(
        root=project,
        path="app/routes.py",
        search='@main.route("/about")\ndef about():\nreturn render_template("about.html", title="About")\n',
        replace='@main.route("/about")\ndef about():\nreturn render_template("about.html", title="Hakkında")\n',
    )
    assert out["ok"], out
    assert out["match"] == "dedented"
    assert '+    return render_template("about.html", title="Hakkında")' in out["unified_diff"]


@pytest.mark.asyncio
async def test_a_block_that_is_not_there_names_the_closest_lines(project):
    out = await edits.propose_edit(
        root=project,
        path="app/routes.py",
        search='    products = Product.query.filter_by(active=True).all()\n',
        replace="x",
    )
    assert not out["ok"] and out["error"] == "search_not_found"
    assert "Closest lines" in out["model_note"]
    assert "Product.query.order_by" in out["model_note"]


@pytest.mark.asyncio
async def test_an_ambiguous_block_is_refused(project):
    out = await edits.propose_edit(
        root=project, path="app/routes.py", search="    return render_template(", replace="x"
    )
    assert not out["ok"] and out["error"] == "ambiguous"
    assert "2 times" in out["model_note"]


@pytest.mark.asyncio
async def test_a_whole_file_rewrite_that_lost_the_file_is_refused(project):
    out = await edits.propose_edit(
        root=project, path="app/routes.py", new_content="def market():\n    pass\n"
    )
    assert not out["ok"] and out["error"] == "looks_truncated"


@pytest.mark.asyncio
async def test_paths_outside_the_project_and_missing_files_are_refused(project):
    out = await edits.propose_edit(root=project, path="../etc/passwd", search="a", replace="b")
    assert out["error"] == "outside_project"
    out = await edits.propose_edit(root=project, path="app/cart.py", search="a", replace="b")
    assert out["error"] == "not_found" and "create_file" in out["model_note"]


@pytest.mark.asyncio
async def test_semantic_search_finds_by_words_and_says_when_nothing_matches(project, monkeypatch):
    import importlib

    rq = importlib.import_module("app.rag.query")

    async def _no_index(*_a, **_k):
        raise RuntimeError("no index")

    monkeypatch.setattr(rq, "query", _no_index)
    out = await search.semantic_search(root=project, query="ürün listeleme rotası hangi template")
    assert out["ok"] and out["hits"]
    paths = [h["path"] for h in out["hits"]]
    assert "app/routes.py" in paths or "app/templates/market.html" in paths
    assert "semantic_search results" in out["model_note"]

    out = await search.semantic_search(root=project, query="sepet toplamı hesaplama")
    # "cart"/"total" appear nowhere: the honest answer is "nothing", never a route.
    assert out["ok"] and out["hits"] == []
    assert "nothing in the project matches" in out["model_note"]
