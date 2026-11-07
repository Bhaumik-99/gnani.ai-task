# Implementation status and release gates

## Implemented in code

- [x] React/Vite routes for ScamShield and Vaani Assistant.
- [x] FastAPI session creation, health/readiness/config endpoints and WebSocket gateway.
- [x] Short-lived HMAC session capability token carried in WebSocket subprotocol.
- [x] Origin checking, single active socket, TTL storage and rate limiting.
- [x] Redis-backed shared session store/rate limit for production.
- [x] Prisma realtime adapter using published auth/config headers and PCM frame contract.
- [x] AudioWorklet capture, resampling, PCM16LE framing and binary transport.
- [x] Deterministic credential and remote-access detection with evidence.
- [x] Optional Evon v3.3 contextual classification through self-hosted OpenAI-compatible vLLM.
- [x] Timbre v2.5 realtime synthesis and raw PCM playback.
- [x] Turn cancellation, assistant interruption, playback mute and session cleanup.
- [x] Expanded backend security, session and risk regression tests.
- [x] CI backend tests/lint and frontend production build.

## Must be validated with real accounts/devices

- [ ] Add a Gnani API key and smoke-test live Prisma transcription.
- [ ] Verify the selected Timbre voice and test realtime synthesis.
- [ ] Obtain Evon v3.3 weights, provision compatible vLLM hardware and validate response schema.
- [ ] Test microphone capture/playback across target browsers and devices.
- [ ] Test actual VAD segmentation, reconnect behavior and interruption during TTS.
- [ ] Measure WER/CER on independently labelled Hindi/English/Hinglish audio.
- [ ] Measure held-out scam precision, recall, false-positive and false-negative rates.
- [ ] Measure STT, classifier, TTS first-audio and end-to-end latency; report dropped frames.
- [ ] Load-test the Redis-backed multi-worker deployment and run a security review.

## Release rule

Do not claim production readiness, model accuracy, low latency or noise cancellation until those checks have been run with recorded test conditions and results. Warp is not integrated and no denoising feature is claimed.
