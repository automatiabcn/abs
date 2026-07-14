"""Setup UI static file service tests."""

from __future__ import annotations


def test_setup_index_serves_html(client):
    r = client.get("/setup")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    body = r.text
    assert 'data-step="1"' in body
    # Customer-facing wizard carries only the "ABS" product name — the
    # "Automatia" vendor name must never leak into the shipped install flow.
    assert "<h1>ABS</h1>" in body
    assert "Automatia" not in body
    assert 'data-step-key="admin"' in body
    assert 'data-step-key="test"' in body
    # The mark is the product's own (AbsLogo), drawn inline. The rounded gradient
    # PNG and the stock photograph behind the rail are gone from the image, so a
    # reference left behind here would be a 404 on the customer's first screen.
    assert "abs-logo.png" not in body
    assert "setup-rail.jpg" not in body
    assert "<svg" in body


def test_setup_assets_served(client):
    r_js = client.get("/setup/assets/setup.js")
    assert r_js.status_code == 200
    assert "javascript" in r_js.headers["content-type"]
    assert "loadState" in r_js.text

    r_css = client.get("/setup/assets/setup.css")
    assert r_css.status_code == 200
    assert "css" in r_css.headers["content-type"]
    css = r_css.text
    # The wizard is the FIRST screen a customer sees, so it is the one deciding
    # what the product looks like — and it was the last screen still wearing the
    # previous identity (indigo gradient, near-black ground) while the panel and
    # the site had moved to the teal instrument theme.
    #
    # The brand token is asserted against the value the panel ships in
    # core/landing/app/tokens.css. The wizard cannot import that file (it is
    # served by the backend, outside the Next bundle), so the values are copied —
    # and a copy that nothing checks is a copy that drifts.
    assert "--abs-brand-rgb: 11 124 116" in css
    assert "prefers-color-scheme: dark" in css  # the wizard had no dark theme at all
    assert "#4f46e5" not in css and "#818cf8" not in css  # the old indigo is gone


def test_test_step_renders_readable_results_not_raw_json(client):
    """Step 6 ping results are rendered as a readable per-provider list
    (renderTestResults) instead of dumping raw JSON into the box."""
    js = client.get("/setup/assets/setup.js").text
    assert "renderTestResults" in js
    assert "PROVIDER_LABELS" in js
    # the old raw dump is gone
    assert "JSON.stringify(data.test_results" not in js
