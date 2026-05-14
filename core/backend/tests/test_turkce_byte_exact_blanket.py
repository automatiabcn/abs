"""Sprint 2N FAZ A5 — Lesson 11 Türkçe byte-exact CI gate.

Setup wizard HTML + cascade fallback metinleri UTF-8 byte sequence düzeyinde
doğrulanır. ASCII düşmüş Türkçe (Ileri, Tum, lutfen, sagla...) BLOCK edilir.

Sprint 2M bug log: #2M-003 (setup HTML) + #2M-017 (cascade fallback)
"""
from __future__ import annotations

import pathlib

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
SETUP_HTML = BACKEND_ROOT / "app" / "static" / "setup" / "index.html"
CHAT_PY = BACKEND_ROOT / "app" / "api" / "chat.py"


REQUIRED_HTML_BYTES = {
    "İleri": b"\xc4\xb0leri",
    "Adımlar": b"Ad\xc4\xb1mlar",
    "Yönetici": b"Y\xc3\xb6netici",
    "Hesabı": b"Hesab\xc4\xb1",
    "girişini": b"giri\xc5\x9fini",
    "Şifre": b"\xc5\x9eifre",
    "Lisans Anahtarı": b"Lisans Anahtar\xc4\xb1",
    "aldığınız": b"ald\xc4\xb1\xc4\x9f\xc4\xb1n\xc4\xb1z",
    "yapıştırın": b"yap\xc4\xb1\xc5\x9ft\xc4\xb1r\xc4\xb1n",
    "gün": b"g\xc3\xbcn",
    "geliştirme": b"geli\xc5\x9ftirme",
    "erişimi için": b"eri\xc5\x9fimi i\xc3\xa7in",
    "formatı": b"format\xc4\xb1",
    "kullanacaksanız": b"kullanacaksan\xc4\xb1z",
    "Ücretsiz": b"\xc3\x9ccretsiz",
    "anahtarım": b"anahtar\xc4\xb1m",
    "sağlayıcılar": b"sa\xc4\x9flay\xc4\xb1c\xc4\xb1lar",
    "Anahtarları": b"Anahtarlar\xc4\xb1",
    "Yapılandırılmış": b"Yap\xc4\xb1land\xc4\xb1r\xc4\xb1lm\xc4\xb1\xc5\x9f",
    "hızlı": b"h\xc4\xb1zl\xc4\xb1",
    "atılır": b"at\xc4\xb1l\xc4\xb1r",
    "Kurulumu Bitir": b"Kurulumu Bitir",
}

# ASCII düşmüş kelimeler — kesinlikle BULUNMAMALI
FORBIDDEN_ASCII = [
    b">Ileri<",
    b"Kuruluma Bitir",
    b"Yonetici Hesabi",
    b"Sifre <input",
    b"aria-label=\"Adimlar\"",
    b"Lisans Anahtari</h2>",
    b"aldiginiz JWT",
    b"yapistirin",
    b"14 gun aktif",
    b"IP (gelistirme)",
    b"erisimi icin",
    b"sk-ant-...) formati",
    b"abonelik kullanacaksaniz",
    b"Ucretsiz tier",
    b"Anthropic API anahtarim yok",
    b"free saglayicilar)",
    b"Provider Anahtarlari</h2>",
    b"Yapilandirilmis provider",
    b"hizli ping atilir",
]


def test_setup_html_has_correct_turkish_bytes() -> None:
    raw = SETUP_HTML.read_bytes()
    missing = [w for w, b in REQUIRED_HTML_BYTES.items() if b not in raw]
    assert not missing, (
        f"Setup HTML eksik Türkçe byte sequences: {missing}"
    )


def test_setup_html_no_ascii_fallen_turkish() -> None:
    raw = SETUP_HTML.read_bytes()
    leaks = [token.decode() for token in FORBIDDEN_ASCII if token in raw]
    assert not leaks, (
        f"Setup HTML hâlâ ASCII düşmüş Türkçe içeriyor: {leaks}"
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
