# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Composer coverage: a template edit that uses a variable no route provides is
warned about; the false-positive guards stay silent, because a wrong "you
forgot the route" erodes trust like a wrong high-risk score."""

from __future__ import annotations

from app.composer.coverage import coverage_warnings


def _make_project(tmp_path):
    ws = tmp_path / "ws"
    (ws / "templates").mkdir(parents=True)
    (ws / "routes.py").write_text(
        "def market():\n"
        "    products = Product.query.all()\n"
        "    return render_template('market.html', products=products)\n",
        encoding="utf-8",
    )
    (ws / "templates" / "market.html").write_text(
        "<h1>Market</h1>\n{% for p in products %}{{ p.name }}{% endfor %}\n",
        encoding="utf-8",
    )
    return ws


TMPL_ADDS_PAGE = (
    "@@ -2,1 +2,4 @@\n"
    " {% for p in products %}{{ p.name }}{% endfor %}\n"
    "+<nav>\n"
    "+{% if page > 1 %}<a href=\"?page={{ page - 1 }}\">Prev</a>{% endif %}\n"
    "+</nav>\n"
)


def test_dangling_template_var_is_warned(tmp_path):
    ws = _make_project(tmp_path)
    warnings = coverage_warnings(
        [("templates/market.html", TMPL_ADDS_PAGE)], str(ws)
    )
    assert len(warnings) == 1
    assert "page" in warnings[0]
    assert "incomplete" in warnings[0]


def test_route_edit_that_provides_the_var_is_silent(tmp_path):
    ws = _make_project(tmp_path)
    route_diff = (
        "@@ -1,3 +1,4 @@\n def market():\n"
        "-    return render_template('market.html', products=products)\n"
        "+    page = request.args.get('page', 1)\n"
        "+    return render_template('market.html', products=products, page=page)\n"
    )
    warnings = coverage_warnings(
        [("templates/market.html", TMPL_ADDS_PAGE), ("routes.py", route_diff)],
        str(ws),
    )
    assert warnings == []


def test_existing_route_already_provides_the_var(tmp_path):
    ws = _make_project(tmp_path)
    # The route on disk already passes `page`; a template that starts using it
    # is complete without a route edit.
    (ws / "routes.py").write_text(
        "def market():\n"
        "    return render_template('market.html', products=products, page=1)\n",
        encoding="utf-8",
    )
    warnings = coverage_warnings(
        [("templates/market.html", TMPL_ADDS_PAGE)], str(ws)
    )
    assert warnings == []


def test_globals_and_loop_locals_are_not_flagged(tmp_path):
    ws = _make_project(tmp_path)
    safe = (
        "@@ -1,1 +1,4 @@\n"
        "+<a href=\"{{ url_for('main.home') }}\">Home</a>\n"
        "+{% for item in products %}{{ item.title }}{% endfor %}\n"
        "+{{ current_user.username }}\n"
    )
    warnings = coverage_warnings([("templates/market.html", safe)], str(ws))
    assert warnings == []


def test_no_template_edit_is_silent(tmp_path):
    ws = _make_project(tmp_path)
    route_diff = "@@ -1,1 +1,1 @@\n-a\n+b\n"
    assert coverage_warnings([("routes.py", route_diff)], str(ws)) == []


def test_attribute_root_must_still_be_provided(tmp_path):
    ws = _make_project(tmp_path)
    # `{{ pagination.pages }}` — `pagination` is the value that must be passed;
    # `.pages` is an attribute, not a separate variable.
    diff = "@@ -1,1 +1,2 @@\n <h1>Market</h1>\n+<span>{{ pagination.pages }}</span>\n"
    warnings = coverage_warnings([("templates/market.html", diff)], str(ws))
    assert len(warnings) == 1
    assert "pagination" in warnings[0]
