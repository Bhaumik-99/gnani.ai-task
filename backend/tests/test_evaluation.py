from pathlib import Path

import pytest

from evaluation.evaluate_rules import evaluate
from evaluation.metrics import character_error_rate, latency_summary, percentile, word_error_rate


def test_wer_and_cer_casefold_and_tokenize_native_script():
    assert word_error_rate("Please share your OTP", "please share your otp") == 0
    assert word_error_rate("नमस्ते आप कैसे हैं", "नमस्ते आप कैसे") == pytest.approx(1 / 6)
    assert character_error_rate("hello", "hallo") == pytest.approx(0.2)
    assert character_error_rate("hello world", "helloworld") > 0


def test_empty_reference_metrics():
    assert word_error_rate("", "") == 0
    assert word_error_rate("", "hello") == 1


def test_latency_summary_interpolates_percentiles():
    assert latency_summary([10, 20, 30, 40]) == {
        "samples": 4,
        "min_ms": 10.0,
        "p50_ms": 25.0,
        "p95_ms": 38.5,
        "max_ms": 40.0,
    }


def test_metrics_reject_invalid_samples():
    with pytest.raises(ValueError):
        percentile([1, 2], 2)
    with pytest.raises(ValueError):
        latency_summary([3, -1])


def test_synthetic_rule_smoke_dataset_is_labelled():
    dataset = Path(__file__).parents[1] / "evaluation" / "datasets" / "rules_smoke.jsonl"
    result = evaluate(dataset)
    assert result["samples"] >= 8
    assert result["tp"] >= 1
    assert result["tn"] >= 1
    assert result["scope"].startswith("deterministic rules only")
