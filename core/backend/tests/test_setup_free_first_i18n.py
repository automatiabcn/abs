# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Roadmap (d) — setup wizard free-first framing + EN-default i18n.

Locks two product requirements at the static-asset contract level:

  free-first: the "use only free providers" path is the zero-click default.
  The skip checkbox ships `checked` and the hidden skip_paid_providers field
  defaults to "true", so an operator with no Anthropic key completes the
  Premium step by just clicking Next (Anthropic is opt-in, not mandatory).

  i18n: the served HTML is English by default (<html lang="en">) and carries
  data-i18n hooks; setup.js bundles the TR + ES dictionaries and a language
  switcher that persists via /v1/setup/lang.
"""

from __future__ import annotations


def test_index_is_english_default_with_i18n_hooks(client):
    body = client.get("/setup").text
    assert '<html lang="en">' in body
    assert "data-i18n=" in body
    # language switcher present for the three supported locales
    assert 'data-lang="en"' in body
    assert 'data-lang="tr"' in body
    assert 'data-lang="es"' in body


def test_premium_step_defaults_to_free_first(client):
    body = client.get("/setup").text
    # skip checkbox checked by default → free path is zero-click
    assert 'id="setup-skip-paid"' in body
    skip_idx = body.index('id="setup-skip-paid"')
    # the same <input> tag carries the `checked` attribute
    input_tag = body[body.rindex("<input", 0, skip_idx) : body.index(">", skip_idx)]
    assert "checked" in input_tag
    # hidden flag defaults to true (free tier)
    assert 'name="skip_paid_providers" value="true"' in body
    # the Anthropic key field is NOT hard-required in markup (opt-in only)
    key_idx = body.index('id="setup-anthropic-key"')
    key_tag = body[body.rindex("<input", 0, key_idx) : body.index(">", key_idx)]
    assert "required" not in key_tag


def test_setup_js_bundles_tr_and_es_dictionaries(client):
    js = client.get("/setup/assets/setup.js").text
    assert "applyI18n" in js
    assert "persistLang" in js
    # TR + ES sample strings present
    assert "Kaosu Otomatikleştir" in js  # tagline TR
    assert "Comenzar gratis" in js or "proveedores gratuitos" in js  # ES
    # free-first toggle logic present
    assert "initSkipToggle" in js
