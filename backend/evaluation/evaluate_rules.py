from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.risk.rules import analyse_explicit_request


def evaluate(path: Path) -> dict:
    tp = fp = tn = fn = 0
    count = 0
    with path.open(encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid JSON at line {line_no}") from error
            if not isinstance(row, dict) or not isinstance(row.get("text"), str) or row.get("label") not in {"scam", "benign"}:
                raise ValueError(f"Invalid record at line {line_no}")
            predicted = analyse_explicit_request(row["text"]) is not None
            actual = row["label"] == "scam"
            tp += predicted and actual
            fp += predicted and not actual
            tn += not predicted and not actual
            fn += not predicted and actual
            count += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "samples": count,
        "scope": "deterministic rules only; not an ASR/Evon or end-to-end model benchmark",
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "false_positive_rate": round(fp / (fp + tn), 4) if fp + tn else 0.0,
        "false_negative_rate": round(fn / (fn + tp), 4) if fn + tp else 0.0,
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate deterministic scam rules on labelled JSONL.")
    parser.add_argument("--dataset", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.dataset), indent=2))


if __name__ == "__main__":
    main()
