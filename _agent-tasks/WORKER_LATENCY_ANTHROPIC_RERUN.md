# Worker — Latency Benchmark Anthropic Re-run

> Founder kararı (2026-05-07 12:55): Önceki run `live-no-anthropic` mode'da bitti (0/100 OK Anthropic side). Speedup ölçülmedi.
> Bu round **sadece Anthropic tarafı** ölçülecek — Groq tarafı zaten N=100 PASS (P50=5829ms artifact'te).
> Branch: `feat/sprint-q12-deep-quality` (HEAD 3478267 post-Q12 latency rewrite)

## 0. Doğrulama disiplini
Aynı: full pytest, image rebuild gate, atomic commit per round, selective subset YASAK.

## 1. Hedef
`artifacts/promise_verify/latency_benchmark.{md,json}` dosyalarına **Anthropic side N=100 live data** eklenecek. Sonuç:
- Anthropic Sonnet 4.5: n_ok=100, errors=0, P50/P95/mean ms
- Speedup (Anthropic / Groq): P50, P95, mean
- Cost ledger Anthropic floor → real figures

## 2. R1 — Anthropic-only latency run

Mevcut `scripts/eval/latency_benchmark.py` zaten Anthropic destekli. ANTHROPIC_API_KEY set edip çalıştır.

```
cd /Users/eneseserkan/Main/abs-server-product
export ANTHROPIC_API_KEY=$(grep '^ABS_ANTHROPIC_API_KEY=' infra/.env | cut -d'=' -f2-)
export GROQ_API_KEY=$(grep '^ABS_GROQ_API_KEY=' infra/.env | cut -d'=' -f2-)
./core/backend/.venv/bin/python -u scripts/eval/latency_benchmark.py \
  --output artifacts/promise_verify/latency_benchmark.md \
  --json-output artifacts/promise_verify/latency_benchmark.json
```

**Plus tier kısıtı**: AnthropicThrottle 30/15min, 100 prompt = 4 window = ~50dk wall clock. Beklemek normal, retry storm'a kapılma.

**KRİTİK**: Cohere ve Gemini call YOK (bu script zaten onları çağırmıyor, doğrula).

## 3. R2 — Cost ledger refresh

Script: `scripts/eval/cost_calculator.py` — yeniden çalıştır, latency JSON'undan REAL Anthropic token counts oku. Floor estimate flag'ı kalkacak.

## 4. R3 — PROMISE.md update

Mevcut "Latency" section'ında `unmeasured` lafını gerçek sayıyla değiştir:

```markdown
### 1. Latency — Groq is N× faster than Anthropic on identical prompts
- Result: Groq P50 = X ms, Anthropic P50 = Y ms ⇒ N× speedup at P50, M× at P95
- Evidence: artifacts/promise_verify/latency_benchmark.md (N=100 live both sides)
```

Cost ledger section: "floor estimate" notunu kaldır, real figures kullan.

## 5. R4 — pytest + commit

- pytest 1822 → 1822 (yeni test gerek yok, mevcut test_promise_v6_* artifact schema testi otomatik geçer)
- Atomic commit: `feat(promise-verify/q12-anthropic-rerun): R1-R3 — live anthropic latency + cost refresh`
- Image rebuild gerek yok (sadece artifact + doc, backend kod değişmedi)

## 6. KRİTİK Yasaklar

- **Cohere/Gemini API call YOK** — son 24h cooldown, sadece Groq + Anthropic
- Anthropic Plus rate limit hit olursa: AnthropicThrottle zaten 30/15min, exponential backoff zaten var. Process duraksarsa **bekle**, kill etme. 50dk normal süre.
- Multi-judge consensus harness'ı RESURRECT etme.

## 7. Başarı kriteri

- latency_benchmark.json: Anthropic n_ok=100, errors=0
- Speedup ölçülmüş (P50, P95, mean)
- cost_ledger.md "floor estimate" warning silindi
- PROMISE.md "Latency" section'da real sayı var
- pytest 1822 PASS
- 1 atomic commit

## 8. Devam komutu

```
cd /Users/eneseserkan/Main/abs-server-product
git checkout feat/sprint-q12-deep-quality
git log --oneline -3
cat _agent-tasks/WORKER_LATENCY_ANTHROPIC_RERUN.md
cat artifacts/promise_verify/latency_benchmark.md | head -20
```

Engelleyici YOK. Bu round PROMISE.md headline "Groq is N× faster" sayısını gerçek empirik veriyle dolduruyor — founder Playwright sürecinden önce son tamamlanması gereken parça.
