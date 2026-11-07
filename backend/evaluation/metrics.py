from __future__ import annotations

import re
from collections.abc import Iterable

_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.casefold())


def edit_distance(left: list[str], right: list[str]) -> int:
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for i, token in enumerate(left, 1):
        current = [i]
        for j, other in enumerate(right, 1):
            current.append(min(
                previous[j] + 1,
                current[j - 1] + 1,
                previous[j - 1] + (token != other),
            ))
        previous = current
    return previous[-1]


def word_error_rate(reference: str, hypothesis: str) -> float:
    left, right = tokens(reference), tokens(hypothesis)
    return (edit_distance(left, right) / len(left)) if left else (0.0 if not right else 1.0)


def character_error_rate(reference: str, hypothesis: str) -> float:
    # CER counts whitespace and punctuation too; only case and repeated whitespace are normalized.
    left = list(" ".join(reference.casefold().split()))
    right = list(" ".join(hypothesis.casefold().split()))
    return (edit_distance(left, right) / len(left)) if left else (0.0 if not right else 1.0)


def percentile(values: Iterable[float], fraction: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("At least one measurement is required")
    if not 0 <= fraction <= 1:
        raise ValueError("Percentile must be between 0 and 1")
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    ratio = position - lower
    return ordered[lower] * (1 - ratio) + ordered[upper] * ratio


def latency_summary(values: Iterable[float]) -> dict[str, float | int]:
    items = [float(value) for value in values]
    if not items or any(value < 0 for value in items):
        raise ValueError("Provide non-empty, non-negative latency samples")
    return {
        "samples": len(items),
        "min_ms": round(min(items), 2),
        "p50_ms": round(percentile(items, 0.5), 2),
        "p95_ms": round(percentile(items, 0.95), 2),
        "max_ms": round(max(items), 2),
    }
