from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from evaluation.metrics import latency_summary


def evaluate(path: Path) -> dict:
    metrics: dict[str, list[float]] = defaultdict(list)
    with path.open(encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid JSON at line {line_no}") from error
            if not isinstance(row, dict):
                raise ValueError(f"Expected object at line {line_no}")
            for name, value in row.items():
                if name in {"id", "language", "notes"} or value is None:
                    continue
                if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                    raise ValueError(f"Invalid latency value for {name!r} at line {line_no}")
                metrics[name].append(float(value))
    if not metrics:
        raise ValueError("No latency values found")
    return {
        "units": "milliseconds",
        "metrics": {name: latency_summary(values) for name, values in sorted(metrics.items())},
    }


def main():
    parser = argparse.ArgumentParser(description="Summarize VaaniShield latency samples.")
    parser.add_argument("--dataset", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.dataset), indent=2))


if __name__ == "__main__":
    main()
