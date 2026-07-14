# Third-Party Licenses

This document tracks every third-party software dependency bundled with **abs-server-product**. For each component we list the attribution, SPDX license identifier, and upstream URL so that downstream operators can meet the required obligations.

---

## Table of Contents

- [Runtime services](#runtime-services)
- [Python backend deps (existing)](#python-backend-deps-existing)
- [Frontend deps (existing)](#frontend-deps-existing)
- [TTS + ASR model files](#tts--asr-model-files)
- [Obligation summary](#obligation-summary)
- [Adding new dependencies](#adding-new-dependencies)

---

## Runtime services

| Service | SPDX License | Upstream URL | Role in ABS | Obligations |
|---------|--------------|--------------|-------------|-------------|
| **Piper TTS** | MIT | <https://github.com/rhasspy/piper> | Primary text-to-speech engine used by the S20.1 container. | Must retain copyright notice in binary distribution; no source-release requirement. |
| **faster-whisper** | MIT | <https://github.com/SYSTRAN/faster-whisper> | High-performance ASR backbone inside the WhisperX container (S20.2). | Attribution required; source distribution optional. |
| **pyannote.audio** | MIT | <https://github.com/pyannote/pyannote-audio> | Speaker diarization module invoked by WhisperX for multi-speaker streams. | Keep license file with distribution; no further conditions. |
| **openai-whisper-asr-webservice** | MIT | <https://github.com/ahmetoner/whisper-asr-webservice> | Thin HTTP wrapper exposing WhisperX as a REST endpoint (S20.2). | Attribution in documentation; binary can be redistributed unchanged. |
| **onnxruntime** | MIT | <https://github.com/microsoft/onnxruntime> | Runtime for executing ONNX graphs produced by Piper and faster-whisper. | Retain license text; no copyleft effect. |
| **espeak-ng** | GPL-3.0-or-later | <https://github.com/espeak-ng/espeak-ng> | Phonemizer library called by Piper to generate phoneme sequences. | GPL-3.0 requires that any distribution of the Piper container that includes the espeak-ng binary also provide the complete corresponding source code. The obligation is confined to the optional Piper container; the core ABS backend image is not affected. |

*All containers are built from the official upstream Dockerfiles where possible. License files are copied into `/licenses` inside each image for automated compliance scanning.*

---

## Python backend deps (existing)

| Package | SPDX License | Usage |
|---------|--------------|-------|
| **FastAPI** | MIT | HTTP API framework that powers the ABS control plane. |
| **uvicorn** | BSD-3-Clause | ASGI server used to run the FastAPI application. |
| **pydantic** | MIT | Data validation and settings management for request/response models. |
| **SQLModel** | MIT | ORM layer built on top of SQLAlchemy for persisting user and job metadata. |
| **httpx** | BSD-3-Clause | Async HTTP client for internal service-to-service calls (e.g., health checks). |
| **python-jose** | MIT | JSON Web Token creation and verification for authentication. |
| **bcrypt** | Apache-2.0 | Password hashing for local user accounts. |
| **cryptography** | Apache-2.0 OR BSD-3-Clause | TLS handling and symmetric encryption for secret storage. |
| **sops** | MPL-2.0 | Secrets-as-code tool used by the deployment scripts to encrypt configuration files. |
| **age** | BSD-3-Clause | Lightweight encryption utility used by the backup subsystem. |

Each of these libraries is installed via `pip` (pyproject.toml) in the `abs-backend` image and the full license text is retained in `/app/licenses/python`. No downstream redistribution of source code is required beyond the standard MIT/BSD/Apache/MPL notices.

---

## Frontend deps (existing)

| Package | SPDX License | Usage |
|---------|--------------|-------|
| **Next.js** | MIT | Server-side rendering framework for the web UI. |
| **React** | MIT | Component library that drives the interactive dashboard. |
| **Tailwind CSS** | MIT | Utility-first CSS framework for styling the UI. |
| **Framer Motion** | MIT | Animation library used for transitions and visual feedback. |
| **Phosphor Icons** | MIT | Open-source icon set displayed throughout the console. |
| **@playwright/test** | Apache-2.0 | End-to-end test runner executed in CI pipelines. |

All frontend assets are bundled into the landing/panel Next.js build. License files are copied into `/public/licenses` and are served under the `/licenses` endpoint for transparency.

---

## TTS + ASR model files

The runtime containers download model weights on first start from the official Hugging Face model hubs:

* **Piper voices** – `.onnx` acoustic models and associated phoneme tables. Licensed under **CC-BY-4.0** (or MIT for community-contributed voices). Operators must accept the model card before using the voice in production. See the catalog at <https://huggingface.co/rhasspy/piper-voices>.
* **faster-whisper** – Large-scale Whisper checkpoints exported to ONNX. The base Whisper model is released under the **MIT** license; the specific fine-tuned checkpoints may carry an **Apache-2.0** notice depending on the author. Model cards are available at <https://huggingface.co/SYSTRAN/faster-whisper>.

Model files are not redistributed with the ABS images; they are fetched at runtime, which isolates the downstream licensing obligations to the operator's environment. Nevertheless, the ABS installer script prints a reminder to review the model card and record the acceptance in the deployment log.

---

## Obligation summary

The core ABS backend image ships exclusively with dependencies under permissive licenses (MIT, BSD-3-Clause, Apache-2.0, MPL-2.0). These licenses impose only attribution and preservation of copyright notices, which we satisfy by including a `/licenses` directory in every image.

The optional **Piper** container introduces **espeak-ng** under GPL-3.0-or-later. Because GPL-3.0 is a strong copyleft license, any redistribution of that container must also provide the complete source code for espeak-ng (including any modifications) and retain the GPL notice. This obligation does **not** cascade to the core ABS backend image because the GPL-covered binary is isolated in its own container layer. Operators who choose to ship the Piper container as part of a commercial offering must therefore publish the corresponding source archive or provide a written offer to supply it.

We deliberately rejected the Coqui CPML-licensed TTS component (non-commercial clause) and replaced it with Piper to avoid non-permissive restrictions. Consequently, ABS contains no CPML, AGPL, or other non-commercial licenses.

---

## Adding new dependencies

When introducing a new third-party component, follow this checklist:

1. **Identify** the SPDX identifier and the canonical upstream URL (GitHub, PyPI, npm, etc.).
2. **Update** this `THIRD_PARTY_LICENSES.md` file in the same pull request, adding the component to the appropriate section and noting any additional obligations (e.g., source-disclosure, attribution).
3. **Run** the license verification helper: `make license-check` (TODO: implement CI step that fails on missing SPDX or license file).

Compliance is the responsibility of the contributor; failure to update this document will block the PR.

---

_Last updated: 2026-04-29_
