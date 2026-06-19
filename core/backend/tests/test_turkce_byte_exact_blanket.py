"""Sprint 2N FAZ A5 — Lesson 11 Türkçe byte-exact CI gate.

Setup wizard HTML + cascade fallback metinleri UTF-8 byte sequence düzeyinde
doğrulanır. ASCII düşmüş Türkçe (Ileri, Tum, lutfen, sagla...) BLOCK edilir.

Sprint 2M bug log: #2M-003 (setup HTML) + #2M-017 (cascade fallback)
"""
from __future__ import annotations

import pathlib

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
SETUP_DIR = BACKEND_ROOT / "app" / "static" / "setup"
# Wizard Türkçesi i18n sözlüğünde (setup.js) yaşıyor: index.html artık EN-default
# (data-i18n ile çevriliyor). Byte-exact gate Türkçeyi setup.js'te doğrular.
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


CASCADE_REQUIRED_BYTES = {
    "Henüz sağlayıcı yapılandırılmadı": (
        b"Hen\xc3\xbcz sa\xc4\x9flay\xc4\xb1c\xc4\xb1 yap\xc4\xb1land\xc4\xb1r\xc4\xb1lmad\xc4\xb1"
    ),
    "Ücretsiz sağlayıcı yapılandırılmadı": (
        b"\xc3\x9ccretsiz sa\xc4\x9flay\xc4\xb1c\xc4\xb1 yap\xc4\xb1land\xc4\xb1r\xc4\xb1lmad\xc4\xb1"
    ),
    "Tüm sağlayıcılar geçici hata verdi": (
        b"T\xc3\xbcm sa\xc4\x9flay\xc4\xb1c\xc4\xb1lar ge\xc3\xa7ici hata verdi"
    ),
    "lütfen tekrar deneyin": b"l\xc3\xbctfen tekrar deneyin",
    "Cascade canlı uçları henüz aktif değil": (
        b"Cascade canl\xc4\xb1 u\xc3\xa7lar\xc4\xb1 hen\xc3\xbcz aktif de\xc4\x9fil"
    ),
}

CASCADE_FORBIDDEN_ASCII = [
    b"Henuz saglayici yapilandirilmadi",
    b"Ucretsiz saglayici yapilandirilmadi",
    b"Tum saglayicilar gecici hata verdi",
    b"lutfen tekrar deneyin",
    b"Cascade canli uclari henuz aktif degil",
]


def test_chat_cascade_fallback_byte_exact() -> None:
    raw = CHAT_PY.read_bytes()
    missing = [w for w, b in CASCADE_REQUIRED_BYTES.items() if b not in raw]
    assert not missing, (
        f"chat.py cascade fallback eksik Türkçe byte: {missing}"
    )


def test_chat_cascade_no_ascii_fallen_turkish() -> None:
    raw = CHAT_PY.read_bytes()
    leaks = [t.decode() for t in CASCADE_FORBIDDEN_ASCII if t in raw]
    assert not leaks, (
        f"chat.py cascade hâlâ ASCII Türkçe içeriyor: {leaks}"
    )
