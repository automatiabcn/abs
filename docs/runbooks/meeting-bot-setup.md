# ABS Meeting Bot — Self-host Setup

> Free-tier alternative to Recall.ai.

## Why

Recall.ai is opt-in (`ABS_RECALL_ENABLED=true`). The default flow is self-hosted via meetily (or jitsi) recording + local WhisperX transcription. Cost: $0/month.

## Architecture

ABS Python writes a job manifest into `meeting_local_jobs_dir` (default `/tmp/abs-meetings`). An external runner (meetily or jitsi side-car) tails this directory, joins the meeting, records audio, drops a `.wav`, and calls back into ABS via `app.meeting.bot_local.transition(bot_id, status="completed", transcript_path=...)`. `Transcriber` (WhisperX local) then parses the audio into a `Transcript` that downstream nodes consume — same interface the workflow node `abs.meeting_transcribe` already uses.

## Prerequisites

- Docker + Docker Compose
- 8 GB GPU recommended (CPU works but slow)
- Linux host (meetily) OR macOS for the jitsi web client
- Calendar: Google Workspace OAuth (free quota — 1M req/day) for cron pickup

## Choosing the runner

| Runner | Best for | Notes |
|--------|----------|-------|
| meetily | Linux servers | Joins Zoom/Meet/Teams via headless Chrome, captures audio |
| jitsi | Self-host meeting room | Run Jitsi Meet on your VPS; ABS supplies a bot account |

Set `ABS_MEETING_LOCAL_RUNNER=meetily` (default) or `=jitsi`.

## Configuration

| Var | Default | Purpose |
|-----|---------|---------|
| `ABS_RECALL_BACKEND` | `mock` (test) / `local` (prod recommended) | Which backend `MeetingBot` uses |
| `ABS_RECALL_ENABLED` | `false` | Must be `true` to use the paid Recall.ai backend |
| `ABS_MEETING_LOCAL_RUNNER` | `meetily` | `meetily` or `jitsi` |
| `ABS_MEETING_LOCAL_JOBS_DIR` | `/tmp/abs-meetings` | Where ABS writes job manifests |
| `ABS_MEETING_RECORDINGS_DIR` | `/tmp/abs-meetings/recordings` | Where uploads + recordings land |
| `ABS_TRANSCRIBE_BACKEND` | `mock` (test) / `whisperx` (prod) | Local transcription engine |
| `ABS_TRANSCRIBE_DEVICE` | `cuda` or `cpu` | WhisperX device |
| `ABS_WHISPERX_MODEL` | `small` | `small` / `medium` / `large-v3` |

## Running meetily

1. Pull `ghcr.io/meetily/recorder:latest`.
2. Mount `${ABS_MEETING_LOCAL_JOBS_DIR}` and `${ABS_MEETING_RECORDINGS_DIR}` as read/write volumes.
3. The recorder polls the jobs dir every 30 s; for each `*.json` with `status=scheduled` it joins the meeting URL.
4. After the meeting ends, the recorder writes `<bot_id>.wav` next to the manifest and PATCHes the manifest with `status=recording_done` + `transcript_path` set to the wav.
5. ABS's transcribe cron picks up `recording_done` jobs, runs WhisperX locally, writes `<bot_id>.transcript.txt`, then transitions the manifest to `status=completed`.

```yaml
services:
  meetily-recorder:
    image: ghcr.io/meetily/recorder:latest
    restart: unless-stopped
    environment:
      ABS_RUNNER: meetily
      ABS_MEETING_LOCAL_JOBS_DIR: /jobs
      ABS_MEETING_RECORDINGS_DIR: /recordings
    volumes:
      - ./abs-meetings:/jobs
      - ./abs-meetings/recordings:/recordings
```

## Manual upload pipeline

For meetings where the recorder isn't available, users can POST audio (`.mp3` / `.mp4` / `.wav` / `.m4a` / `.webm`) to `/v1/meeting/upload`. The handler calls `app.meeting.upload_manual.accept_upload(tenant_id=..., filename=..., payload=...)` which persists the audio, schedules a synthetic local job, runs WhisperX, and returns the `BotJob` + `Transcript`.

## Google Calendar pickup

A cron worker calls `google_calendar_pickup_stub(events)` (or the real Calendar API equivalent) every 5 minutes. For each event with a `hangoutLink`, ABS schedules a local meeting bot job. Tenant ID is taken from the `tenant_id` event property or falls back to the organiser email.

## Quality target — WER < 10 %

- Use `whisperx` model `medium` or larger for Turkish/Spanish (`small` is acceptable for English).
- Provide good audio: ≥ 16 kHz mono PCM.
- Test locally with `app.meeting.upload_manual.wer(reference, hypothesis)` — Levenshtein-based WER.
- Acceptance: WER < 10 % on a 5-minute Turkish reference clip.

## Operations

- Backups: `meeting_recordings_dir` is a regular filesystem path; back it up nightly alongside `qdrant_backup.sh`.
- Retention: `meeting_retention_days` (default 90) — a separate sweeper deletes manifests + audio after N days.
- Tenant boundary: every job manifest includes `tenant_id`; the workflow node `abs.meeting_transcribe` requires the tenant `gdpr_consent: true` flag (Cerbos policy `resource.workflow_node.v1.yaml`).

## Rollback to Recall.ai

If a customer needs Recall.ai (e.g. enterprise SLA): set `ABS_RECALL_ENABLED=true`, `ABS_RECALL_BACKEND=recall`, supply `ABS_RECALL_AI_API_KEY`. The `MeetingBot` interface is identical so no code changes are needed downstream. Cost: ~$0.50 / recording-hour, capped daily by `recall_ai_cost_cap_usd_per_day`.

## Sign-off

> Author: ABS engineering · Date: 2026-04-29.
