# Gnani integration checklist

Target model versions requested for this project:
- Prisma v3.0 — speech-to-text
- Evon v3.3 — reasoning/classification
- Timbre v3.0 — text-to-speech
- Warp v2.0 — optional speech-to-speech experiment

This repository intentionally does not guess endpoint paths, headers, payloads, voice IDs or WebSocket event schemas. Confirm each item in the current official Gnani developer documentation and your account console before writing the adapter.

## Verify for each model
1. Exact model identifier enabled for this API account.
2. Endpoint URL and region.
3. Authentication header or handshake format.
4. Request/response schema and streaming event names.
5. Audio format: codec, sample rate, bit depth, channel count, frame size.
6. Language and code-mix options for Hinglish.
7. Keepalive, end-of-turn, cancellation and reconnect semantics.
8. Quotas, rate limits, concurrency and billing.

## Backend environment variables
- GNANI_API_KEY
- GNANI_PRISMA_WS_URL
- GNANI_EVON_URL
- GNANI_TIMBRE_WS_URL
- GNANI_WARP_URL (only if a supported Warp operation is documented)

Do not prefix secrets with VITE_ or expose them to browser code. Do not commit .env files.

## Implementation notes
Prisma must forward partial and final transcript events in order. Resample browser audio to the exact documented provider format. Evon output must be schema-validated and invalid responses must result in an uncertain/safe state. Timbre audio chunks need codec validation, bounded playback queues and cancellation on interruption where supported.

Warp speech-to-speech does not itself prove denoising. If there is no official audio enhancement operation returning processed audio, leave denoising unavailable and report ASR robustness metrics separately.
