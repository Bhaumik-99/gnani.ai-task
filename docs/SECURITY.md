# Security and privacy notes

## Implemented protections

- Provider API keys stay on the backend.
- Session capabilities are HMAC-signed, bound to a session ID and short-lived (maximum 14 minutes).
- Capability tokens are carried in the WebSocket subprotocol instead of URL query parameters.
- WebSocket Origin is checked when supplied; CORS uses explicit configured origins.
- One active WebSocket connection is allowed for each session.
- Session creation has IP-based rate limiting, shared through Redis in production.
- Production startup requires a Redis URL, explicit CORS origins and a unique signing secret of at least 32 characters.
- Control payloads and binary audio frames are size-limited and audio cadence is checked.
- Raw audio and transcripts are not persisted by default.

## Deployment requirements

- Keep `.env` out of version control and rotate credentials if exposed.
- Serve the application over HTTPS; microphone capture requires a secure browser context.
- Keep FastAPI private behind the included Nginx reverse proxy or another trusted gateway.
- Restrict Redis and Evon inference endpoints to a private application network.
- Use TLS for remote Redis and Evon endpoints.
- Redact transcripts, audio, authorization headers and sensitive financial data from application logs and traces.
- Never ask users to provide real OTPs, UPI PINs, CVVs or passwords.

## Remaining security work

This repository does not implement end-user identity accounts, persistent consent records, a formal retention workflow, or an independent penetration test. It should not be represented as a certified financial security product or a real mobile-call protection service.
