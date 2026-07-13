"""The product speaks English everywhere it is not deliberately translated.

This repo is public and the product is sold in English. Turkish reached the
customer in three ways before this guard existed, and each one is a case here:

* chat's error text, the agents' system prompt, API error details — English now;
* comments and docstrings, which anyone reading the repo reads too;
* strings with the accents flattened out — ``yapilandirilmadi`` for
  ``yapılandırılmadı``. A character-class grep never sees those, which is
  exactly why they survived every earlier sweep. The word list below is the
  antidote: it matches the Turkish that hides in ASCII.

What is deliberately excluded is as important as what is checked. The setup
wizard's dictionary, the ``_tr`` email templates, the ``title_tr`` workflow
titles and the i18n locale files are *translations sitting beside English
originals* — the product ships in three languages on purpose. Turkish there is
the feature. Turkish anywhere else is the leak.
"""

from __future__ import annotations

import pathlib
import re

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = BACKEND_ROOT / "app"

TURKISH_LETTERS = "şğıçöüŞĞİÇÖÜ"

# Turkish that survives having its accents stripped. Each of these actually
# leaked into shipped code — an API `detail=`, a marketplace listing, a
# module docstring — and no accent-based check would have caught any of them.
ASCII_TURKISH = re.compile(
    r"\b("
    r"yapilandir\w*|tanimli|degil|icin|cagr\w*|doner|bulunamadi|gerekli"
    r"|kullanici\w*|mesaji|yuklu|olustur\w*|guncelle\w*|baglanti|bekleniyor"
    r"|lisans|aktarir|baglar|senkronize|yansitir|sorgulama|hata"
    r")\b",
    re.IGNORECASE,
)

# Where Turkish is the product, not a leak.
TRANSLATION_SURFACES = (
    "i18n/locales",  # the locale catalogues themselves
    "email/templates",  # welcome_tr.html sits beside welcome_en.html
    "static/setup",  # the wizard's EN/TR/ES dictionary
    "workflow_v10/builder/templates.py",  # title_tr beside title
)

# Files that match on Turkish input on purpose: a Turkish question has to route
# to the Turkish pipeline, and a CSV column called "şirket" has to be read.
# These keep their Turkish as \u escapes, so they are ASCII on disk and this
# guard's word list is what would otherwise flag them.
INPUT_MATCHERS = (
    "chat/pipeline_router.py",
    "email_v10/classify.py",
    "graph_context/service.py",
    "graph_rag/extract.py",
    "meeting/action_items.py",
    "erp/two_step_sql.py",
    "erp/hybrid_router.py",
    "erp/vanna_app.py",
    "connectors/adapters/csv_import.py",
    "connectors/registry.py",  # "Paraşüt" is a vendor's name
    "hooks/enrichment.py",
    "hooks/delegate_nudge.py",
    "mcp/tools/fullstack.py",
    "pipelines/humanize/scorer.py",
    "pipelines/qual/translate.py",
    "services/tts.py",  # a Turkish voice is a Turkish voice
)


def _shipped_python() -> list[pathlib.Path]:
    out: list[pathlib.Path] = []
    for path in APP.rglob("*.py"):
        rel = path.relative_to(BACKEND_ROOT).as_posix()
        if any(s in rel for s in TRANSLATION_SURFACES):
            continue
        if any(rel.endswith(m) for m in INPUT_MATCHERS):
            continue
        out.append(path)
    return sorted(out)


def _offenders(pattern: re.Pattern[str]) -> list[str]:
    hits: list[str] = []
    for path in _shipped_python():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for n, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                rel = path.relative_to(BACKEND_ROOT).as_posix()
                hits.append(f"{rel}:{n}: {line.strip()[:100]}")
    return hits


def test_no_turkish_in_shipped_code() -> None:
    hits = _offenders(re.compile(f"[{TURKISH_LETTERS}]"))
    assert not hits, (
        "Turkish in shipped code — the customer reads this, and so does anyone "
        "who opens the repo:\n" + "\n".join(hits[:25])
    )


def test_no_accent_stripped_turkish_in_shipped_code() -> None:
    # The sneaky half. "Vault yapilandirilmadi" was an HTTP 503 detail a
    # customer could hit, and it passed every accent-based check ever run
    # against this repo.
    hits = _offenders(ASCII_TURKISH)
    assert not hits, (
        "Turkish with the accents stripped out — invisible to a character-class "
        "grep, still Turkish to the reader:\n" + "\n".join(hits[:25])
    )
