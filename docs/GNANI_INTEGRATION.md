# Gnani integration guide

This guide follows the current published API docs. Verify access and voice availability in the Gnani console before live use.

## Prisma realtime STT

Published endpoint: `wss://api.vachana.ai/stt/v3/stream`

Required WebSocket headers:
- `x-api-key-id`: Gnani API key.
- `lang_code`: BCP-47 language code such as `hi-IN` or `en-IN`.
- `x-sample-rate`: `8000` or `16000` for the VaaniShield PCM frame modes.
- `x-format`: `verbatim` or `transcribe`; the latter enables inverse text normalization.

Do not send an undocumented `model`, `language_code` or `format` header. The public realtime docs use `lang_code` and `x-format`.

Audio is raw mono PCM signed 16-bit little-endian:
- 512 samples per frame.
- Exactly 1,024 bytes per frame.
- One frame every 32 ms at 16 kHz or every 64 ms at 8 kHz.
- Send frames at real-time cadence, not in bursts.

Server messages include `connected`, `processing`, `transcript` and `error`. A completed transcript contains `text`, `segment_id`, `segment_index`, `audio_duration_ms` and `latency`.

## Timbre realtime TTS

Published endpoint: `wss://api.vachana.ai/api/v1/tts`

Required header:
- `X-API-Key-ID`: Gnani API key.

Current API docs list Timbre v2.5. Request example used by this application:
- `model: timbre-v2.5`
- `voice: Poorvi` (verify exact voice availability in your account catalog).
- `language: hi-en` for Hinglish.
- `audio_config.sample_rate: 24000`
- `num_channels: 1`
- `sample_width: 2`
- `encoding: linear_pcm`
- `container: raw`

Timbre sends JSON `start`, `audio`, `complete`, and `error` messages. Audio data is base64 in `data.audio`; the backend decodes it and forwards raw PCM16LE bytes. The `complete` event has `data.is_final=true`.

## Evon v3.3

Evon v3.3 is currently open-weight and not exposed as a hosted inference model in the API platform. Obtain access to the weights and serve them yourself (for example, with vLLM's OpenAI-compatible API).

Configuration:
- `EVON_BASE_URL`: private endpoint root ending in `/v1`.
- `EVON_MODEL`: served model identifier.
- `EVON_API_KEY`: optional gateway bearer credential.

The backend calls `/chat/completions`, supplies transcript context as untrusted data, disables thinking via `chat_template_kwargs.enable_thinking=false`, and validates structured classification output. The exact supported vLLM version, chat template and hardware must be verified against the downloaded model release.

## Environment variables

See `backend/.env.example`. Never prefix provider secrets with `VITE_`, return them from `/api/config`, or commit `.env`.

## Contract verification

Unit tests should mock network calls. A live smoke test is still required for each account to confirm credentials, plan entitlement, rate limits, model access, selected voice and current payload compatibility.

Official references:
- https://docs.gnani.ai/api/STT/stt-websocket
- https://docs.gnani.ai/api/TTS/tts-websocket
- https://docs.gnani.ai/api/introduction/quick-start
- https://www.gnani.ai/internship
