# VaaniShield

Your voice. Your protection.

A mobile-first Hinglish voice-security demo with two experiences:

- ScamShield: simulated incoming call, microphone capture scaffold, transcript analysis, and visual threat warning.
- Vaani Assistant: separate conversational voice session scaffold.

## Important integration boundary

This repository is an architecture and runnable scaffold, not a claim that live Gnani inference is already connected. Target models: Prisma v3.0, Evon v3.3, Timbre v3.0, and experimental Warp v2.0. Configure each adapter only against the current official Gnani API contract and models enabled for your account. No API paths, payload schemas, voice IDs, or authentication details are guessed.

Gnani is the only intended AI inference provider. Do not add alternate AI/ASR/TTS providers. Warp is not assumed to be a noise suppressor: speech recognition robustness is not audio denoising. Do not claim noise cancellation unless a documented Gnani enhancement operation returns processed audio and measured SNR improvement.

## Structure

- frontend/ — React, TypeScript, Vite mobile UI
- backend/ — FastAPI, session protocol, detection rules, provider adapters
- docs/ — architecture, Gnani integration checklist, WebSocket protocol, implementation plan
- .github/workflows/ — CI

## Quick start

Backend (Python 3.11+):

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Frontend (Node.js 20+):

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Run checks:

```bash
cd backend && pytest
cd frontend && npm run build
```

See docs/GNANI_INTEGRATION.md before configuring provider credentials. Keep all Gnani API keys on the backend. Never commit .env files.

## Demo safety

The call is simulated, not a real telephone call or telecom interception feature. Use fictional scam phrases only. Never collect/store real OTPs, UPI PINs, passwords or CVVs. Raw audio recording is not enabled by default. Weather or other live facts require a genuine live data source; do not fabricate them.

## Current status

The initial commit provides application structure, a local UI and backend protocol scaffold, plus deterministic rules for explicit credential-harvesting requests. Live Prisma/Evon/Timbre integration, Warp capability verification, streaming resampling, persistence, and benchmarked noise handling remain follow-up milestones.
