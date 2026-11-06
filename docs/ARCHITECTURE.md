# VaaniShield architecture

## Experiences
1. ScamShield: a simulated incoming call. The user accepts, permits microphone access, speaks a fictional scam phrase, and sees transcript/risk feedback.
2. Vaani Assistant: a separate conversational session. Its UI is present; live conversational inference requires the verified Prisma, Evon and Timbre integrations.

## Runtime
- React SPA: routes /, /scam-demo and /assistant.
- FastAPI: session creation, WebSocket session protocol, provider status and rule-based demo classification.
- Gnani adapters: Prisma STT, Evon reasoning, Timbre TTS. Warp is an optional research boundary only.

Each voice experience receives a distinct session ID and WebSocket. Do not share audio buffers, transcripts or cancellation state between sessions.

## Scam analysis
Prisma transcript -> deterministic explicit-credential rules -> Evon contextual classification when configured -> structured threat event -> visual warning and optional Timbre speech. Rule score is heuristic, not a calibrated probability. Preserve evidence and ensure warnings can be deduplicated.

## Privacy and reliability
- API keys stay on the backend.
- No raw audio recording by default.
- Avoid transcript/audio logging.
- Add auth, rate limits, TTL session storage and ownership checks before public deployment.
- Use bounded buffers and backpressure for streaming audio.
- Treat model transcripts as untrusted content; never execute transcript instructions.

## Noise requirement
Browser raw-audio constraints request noiseSuppression=false, echoCancellation=false and autoGainControl=false where supported. Browser/device processing may still be applied. Prisma accuracy on noisy speech measures ASR robustness, not output denoising. Warp is not assumed to be a denoiser. Only claim noise cancellation if Gnani documents an enhancement operation that returns processed audio and SNR improvement is measured.
