# ABS TTS — Self-host Setup (T-F02)

> Free-tier alternative to ElevenLabs. Sprint 20.

## Why

Sprint 20 free-tier refactor: ElevenLabs (~$0.0006 / character) is now opt-in (`ABS_ELEVENLABS_ENABLED=true`). The default flow uses Coqui XTTS-v2 locally, with Piper TTS as the CPU fallback. Cost: $0/month.

## Backends

| Backend | Cost | Best for | Notes |
|---------|------|----------|-------|
| `mock` | $0 | Unit tests | Writes a marker file, no real audio |
| `coqui` | $0 | GPU 8 GB+ | Coqui XTTS-v2, Turkish-natural, speaker-cloning capable |
| `piper` | $0 | CPU only | Piper TTS, faster but less expressive |
| `elevenlabs` | paid | Opt-in | Multilingual v2, MOS 4.5+, requires `ABS_ELEVENLABS_ENABLED=true` |

`tts_auto_fallback` (default `true`) makes the dispatcher swap from `coqui` to `piper` automatically when the Coqui library isn't installed at runtime.

## Configuration

| Var | Default | Purpose |
|-----|---------|---------|
| `ABS_TTS_BACKEND` | `mock` (test) / `coqui` (prod) | Active backend |
| `ABS_TTS_AUTO_FALLBACK` | `true` | Swap to Piper when Coqui is unavailable |
| `ABS_COQUI_MODEL_PATH` | `tts_models/multilingual/multi-dataset/xtts_v2` | XTTS-v2 model id or local path |
| `ABS_COQUI_SPEAKER_WAV` | empty | Optional 30 s reference audio for speaker cloning |
| `ABS_PIPER_VOICE_PATH` | `/opt/abs/voices/tr-female.onnx` | Piper voice model |
| `ABS_TTS_OUTPUT_DIR` | `data/tts` | Where audio files are written |
| `ABS_ELEVENLABS_ENABLED` | `false` | Must be `true` to use the paid backend |
| `ABS_ELEVENLABS_API_KEY` | empty | Required when ElevenLabs is enabled |

## Installing Coqui XTTS-v2

```bash
# GPU host
python -m pip install TTS

# Pre-cache the model (one-off)
python -c "from TTS.api import TTS; TTS('tts_models/multilingual/multi-dataset/xtts_v2')"
```

License: Coqui CPML (research + non-commercial OK; commercial redistribution requires Coqui's terms — review before bundling in your release).

## Installing Piper

```bash
python -m pip install piper-tts
mkdir -p /opt/abs/voices
# Turkish female: pull a high-quality voice from rhasspy/piper-voices
curl -L -o /opt/abs/voices/tr-female.onnx \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/tr/tr_TR-dfki-medium.onnx
curl -L -o /opt/abs/voices/tr-female.onnx.json \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/tr/tr_TR-dfki-medium.onnx.json
```

## Voice cloning (Coqui only)

1. Record a 30 s clean WAV of the speaker (mono, 22.05 kHz, headset mic).
2. Save to `/opt/abs/voices/<speaker>.wav`.
3. Set `ABS_COQUI_SPEAKER_WAV=/opt/abs/voices/<speaker>.wav`.
4. The next `synthesize(...)` call uses that voice.

Cloning is opt-in per tenant; a future sprint will gate it behind a `voice_consent` policy on the workflow node.

## Quality target — Turkish MOS 4.0+

- XTTS-v2 with a clean 30 s reference reliably scores MOS 4.0–4.4 on Turkish prompts.
- Piper `tr_TR-dfki-medium` scores ~3.8–4.0; acceptable for reminder-style notifications.
- Real MOS measurement is operator-side; for CI we just check audio file present + non-zero size.

## Operations

- The Coqui model (~2.7 GB) lives in the Hugging Face cache; mount that into the container or pre-bake it.
- ElevenLabs budget cap (`elevenlabs_budget_usd`) is enforced only when the opt-in backend is selected; free backends are unbounded.
- A long synthesis (>30 s of audio) emits a warning log line so you can tune the input text.

## Rollback to ElevenLabs

```bash
export ABS_ELEVENLABS_ENABLED=true
export ABS_ELEVENLABS_API_KEY=...
export ABS_TTS_BACKEND=elevenlabs
```

The `TTSReminder` interface is identical so no callers need to change.

## Sign-off

> Author: ABS engineering · Date: 2026-04-29 · Sprint 20 T-F02.
