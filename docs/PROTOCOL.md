# VaaniShield browser WebSocket protocol

Create a session with `POST /api/sessions`. The response contains a short-lived signed capability token. Connect to `/ws/sessions/{session_id}` with these WebSocket subprotocols:

- `vaanishield.v1`
- `session.<signed-capability-token>`

The token is carried in the handshake subprotocol rather than the URL. The server checks the signature, expiry, session binding, Origin (when present) and exclusive socket claim.

## Client text events

```json
{"event":"session.start","payload":{"language_code":"hi-IN","sample_rate":16000}}
{"event":"transcript.demo","payload":{"text":"Please share your OTP"}}
{"event":"assistant.interrupt","payload":{}}
{"event":"session.end","payload":{}}
```

`transcript.demo` is supported only for the ScamShield simulated experience. It is untrusted sample text and is not represented as a Prisma transcript.

## Client binary frames

Microphone audio is sent as binary WebSocket messages rather than base64 JSON. Each message contains exactly 1,024 bytes of mono PCM16LE (512 samples). At 16 kHz this is one frame every 32 ms; at 8 kHz one every 64 ms. The server validates size and cadence before forwarding the frame to Prisma.

## Server text events

- Lifecycle: `session.ready`, `session.started`, `session.ended`, `session.expired`.
- Providers: `provider.status`, `provider.error`.
- Transcript: `speech.start`, `transcript.partial`, `transcript.meta`, `transcript.processing`, `transcript.final`.
- Analysis: `analysis.status`, `threat.detected`, `threat.updated`.
- Assistant/audio: `assistant.message`, `assistant.error`, `assistant.interrupted`, `audio.output.start`, `audio.output.end`, `audio.output.error`.
- Validation: `error`.

## Server binary frames

Timbre output is forwarded as raw mono PCM16LE binary messages. The preceding `audio.output.start` event provides the sample rate. Playback is bounded and cancelled on interruption.

## Lifecycle

Session capability lifetime is configured with `SESSION_TTL_SECONDS` (60–840 seconds). A session permits one active WebSocket. Disconnect, expiry, interruption and explicit end cancel active tasks and close provider resources.
