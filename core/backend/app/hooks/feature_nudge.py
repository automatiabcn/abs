"""GUARD 9 — Feature nudge (Bash + MCP idle pattern).

15 Bash pattern + 8 MCP idle nudge. Her feature için 10dk pencere.
SERVER feature_nudge.py'den ürün için adapte: /tmp/abs_*.json yerine
`settings.cache_dir / feature_nudge_rate.json`, davranış birebir.
"""

from __future__ import annotations

from .common import allow_once, load_rate, persist_rate, safe_hook

_RATE_FILE = "feature_nudge_rate.json"
_WINDOW_SEC = 600  # 10 dakika per feature


def _nudge_factory(rate: dict) -> tuple:
    def _allow(key: str) -> bool:
        return allow_once(rate, key, _WINDOW_SEC)

    def _persist() -> None:
        persist_rate(_RATE_FILE, rate)

    return _allow, _persist


# =============================================================================
# Bash nudges (15 pattern)
# =============================================================================

@safe_hook("feature_nudge_bash")
def maybe_feature_nudge_bash(cmd: str) -> str:
    if not cmd or len(cmd) < 10:
        return ""
    if "ask " not in cmd and 'ask "' not in cmd:
        return ""
    cmd_l = cmd.lower()

    rate = load_rate(_RATE_FILE)
    _allow, _persist = _nudge_factory(rate)

    # 1. Kod yazma → qual-code
    if "qual-code" not in cmd_l and "qual " not in cmd_l:
        kw = ("write a function", "write function", "fonksiyon yaz", "kod yaz",
              "implement", "python function", "javascript function",
              "react component", "api endpoint", "write code")
        if any(k in cmd_l for k in kw) and "ask" in cmd_l:
            if _allow("qual-code"):
                _persist()
                return (
                    "FEATURE NUDGE (qual-code): Kod yazma görevinde. "
                    "ask \"...\" qual-code kullanabilirsin — üret(kimi+gpt20b) → "
                    "doğrula(codellama) → düzelt(gptoss). 10dk içinde tekrar gelmez."
                )

    # 2. Karşılaştırma → race
    if "race" not in cmd_l and "mcp__abs__race" not in cmd_l:
        kw = ("compare ", "karsilastir", " vs ", "farkli", "alternatifleri",
              "arastir", "research", "birkac model", "multiple models")
        if any(k in cmd_l for k in kw):
            if _allow("race"):
                _persist()
                return (
                    "FEATURE NUDGE (race): Karşılaştırma/araştırma görevinde. "
                    "ask \"...\" race veya race_code kullanabilirsin — 3 model paralel, "
                    "en iyi sonucu sen seçersin. Şu an tek model çağırıyorsun."
                )

    # 3. Docs → write_docs / fs-doc
    if "write_docs" not in cmd_l and "fs-doc" not in cmd_l:
        kw = ("readme yaz", "documentation", "dokuman yaz", "api doc",
              "rapor yaz", "detailed report", "user guide", "kullanim kilavuzu")
        if any(k in cmd_l for k in kw):
            if _allow("docs"):
                _persist()
                return (
                    "FEATURE NUDGE (docs): Dokümantasyon görevinde. "
                    "mcp__abs__write_docs veya ask \"...\" fs-doc — Qwen3 32B + Aya gramer paralel."
                )

    # 4. Proje scan → fs-scan/plan/exec
    if all(p not in cmd_l for p in ("fs-scan", "fs-plan", "fs-exec")):
        kw = ("proje tara", "eksiklik", "bulgular", "scan project",
              "project analysis", "tamamla proje", "project completion")
        if any(k in cmd_l for k in kw):
            if _allow("fs-scan"):
                _persist()
                return (
                    "FEATURE NUDGE (project completion): Proje tarama görevinde. "
                    "mcp__abs__fullstack_scan veya ask \"/path\" fs-scan — hızlı scan + gap analiz."
                )

    # 5. RAG
    if "rag" not in cmd_l and "mcp__abs__rag" not in cmd_l:
        kw = ("projemde var mi", "projemizde var mi", "daha once yaptik",
              "onceki projede", "daha once nasil", "similar pattern",
              "benzer kod", "benzer pattern")
        if any(k in cmd_l for k in kw):
            if _allow("rag"):
                _persist()
                return (
                    "FEATURE NUDGE (RAG): Geçmiş proje arama görevinde. "
                    "mcp__abs__rag_query — binlerce chunk indexli, benzer kod/pattern bulur."
                )

    # 6. Test/verify → auto_verify
    if "auto_verify" not in cmd_l and "write_tests" not in cmd_l:
        kw = ("test yaz", "unit test", "verify code", "kodu dogrula",
              "kod kontrol", "security check", "guvenlik kontrol")
        if any(k in cmd_l for k in kw):
            if _allow("auto_verify"):
                _persist()
                return (
                    "FEATURE NUDGE (auto_verify): Test/doğrulama görevinde. "
                    "mcp__abs__auto_verify_code veya mcp__abs__write_tests — "
                    "3 PC GPU paralel (codellama + granite + deepseek)."
                )

    # 7. Hızlı pass/fail → granite-fast
    if "granite" not in cmd_l and "verify" not in cmd_l:
        kw = ("evet mi hayir mi", "pass fail", "dogru mu", "correct yes no", "true false check")
        if any(k in cmd_l for k in kw):
            if _allow("granite-fast"):
                _persist()
                return (
                    "FEATURE NUDGE (granite-fast): Mikro doğrulayıcı. "
                    "mcp__abs__ask_granite_fast — hızlı evet/hayır yanıtı (<2s)."
                )

    # 8. Türkçe gramer → aya
    if "aya" not in cmd_l and "qual-tr" not in cmd_l:
        kw = ("turkce gramer", "tr dil", "turkce kalite", "yazim hata", "imla")
        if any(k in cmd_l for k in kw):
            if _allow("aya"):
                _persist()
                return (
                    "FEATURE NUDGE (aya): Türkçe dil kontrolü görevinde. "
                    "mcp__abs__ask_aya veya ask \"...\" qual-tr — Cohere Aya 8B."
                )

    # 9. Görsel analiz → gemini_image
    if "gemini_image" not in cmd_l and "llava" not in cmd_l:
        kw = ("gorsel analiz", "image analysis", "chart read", "mockup", "screenshot anlat")
        if any(k in cmd_l for k in kw):
            if _allow("gemini_image"):
                _persist()
                return (
                    "FEATURE NUDGE (gemini_image): Görsel analiz. "
                    "mcp__abs__gemini_image — multimodal okuma."
                )

    # 10. Yapılandırılmış çıktı → gemini_structured
    if "gemini_structured" not in cmd_l:
        kw = ("json schema", "structured output", "yapilandirilmis", "table extract")
        if any(k in cmd_l for k in kw):
            if _allow("gemini_structured"):
                _persist()
                return (
                    "FEATURE NUDGE (gemini_structured): Yapılandırılmış çıktı. "
                    "mcp__abs__gemini_structured — JSON schema ile garanti tip."
                )

    # 11. Matematik/mantık → phi4
    if "phi4" not in cmd_l:
        kw = ("karmasik matematik", "math proof", "reasoning problem", "logic puzzle", "mantiksal cozum")
        if any(k in cmd_l for k in kw):
            if _allow("phi4"):
                _persist()
                return (
                    "FEATURE NUDGE (phi4): Karmaşık reasoning. "
                    "mcp__abs__ask_phi4 — yerel 14B Phi-4 (Ollama gerekli)."
                )

    # 12. FIM / autocompletion → starcoder
    if "starcoder" not in cmd_l:
        kw = ("fill in the middle", "fim complet", "code completion", "autocomplete")
        if any(k in cmd_l for k in kw):
            if _allow("starcoder"):
                _persist()
                return (
                    "FEATURE NUDGE (starcoder): Kod tamamlama. "
                    "mcp__abs__ask_starcoder — FIM destekli hızlı lint."
                )

    # 13. Uzun context → scout/kimi2
    if "scout" not in cmd_l and "kimi2" not in cmd_l:
        kw = ("128k", "200k", "262k", "long context", "uzun context", "buyuk dosya")
        if any(k in cmd_l for k in kw):
            if _allow("longcontext"):
                _persist()
                return (
                    "FEATURE NUDGE (scout/kimi2): Uzun context görevi. "
                    "ask_scout (128K) veya ask_kimi2 (262K) kullanabilirsin."
                )

    # 14. Hızlı hafif → gptoss20
    if "gptoss20" not in cmd_l and "ask_groq_fast" not in cmd_l:
        kw = ("cok hizli", "ultra fast", "basit gorev", "trivial task")
        if any(k in cmd_l for k in kw):
            if _allow("gptoss20"):
                _persist()
                return (
                    "FEATURE NUDGE (gptoss20/ask_groq_fast): Hafif görev. "
                    "mcp__abs__ask_gptoss20 veya ask_groq_fast — <1s latency."
                )

    # 15. Kritik karar → race critical
    if "race" not in cmd_l:
        kw = ("kritik karar", "production deploy", "mimari karar", "critical decision")
        if any(k in cmd_l for k in kw):
            if _allow("race-critical"):
                _persist()
                return (
                    "FEATURE NUDGE (race critical): Kritik karar görevinde. "
                    "mcp__abs__race veya ask_disagree — 3 model + consensus skoru."
                )

    return ""


# =============================================================================
# MCP idle nudges (8 — tek-model → pipeline önerisi)
# =============================================================================

_MCP_NUDGE_TARGETS = {
    # Tool adı → (rate-key, öneri metni)
    "ask_gptoss": (
        "mcp_qual_code",
        "FEATURE NUDGE: Tek model ile kod yazıyorsun. "
        "mcp__abs__race_code (3 model paralel, en iyisini seç) veya "
        "mcp__abs__qual_code pipeline (üret→doğrula→düzelt) daha kaliteli sonuç verir.",
    ),
    "ask_kimi": (
        "mcp_qual_code",
        "FEATURE NUDGE: Tek model ile kod yazıyorsun. mcp__abs__race_code veya "
        "qual-code pipeline (üret→doğrula→düzelt) daha kaliteli sonuç verir.",
    ),
    "ask_qwen32b": (
        "mcp_qual_tr",
        "FEATURE NUDGE: Tek model ile Türkçe metin yazıyorsun. "
        "qual-tr pipeline (üret→kontrol→polish) veya mcp__abs__race_tr "
        "(qwen32b vs gemini) daha kaliteli sonuç verir.",
    ),
    "ask_gemini": (
        "mcp_qual_tr",
        "FEATURE NUDGE: Tek model kullanıyorsun. qual-tr pipeline veya race_tr daha kaliteli.",
    ),
    "ask_gemini_pro": (
        "mcp_qual_analysis",
        "FEATURE NUDGE: Derin analiz için qual-analysis daha güçlü (3 perspektif + sentez).",
    ),
    "ask_cf": (
        "mcp_fullstack",
        "FEATURE NUDGE: Tek provider yerine mcp__abs__fullstack layer'lı öneri — "
        "katman-özel model seçimi + verification gate'ler.",
    ),
    "ask_cf_gptoss": (
        "mcp_qual_analysis",
        "FEATURE NUDGE: 120B için qual-analysis veya race — tek model body text'i değil yapı öneriyor.",
    ),
    "ask_scout": (
        "mcp_code_review",
        "FEATURE NUDGE: Sınıflandırma/kısa görevde mcp__abs__code_review (auto-tier) veya "
        "mcp__abs__ask_rerank daha isabetli olabilir.",
    ),
}


@safe_hook("feature_nudge_mcp")
def maybe_feature_nudge_mcp(tool_name: str, _tool_input: dict) -> str:
    """MCP tool çağrısında idle feature nudge."""
    if not tool_name:
        return ""
    pair = _MCP_NUDGE_TARGETS.get(tool_name)
    if pair is None:
        return ""
    key, text = pair

    rate = load_rate(_RATE_FILE)
    if not allow_once(rate, key, _WINDOW_SEC):
        return ""
    persist_rate(_RATE_FILE, rate)
    return text
