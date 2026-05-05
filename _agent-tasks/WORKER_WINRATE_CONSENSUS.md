# Worker — Multi-Judge Consensus Eval (Bias-Controlled Win Rate)

> Founder ölçüm (2026-05-06): single-judge bias 58 puan (Llama %80 vs Sonnet %22 same dataset). Smoke 5-prompt 2-judge × position swap → %50 confident win + **%60 position bias**.
> Branch: `feat/sprint-q12-deep-quality` (post Promise-Verify R1-R6, baseline 1806 PASS / 0 / 0)

## 0. Doğrulama disiplini

```
cd core/backend && ./.venv/bin/python -m pytest --no-header -q \
  --ignore=tests/test_providers.py \
  --ignore=tests/test_q03_real_saas_backends.py \
  --ignore=tests/test_update_channel.py
```

Round summary: `pytest_full_suite + image_rebuilt_at + live_path_verified` zorunlu. Selective subset YASAK. Git commit per round.

## 1. Hedef

Mevcut `scripts/eval/winrate_consensus.py` smoke testte sağlam veri verdi (%50 confident, %60 position bias). Full 30 prompt run **rate limit yedi** (Plus tier 50/5h quota, 2 model + 4 judge × 30 prompt = 180 LLM call, sessiz TIE fallback).

PROMISE.md "≥%50 win-rate" iddiası dürüst güncellendi (judge-dependent +/-30 puan). Empirik kanıt için **istatistik gücü olan** eval gerek.

## 2. Yapılacaklar (4 round)

### R1 — Judge pool genişlet (4 judge)

`winrate_consensus.py`'a 4 judge ekle:
- `groq/llama-3.3-70b-versatile` (mevcut)
- `anthropic/claude-sonnet-4-5-20250929` (mevcut)
- `gemini/gemini-2.5-pro` (yeni — Gemini API)
- `cohere/command-r-plus-08-2024` (yeni — Cohere API)

`call_gemini` ve `call_cohere` helper'ları script'e ekle (mevcut kodbase'de `app/providers/gemini/` ve cohere adapter'ı var, oradan örnek al). `judge_one`'a provider="gemini"|"cohere" branchleri.

8 verdict per prompt (4 judge × position swap). Consensus rule: 6/8 majority = confident, 5/8 = weak, ≤4/8 = uncertain.

### R2 — Dataset genişlet (30 → 100 prompt)

`golden_eval_multimodel.json` 30 → 100 prompt:
- code: 25 (mevcut 10 + 15 yeni — algorithms, refactor, debug, perf, security)
- analysis: 25 (mevcut 10 + 15 yeni — comparisons, root-cause, tradeoffs)
- translation: 25 (mevcut 10 + 15 yeni — TR↔EN↔ES, idiom, technical, casual)
- writing: 25 (yeni — TR/EN docs, summary, email)

Her prompt `expected_traits` şart (judge prompt'a yansır). LLM-generated dataset NO — uydurma riski.

### R3 — Rate limit handling

Mevcut script: exception → silent TIE. Bu **yanlış sinyal** verir.

Fix:
- `RateLimitError` exception class — provider 429 → bekle exponential backoff (1s, 2s, 4s, 8s, max 60s, 5 retry)
- Plus tier (Anthropic) için: max 30 call/15dk throttle (50/5h budget'a uygun)
- Silent TIE YOK — error halinde verdict="error", aggregate'te excluded
- Multi-provider rotate: Llama+Sonnet rate limit'te ise Gemini+Cohere'ye fallover (ama judge consistency için sıralı, paralel değil)

### R4 — Statistical reporting

Output:
- **Confident win rate** (6/8+ majority) on N≥100
- **Per-judge breakdown** — her judge'in win rate'i ayrı ayrı (bias ölçümü)
- **Position bias rate** — per judge, swap mismatch %
- **Inter-judge agreement** (Krippendorff's alpha veya pairwise agreement %)
- **Confidence interval** — Wilson 95% CI (binomial)

Markdown artifact `artifacts/promise_verify/winrate_consensus_v2.md` + JSON sidecar.

## 3. PROMISE.md güncelleme kuralı

Confident win rate (6/8+ on N≥100) sonucuna göre:
- `≥55%` → "GPT-OSS-120B beats Sonnet/Opus on most tasks" claim defansiyle yeniden yaz
- `45-55%` → "competitive parity" (mevcut dürüst metin)
- `<45%` → "Anthropic edges out on quality; ABS wins on cost+latency only"

R6'da PROMISE.md edit + commit.

## 4. Round döngüsü

1. R1 = 2 yeni judge ekle (gemini, cohere) + script extend
2. R2 = dataset 30 → 100 prompt (founder onay öncesi review olur)
3. R3 = rate limit + retry + backoff
4. R4 = statistical reporting + plot
5. R5 = full eval run (founder Plus key + Anthropic API key) + artifact ship
6. R6 = PROMISE.md update kurala göre

## 5. Kesin yasaklar

- LLM-generated dataset (uydurma trait riski) YASAK — manual veya gerçek müşteri promptlarından örnekle
- Silent TIE on error YASAK — error explicit reported
- Single judge claim YASAK — confident verdict 6/8+ majority gerek
- "Best free verified" badge YASAK iddia (eski legacy line) — yerine empirik veri

## 6. Delegation %70+ MCP

- Gemini/Cohere call helper kod: ask_gptoss
- Dataset genişletme: ask_qwen32b (TR/EN/ES translation prompts)
- Statistical reporting (Wilson CI, Krippendorff alpha): ask_gptoss
- Patch judge: judge_patch

## 7. Başarı kriteri

- N=100 prompt × 8 verdict run end-to-end
- Confident verdict ≥80% (uncertain <%20)
- Per-judge bias range raporu
- Position bias <%20 per judge
- 95% CI raporu — empirik win rate ±X%
- PROMISE.md kurala göre güncellendi
- pytest 1806 → ≥1810 (4 yeni test: judge_one branches + consensus rule + rate limit handling + dataset schema)

## 8. Founder ölçtüğü baseline (referans)

| Run | Judge | N | Win % | Yorum |
|-----|-------|---|-------|-------|
| Sonnet vs GPT-OSS | Llama | 30 | 80% | judge yanlı + |
| Opus vs GPT-OSS | Llama | 30 | 80% | judge yanlı + |
| Sonnet vs GPT-OSS | Sonnet | 30 | 22% | judge yanlı − |
| Sonnet vs GPT-OSS | Llama+Sonnet (smoke) | 5 | 50% confident | en iyi sinyal |

Yeni eval bunları geçecek istatistiksel güvenle.

## 9. Devam komutu

```
cd /Users/eneseserkan/Main/abs-server-product
git checkout feat/sprint-q12-deep-quality
git log --oneline -5
cat _agent-tasks/WORKER_WINRATE_CONSENSUS.md
ls scripts/eval/
cat artifacts/promise_verify/winrate_consensus.json | python3 -m json.tool | head -40
```

Engelleyici YOK. Bu round PROMISE.md son güncel halini empirik istatistiğe oturtur. Tester paketi gönderilmeden önce vaat dokümanının arkasında durabileceğimiz tek sayı gerekli.
