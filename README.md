# VaaniShield

**Real-time AI voice scam detection for safer conversations.**

VaaniShield is a browser-based, Hinglish-first voice safety application. It combines speech recognition, deterministic scam-pattern detection, contextual reasoning, and spoken responses to help users recognize suspicious requests during a conversation.

> **Product boundary:** ScamShield currently provides a simulated incoming-call experience in the browser. It does not intercept cellular calls, monitor a phone dialer, or provide operating-system-level call screening.

## Solution pitch

Voice scams use urgency, impersonation, and social engineering to persuade people to disclose OTPs, UPI PINs, banking credentials, or other sensitive information. Traditional spam filters may not recognize these tactics once a conversation is already in progress.

**VaaniShield is an AI-powered voice safety assistant that analyses spoken conversations and surfaces timely warnings when it detects suspicious behaviour.** The browser captures microphone audio and streams it to the application backend. Gnani Prisma converts speech to text; deterministic rules immediately identify explicit credential-theft and remote-access patterns; contextual reasoning can assess less obvious turns; and Gnani Timbre can speak warnings or assistant responses back to the user.

The product has two experiences: **ScamShield**, a simulated caller flow for scam-awareness demonstrations, and **Vaani Assistant**, a separate voice conversation with an AI assistant. The system is designed for cloud inference: the user's PC runs the browser and, during development, the application services—not the AI model weights or model inference server.

**Goal:** make voice interactions safer by explaining risk signals and helping users pause before sharing sensitive information. VaaniShield is an assistive warning tool, not a guarantee that every scam will be detected.

## At a glance

| Area | Technology / approach |
|---|---|
| Frontend | React, TypeScript, Vite |
| Backend | Python 3.11+, FastAPI, WebSockets |
| Speech-to-text | Gnani Prisma realtime STT |
| Text-to-speech | Gnani Timbre realtime TTS |
| Scam detection | Deterministic rules first; optional contextual LLM analysis |
| Contextual model | Evon v3.3 is the intended Gnani reasoning model; hosted API entitlement and its exact request contract must be verified before claiming the managed integration is active |
| Session state | Redis-backed TTL sessions and rate limits in production |
| Audio transport | Mono PCM16LE over WebSockets |
| Local inference | **Not required.** Model inference is intended to happen through remote cloud APIs. |

## What is implemented

| Capability | Current implementation | What is still required |
|---|---|---|
| Realtime speech recognition | Prisma realtime WebSocket adapter (`hi-IN` / `en-IN`) | Valid Gnani API credentials, entitlement, and live account test |
| Browser audio capture & DSP | WebRTC AEC/NS/AGC + AudioWorklet 85 Hz Butterworth HPF, adaptive soft noise gate with TTS ducking, anti-alias filter, resampling, and PCM16 framing | HTTPS or localhost browser context and microphone permission |
| Scam pattern detection | Multilingual deterministic rules (English, Hinglish, Devanagari) with negation/reported-speech guards and cross-turn split-phrase detection across both ScamShield and Vaani Assistant | Broader labelled evaluation and tuning |
| Contextual scam analysis | Pooled `EvonClient` calling an OpenAI-compatible `/chat/completions` endpoint with semantic consistency validation | Confirm the Gnani-hosted Evon endpoint and adapt the provider request/response contract if it differs |
| Spoken warnings and replies | Timbre v2.5 realtime TTS adapter (`is_final` and `complete` support) and 120s-buffered PCM playback | Confirm voice availability and validate live account access |
| Session security | Short-lived HMAC capability, required WebSocket `Origin` enforcement, expiring ownership-aware socket lease, and TTL | Production secrets, explicit origins, TLS, and deployment verification |
| Shared session state | Redis-backed TTL store, Lua ownership lease release, sorted-set (`ZSET`) sliding-window rate limiting, and IPv6 `/64` normalization | Managed Redis or private production Redis |
| Protocol test hook | Backend `transcript.demo` WebSocket event for automated rule tests (live call UI streams microphone speech directly) | Keep test scenarios fictional |

**Important Evon integration note:** the current backend's `EvonClient` is written for an OpenAI-compatible `/chat/completions` endpoint configured through `EVON_BASE_URL` (tested with vLLM-compatible and local Ollama dev endpoints). That does not yet prove integration with Gnani's managed Evon API. Gnani's public Evon page describes a selected closed beta via a waitlist, with general availability still to be announced. A standard Prisma/Timbre API key does not by itself establish Evon access. Before enabling managed Evon in production, verify account selection and use the endpoint, authentication method, payload, and response schema supplied by Gnani. If the managed API contract differs from the current OpenAI-compatible adapter, implement a dedicated Gnani Evon adapter.

## Architecture

### 1. System & audio-security architecture

The browser handles microphone capture, lightweight AudioWorklet DSP, and audio playback. Application orchestration runs in the backend. Speech and reasoning inference run over remote provider APIs in production (or an optional local OpenAI-compatible server such as Ollama during local development).

```mermaid
flowchart LR
  subgraph CLIENT["User device — browser"]
    UI["React UI<br/>ScamShield + Vaani Assistant"]
    CAP["AudioWorklet<br/>85 Hz HPF, adaptive soft gate,<br/>anti-alias resample, PCM16"]
    PLAY["PCM audio player<br/>(120s jitter/burst buffer)"]
    UI --> CAP
    PLAY -.->|"tts_playing ducking"| CAP
    PLAY --> UI
  end

  subgraph APP["VaaniShield application — FastAPI runtime"]
    GW["FastAPI HTTP / WebSocket gateway"]
    AUTH["Session capability<br/>Required Origin & lease checks"]
    TURN["Per-session turn orchestrator"]
    RULES["Multilingual scam rules<br/>(EN, Hinglish, Devanagari + split-turn)"]
    VALID["ThreatResult semantic validator"]
    STORE[("Redis<br/>TTL sessions, leases, ZSET limiter")]
    GW --> AUTH --> TURN
    TURN --> RULES --> VALID
    TURN <--> STORE
  end

  subgraph PROVIDERS["AI inference services"]
    STT["Gnani Prisma<br/>realtime speech-to-text"]
    LLM["Evon v3.3 / OpenAI-compatible /v1<br/>(pooled HTTP client)"]
    TTS["Gnani Timbre<br/>realtime text-to-speech"]
  end

  CAP -->|"1,024-byte PCM16 frames over WSS"| GW
  TURN <-->|"audio stream / transcript events"| STT
  TURN -.->|"contextual classification or reply"| LLM
  LLM --> VALID
  VALID -->|"threat.detected / status"| UI
  TURN -->|"warning or assistant text"| TTS
  TTS -->|"PCM16 audio chunks"| GW
  GW -->|"binary audio"| PLAY
```

**Inference boundary:** in production, speech and reasoning inference run remotely (`EVON_BASE_URL` must use `https://` when `ENVIRONMENT=production`). For local development without GPU access, `EVON_BASE_URL` can point to a local OpenAI-compatible server such as Ollama. Never expose provider keys in `VITE_*` frontend variables.

### 2. ScamShield live-call detection sequence

ScamShield automatically monitors speech throughout the call. Explicit credential or remote-access demands (including Devanagari Hindi and phrases split across VAD pauses) trigger warnings in `<1 ms` without cancelling in-flight contextual LLM checks on earlier turns.

```mermaid
sequenceDiagram
  autonumber
  actor User
  participant Browser as Browser Mic & AudioWorklet
  participant API as FastAPI Gateway
  participant STT as Gnani Prisma STT
  participant Rules as Multilingual Rules
  participant LLM as Pooled Evon / OpenAI Client
  participant TTS as Gnani Timbre TTS

  User->>Browser: Speak in simulated call
  Browser->>Browser: WebRTC AEC/NS + 85 Hz HPF + adaptive gate
  Browser->>API: 1,024-byte PCM16 frames over WSS
  API->>STT: Forward realtime audio
  STT-->>API: Final transcript segment
  API-->>Browser: transcript.final
  API->>Rules: Check current turn + adjacent split-turn context
  alt Explicit credential or remote-access signal
    Rules-->>API: ThreatResult (critical / high)
  else Ambiguous turn (serialized without cancelling prior turns)
    API->>LLM: Transcript and bounded context
    LLM-->>API: JSON risk assessment (semantically validated)
  end
  API-->>Browser: threat.detected or analysis.status
  API->>TTS: Spoken warning (when scam detected)
  TTS-->>API: Realtime PCM16 audio chunks
  API-->>Browser: Stream warning audio
  Browser->>Browser: Play warning & raise AudioWorklet ducking gate
```

### 3. Vaani Assistant voice & protection sequence

Vaani Assistant keeps its own multi-turn conversation history and barge-in cancellation while still running automatic live scam detection on incoming utterances.

```mermaid
sequenceDiagram
  autonumber
  actor User
  participant Browser as Browser Mic & Player
  participant API as FastAPI Turn Manager
  participant STT as Gnani Prisma STT
  participant Rules as Multilingual Rules
  participant LLM as Pooled Evon / OpenAI Client
  participant TTS as Gnani Timbre TTS

  User->>Browser: Speak during voice call
  Browser->>API: Stream 1,024-byte PCM16 frames
  API->>STT: Forward audio frames
  STT-->>API: Final transcript
  API-->>Browser: transcript.final
  API->>Rules: Instant explicit scam check
  alt Explicit scam demand detected
    Rules-->>API: ThreatResult + warning message
    API-->>Browser: threat.detected + assistant.message
    API->>TTS: Synthesize spoken scam warning
  else Normal or ambiguous turn
    API->>LLM: Multi-turn chat messages (bounded history)
    LLM-->>API: Spoken reply text
    API-->>Browser: assistant.message
    opt Suspicious keywords detected
      API--)LLM: Non-blocking background scam classification
      LLM--)API: threat.detected (if scam confirmed)
    end
    API->>TTS: Synthesize assistant response
  end
  TTS-->>API: PCM16 audio chunks
  API-->>Browser: audio.output.start + binary PCM chunks
  Browser->>Browser: Play full response (120s buffer) + duck mic gate
  Note over Browser,API: Manual interrupt or replacement user speech cancels the active reply and flushes queued audio.
```

## Runtime behaviour

1. The user starts a session and grants microphone permission (with WebRTC AEC/NS/AGC enabled).
2. The browser AudioWorklet runs an 85 Hz Butterworth high-pass filter, an adaptive noise-floor soft gate (with 300 ms hangover and TTS playback ducking), and anti-alias resampling to emit 1,024-byte mono PCM16LE frames.
3. The frontend opens an `Origin`-validated, HMAC-authenticated WebSocket to FastAPI and streams bounded binary frames.
4. FastAPI forwards audio to Prisma and receives transcript events.
5. **ScamShield** checks English, Hinglish, and Devanagari deterministic rules (including adjacent VAD-split turns) immediately; ambiguous turns run sequentially through the pooled LLM client with semantic validation without cancelling earlier in-flight checks.
6. **Vaani Assistant** runs instant deterministic scam checks first, generates clean multi-turn conversational replies, runs non-blocking contextual scam classification when suspicious cues appear, and streams spoken audio via Timbre v2.5.
7. The browser queues incoming PCM chunks (up to a 120s buffer) and raises the AudioWorklet ducking threshold while audio plays so speaker bleed does not interrupt speech.
8. On interruption, disconnect, or expiry, active tasks and audio streams are cancelled and the ownership-aware session lease is released.

## How to use

1. Start the backend and frontend servers (see **Getting started** below) and open `http://localhost:5173`.
2. On the home page, verify **Provider readiness** (`Prisma`, `Evon`, and `Timbre` show `Configured` when values are set in `backend/.env`).
3. Pick an experience:
   - **Try scam simulation (`/scam-demo`):** Choose **Hindi** or **English**, click **Simulate incoming call** → **Accept**, and speak into the microphone. Live Prisma transcripts appear automatically, explicit OTP/UPI PIN/remote-access requests trigger immediate `SCAM CALL DETECTED` alerts and Timbre spoken warnings, and ambiguous turns (e.g. KYC links or digital arrest threats) are evaluated by the configured LLM endpoint.
   - **Talk to Vaani (`/assistant`):** Enabled when `Prisma`, `Timbre`, and `EVON_BASE_URL` are all configured. Accept the session and speak naturally in Hindi, Hinglish, or English—Vaani replies aloud while background scam monitoring watches the conversation. Use **Interrupt Vaani**, **Mute microphone**, **Mute speaker**, or **End session** at any time.

## Repository layout

```text
.
├── backend/
│   ├── app/
│   │   ├── gnani/          # Prisma STT and Timbre TTS adapters
│   │   ├── risk/           # Deterministic rules and Evon client
│   │   ├── sessions/       # Session store, tokens, and rate limits
│   │   ├── config.py       # Environment-backed settings
│   │   ├── main.py         # HTTP API, WebSocket gateway, orchestration
│   │   └── schemas.py      # Request and response schemas
│   ├── evaluation/         # Smoke evaluation tools and synthetic datasets
│   ├── tests/
│   └── .env.example
├── frontend/
│   ├── public/audio/       # AudioWorklet processor
│   └── src/
│       ├── audio/          # Capture and PCM playback
│       ├── api.ts
│       └── App.tsx
├── docs/
│   ├── ARCHITECTURE.md
│   ├── GNANI_INTEGRATION.md
│   ├── PROTOCOL.md
│   └── SECURITY.md
├── docker-compose.yml
└── README.md
```

## Getting started

### Requirements

- Python 3.11 or newer
- Node.js 20 or newer
- npm
- A modern browser with AudioWorklet support
- A Gnani API account with access to the required speech services
- HTTPS in deployed environments; localhost is sufficient for local microphone development

You can run the frontend and backend locally for development while all speech/model inference remains remote. Redis is recommended for production and is included in the Docker Compose setup.

### 1. Configure the backend

From the repository root:

```bash
cd backend
python -m venv .venv

# Windows PowerShell
.venv\Scripts\Activate.ps1

# macOS / Linux
# source .venv/bin/activate

pip install -e ".[dev]"
```

Copy the example environment file:

```bash
# Windows PowerShell
Copy-Item .env.example .env

# macOS / Linux
# cp .env.example .env
```

Add your Gnani API key to `backend/.env`:

```dotenv
GNANI_API_KEY=your_gnani_api_key
```

Keep this file private. Never commit it or place provider credentials in a `VITE_*` frontend variable.

### 2. Configure contextual reasoning

The `EvonClient` adapter calls an OpenAI-compatible `/chat/completions` API. In production (`ENVIRONMENT=production`), `EVON_BASE_URL` must use `https://`:

```dotenv
EVON_BASE_URL=https://your-authorized-remote-endpoint/v1
EVON_MODEL=your-provider-model-id
EVON_API_KEY=your-provider-api-key
EVON_TIMEOUT_SECONDS=20
```

For local CPU/laptop development without remote Evon access (`ENVIRONMENT=development`), you can also point `EVON_BASE_URL` at a local OpenAI-compatible server such as Ollama (`ollama serve`):

```dotenv
EVON_BASE_URL=http://127.0.0.1:11434/v1
EVON_API_KEY=
EVON_MODEL=qwen2.5-coder:1.5b
EVON_TIMEOUT_SECONDS=45
```

If Gnani's managed Evon endpoint uses a non-OpenAI contract, implement a dedicated Gnani Evon adapter. If `EVON_BASE_URL` is left blank, deterministic ScamShield rules remain active while contextual LLM classification and Vaani Assistant stay disabled.

### 3. Start the backend

```bash
uvicorn app.main:app --reload --port 8000
```

The API is available at `http://localhost:8000`. Useful endpoints:

- `GET /health` — process health
- `GET /ready` — readiness and provider configuration status
- `GET /api/config` — frontend-safe model/configuration metadata

### 4. Start the frontend

In a second terminal:

```bash
cd frontend
npm install
```

Create the frontend environment file:

```dotenv
VITE_API_BASE=http://localhost:8000
```

Start Vite:

```bash
npm run dev
```

Open `http://localhost:5173` and grant microphone access when starting a session.

## Environment configuration

| Variable | Purpose | Notes |
|---|---|---|
| `GNANI_API_KEY` | Authenticates Prisma and Timbre requests | Secret; backend only |
| `PRISMA_MODEL` | Prisma model label | Defaults to `prisma-v2.5` |
| `PRISMA_WS_URL` | Realtime STT WebSocket endpoint | Defaults to the current configured Gnani endpoint |
| `PRISMA_LANGUAGE_CODE` | STT language | `hi-IN` or `en-IN` in current settings |
| `TIMBRE_MODEL` | TTS model label | Defaults to `timbre-v2.5` |
| `TIMBRE_WS_URL` | Realtime TTS WebSocket endpoint | Defaults to the current configured Gnani endpoint |
| `TIMBRE_VOICE` | TTS voice | Confirm availability in your Gnani account |
| `TIMBRE_LANGUAGE` | TTS language mode | Defaults to `hi-en` |
| `EVON_BASE_URL` | OpenAI-compatible reasoning `/v1` endpoint | Must use `https://` in `production`; local endpoints such as Ollama can be used in `development` |
| `EVON_MODEL` | Model identifier expected by that endpoint | Use the provider-issued identifier |
| `EVON_API_KEY` | Optional reasoning-provider credential | Secret; backend only |
| `ENVIRONMENT` | Runtime environment | `development`, `test`, or `production` |
| `CORS_ORIGINS` | Allowed browser origins | Explicit origins in production |
| `SESSION_SIGNING_SECRET` | Signs session capabilities | Use a unique random value of at least 32 characters in production |
| `SESSION_TTL_SECONDS` | Session capability lifetime | Maximum 840 seconds in current settings |
| `REDIS_URL` | Shared session store and rate limiter | Required in production |

The complete set of variables and defaults is maintained in [backend/.env.example](backend/.env.example).

## Run tests and checks

Backend:

```bash
cd backend
pytest -q
ruff check app tests evaluation
python -m evaluation.evaluate_rules --dataset evaluation/datasets/rules_smoke.jsonl
python -m evaluation.evaluate_transcripts --dataset evaluation/datasets/transcripts_smoke.jsonl
python -m evaluation.evaluate_latency --dataset evaluation/datasets/latency_smoke.jsonl
```

Frontend:

```bash
cd frontend
npm install
npm run build
```

The checked-in evaluation datasets are synthetic smoke examples, not production model benchmarks. Evaluate with a labelled, held-out dataset before making accuracy or latency claims. CI runs backend lint/tests, smoke evaluations, and the frontend production build.

## Docker Compose

The repository includes a Compose setup for the API, frontend, and Redis:

```bash
# From the repository root, after configuring backend/.env
docker compose up --build
```

The frontend is exposed on port 8080 by default. Configure `CORS_ORIGINS` to match the browser-facing origin. Use TLS through a trusted reverse proxy for deployment. Docker Compose runs the application services and Redis; it does not download or run AI model weights.

## Security, privacy, and safety

- Provider API keys stay on the backend and must never be exposed through frontend build variables or API responses.
- WebSocket sessions use short-lived HMAC capabilities, required `Origin` validation, and an expiring ownership-aware connection lease.
- Session creation uses sliding-window IP rate limiting (Redis sorted-set in production, IPv6 `/64` normalized).
- Production should use Redis, explicit CORS origins, a strong unique signing secret, and HTTPS/WSS.
- Raw audio and transcripts are not persisted by default.
- Do not log raw audio, provider credentials, authorization headers, or sensitive financial information.
- Use fictional examples in demonstrations. Never ask for or store real OTPs, UPI PINs, CVVs, passwords, or full account details.
- Clearly disclose that users are interacting with an AI assistant.
- VaaniShield is not a certified financial security product and does not currently intercept real phone calls.
- Browser WebRTC AEC/NS/AGC and the AudioWorklet 85 Hz HPF / adaptive soft gate reduce low-frequency hum and speaker bleed, but are not certified neural denoising; evaluate noisy ASR accuracy directly.

## Known limitations and release checklist

Before describing the system as production-ready:

- [ ] Verify the active Gnani account's Prisma and Timbre entitlements, quotas, and selected voice.
- [ ] Obtain and verify Evon hosted API access, endpoint, authentication, payload, and response schema.
- [ ] Implement or validate the Evon provider adapter against the actual account API; do not assume OpenAI compatibility.
- [ ] Run live end-to-end tests for microphone capture, STT, contextual analysis, TTS, interruption, and reconnect behaviour.
- [ ] Measure end-to-end latency, transcript WER/CER, scam precision/recall, and false-positive/false-negative rates on a held-out dataset.
- [ ] Perform security and load testing; configure TLS, Redis, CORS, rate limits, secrets, and monitoring.
- [ ] Validate the user-facing disclosure and warning language for each supported language.

A configured key or endpoint is not proof that a provider is reachable, entitled, healthy, or accurate.

## Official references

- [Gnani API quick start](https://docs.gnani.ai/api/introduction/quick-start)
- [Prisma realtime STT](https://docs.gnani.ai/api/STT/stt-websocket)
- [Timbre realtime TTS](https://docs.gnani.ai/api/TTS/tts-websocket)
- [Evon v3.3 hosted API waitlist and closed-beta information](https://www.gnani.ai/evon-waitlist)
- [Evon v3.3 open-weight model card](https://huggingface.co/gnani/gnani-evon-v3.3-30B-A3B)

---

**Repository:** https://github.com/Bhaumik-99/gnani.ai-task
