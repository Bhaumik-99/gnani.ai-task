# WebSocket protocol (scaffold)

Connect to /ws/sessions/{session_id}. Each socket belongs to exactly one session.

## Client events

Start:
```json
{"event":"session.start","payload":{"language":"hi-en","sample_rate":16000,"encoding":"pcm_s16le"}}
```

Audio envelope:
```json
{"event":"audio.chunk","payload":{"sequence":1,"encoding":"pcm_s16le","sample_rate":16000,"channels":1,"data":"BASE64"}}
```

Demo-only local rule check:
```json
{"event":"transcript.demo","payload":{"text":"Please share your OTP"}}
```

Interrupt and end:
```json
{"event":"assistant.interrupt","payload":{}}
{"event":"session.end","payload":{}}
```

## Server events
- session.ready
- provider.status
- transcript.partial
- transcript.final
- threat.detected
- assistant.interrupted
- session.ended
- error

The initial implementation validates base64 frame size and sequence order, but it does not forward audio to Prisma. The transcript.demo event is deliberately untrusted, demo-only input to exercise deterministic rules. Production transcript events must originate from the Prisma adapter.

Use a binary framing protocol and bounded queues for production after the actual Gnani streaming framing is verified.
