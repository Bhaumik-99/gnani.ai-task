# Evaluation methodology

The included `backend/evaluation/evaluate_rules.py` script evaluates only the deterministic transcript rules against a labelled JSONL file.

## Dataset format

Each line is a JSON object with:
- `text`: fictional transcript text.
- `label`: `scam` or `benign`.

Example:

```json
{"id":"example-1","text":"Please share your OTP now.","label":"scam"}
```

Run:

```bash
cd backend
python -m evaluation.evaluate_rules --dataset evaluation/datasets/rules_smoke.jsonl
```

The checked-in set is a synthetic smoke suite for regression coverage only. Its metrics must not be marketed as the application's accuracy.

## Required measured benchmarks

Before a production launch, collect an independently labelled, held-out test set that includes Hindi, English, Hinglish/code-mixed speech, benign financial conversations, reported scams, negation, remote-access manipulation and varied speaking conditions.

Report:
- Scam detection: precision, recall, F1, false-positive rate, false-negative rate and confusion matrix.
- Speech recognition: WER and CER by language and noise condition.
- Streaming: partial/final transcript latency, model classification latency, TTS time-to-first-audio, frame loss and reconnection rate.
- Reliability: concurrent session count, disconnect rate, provider error rate and recovery time.

Record sample counts, language distribution, annotation method, test date and provider/model versions. Do not claim model confidence is calibrated probability without calibration data. Do not claim denoising from improved transcript accuracy; output-audio enhancement and SNR must be measured separately.
