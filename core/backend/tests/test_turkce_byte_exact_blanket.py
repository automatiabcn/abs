"""Two guards on the words a customer actually reads.

1. The setup wizard ships a real translation dictionary (EN canonical, TR and
   ES applied client-side). A translation that loses its accents — "Ileri" for
   "İleri" — is not a translation, it is a bug that ships silently because
   nothing in a byte-blind test notices. So the Turkish is asserted at the byte
   level, and its ASCII-flattened forms are forbidden outright.

2. Chat's fallback errors are the opposite case. They are the product speaking
   for itself when nothing else could answer, they are not part of the
   dictionary, and the product speaks English. Turkish there is a leak from
   when this was an internal tool, and it reaches the customer in the chat
   bubble — so it is banned rather than pinned.
"""
from __future__ import annotations

import pathlib
import re

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
SETUP_DIR = BACKEND_ROOT / "app" / "static" / "setup"
# The wizard's Turkish lives in setup.js's i18n dictionary; index.html is
# EN-canonical and translated via data-i18n. So the byte gate looks at setup.js.
SETUP_JS = SETUP_DIR / "assets" / "setup.js"
CHAT_PY = BACKEND_ROOT / "app" / "api" / "chat.py"


# Bytes are derived from the string via .encode("utf-8") in the test, so the
# list can't drift from the real UTF-8 encoding. Every entry is a Turkish
# string that actually appears in setup.js's TR i18n dictionary.
REQUIRED_SETUP_TR = [
    "İleri",
    "Geri",
    "Şifre",
    "Yönetici Hesabı",
    "Lisans Anahtarı",
    "yapıştırın",
    "Ücretsiz",
    "Sağlayıcılar",
    "Bağlantı Testi",
    "Kurulumu Bitir",
    "geliştirme",
]

# ASCII düşmüş Türkçe (mojibake / flatten) — setup.js'te kesinlikle BULUNMAMALI.
FORBIDDEN_SETUP_ASCII = [
    "Ileri",
    "Sifre",
    "Yonetici Hesabi",
    "Lisans Anahtari",
    "yapistirin",
    "Ucretsiz",
    "Saglayicilar",
    "Baglanti Testi",
    "gelistirme",
]


def test_setup_js_has_correct_turkish_bytes() -> None:
    raw = SETUP_JS.read_bytes()
    missing = [w for w in REQUIRED_SETUP_TR if w.encode("utf-8") not in raw]
    assert not missing, (
        f"setup.js eksik Türkçe byte sequences: {missing}"
    )


def test_setup_js_no_ascii_fallen_turkish() -> None:
    raw = SETUP_JS.read_bytes()
    leaks = [w for w in FORBIDDEN_SETUP_ASCII if w.encode("utf-8") in raw]
    assert not leaks, (
        f"setup.js hâlâ ASCII düşmüş Türkçe içeriyor: {leaks}"
    )


# The strings chat streams into the bubble when no provider could answer. They
# are what a paying customer reads on the worst day they will have with this
# product, so each one has to name the problem and the way out of it.
CHAT_FALLBACKS = [
    "No provider is set up yet",
    "Only paid providers are configured",
    "Every provider failed on this question",
    "The answer did not come through",
]

TURKISH_LETTERS = "şğıçöüŞĞİÇÖÜ"


def _user_facing_strings(source: str) -> list[str]:
    """Every quoted string on a line that streams text to the client.

    Comments and docstrings are not the customer's problem; `err_text = "…"`
    and the `"content": …` frames are.
    """
    out: list[str] = []
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        out.extend(re.findall(r'"([^"]{12,})"', line))
    return out


def test_chat_fallbacks_tell_the_customer_what_to_do() -> None:
    source = CHAT_PY.read_text(encoding="utf-8")
    missing = [s for s in CHAT_FALLBACKS if s not in source]
    assert not missing, (
        "chat.py no longer says these to the customer when a question cannot "
        f"be answered: {missing}"
    )


def test_chat_never_answers_the_customer_in_turkish() -> None:
    # This product is sold in English. Turkish in a chat bubble is a leak from
    # when it was an internal tool — and the customer, not the author, is the
    # one who finds it.
    source = CHAT_PY.read_text(encoding="utf-8")
    leaks = [
        s
        for s in _user_facing_strings(source)
        if any(ch in s for ch in TURKISH_LETTERS)
    ]
    assert not leaks, f"chat.py speaks Turkish to the customer: {leaks}"
