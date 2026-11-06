# Implementation milestones

## Milestone 1 — foundation
- [x] React/Vite/TypeScript mobile UI and routes.
- [x] FastAPI health, sessions and WebSocket scaffold.
- [x] Conservative local credential-request rules.
- [x] Gnani adapter boundaries, environment template and docs.
- [x] Initial tests and CI.

## Milestone 2 — provider contracts
- [ ] Confirm Prisma/Evon/Timbre/Warp access in the Gnani console.
- [ ] Record exact model IDs, endpoints, auth, payload schemas and streaming events.
- [ ] Implement Prisma streaming and contract tests.
- [ ] Implement Evon contextual JSON analysis.
- [ ] Implement Timbre streamed speech synthesis.
- [ ] Verify whether Warp supports audio enhancement; no denoising claims without it.

## Milestone 3 — live audio
- [ ] Implement resampling to provider-required sample rate.
- [ ] Add binary transport, backpressure and sequence validation.
- [ ] Forward partial/final transcripts.
- [ ] Add cancellation and reconnect handling.

## Milestone 4 — product logic
- [ ] Context-aware risk aggregation and alert deduplication.
- [ ] Timbre spoken warnings.
- [ ] Assistant response streaming and interruption handling.
- [ ] Consent UX for any future recording.

## Milestone 5 — production hardening
- [ ] Authentication, session ownership and TTL persistence.
- [ ] Rate limits, abuse controls and structured secret-redacted logs.
- [ ] Hinglish scam/benign evaluation set.
- [ ] WER, precision, recall, false-positive and latency tests.
- [ ] Noise test matrix; SNR tests only if enhanced audio is actually available.
