from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from evaluation.metrics import character_error_rate, word_error_rate


def evaluate(path: Path) -> dict:
    language_scores: dict[str, list[tuple[float, float]]] = defaultdict(list)
    with path.open(encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid JSON at line {line_no}") from error
            if not isinstance(row, dict) or not isinstance(row.get("reference"), str) or not isinstance(row.get("hypothesis"), str):
                raise ValueError(f"Expected reference and hypothesis strings at line {line_no}")
            language = str(row.get("language", "unknown"))[:32]
            language_scores[language].append((
                word_error_rate(row["reference"], row["hypothesis"]),
                character_error_rate(row["reference"], row["hypothesis"]),
            ))
    if not language_scores:
        raise ValueError("Transcript dataset is empty")

    def summarize(scores: list[tuple[float, float]]) -> dict:
        return {
            "samples": len(scores),
            "wer": round(sum(score[0] for score in scores) / len(scores), 4),
            "cer": round(sum(score[1] for score in scores) / len(scores), 4),
        }

    all_scores = [score for scores in language_scores.values() for score in scores]
    return {
        "samples": len(all_scores),
        "scope": "transcript text only; not an ASR provider benchmark unless hypotheses come from the measured provider",
        "overall": summarize(all_scores),
        "by_language": {language: summarize(scores) for language, scores in sorted(language_scores.items())},
    }


def main():
    parser = argparse.ArgumentParser(description="Calculate WER/CER from a reference/hypothesis JSONL file.")
    parser.add_argument("--dataset", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.dataset), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
