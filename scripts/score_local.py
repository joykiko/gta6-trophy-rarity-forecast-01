"""Local scoring of supplied answers; no answer data is shipped here."""

import argparse
import json
import math
from pathlib import Path

LEVELS = (0.05, 0.25, 0.5, 0.75, 0.95)


def logit(rate):
    clamped = min(99.99, max(0.01, rate))
    return math.log(clamped / (100 - clamped))


def score(answers, output_dir):
    total = miss = covered = 0.0
    count = 0
    for case_id, actual in sorted(answers.items()):
        data = json.loads((Path(output_dir) / (case_id + ".out")).read_text())
        rows = sorted(data["trophies"], key=lambda row: row["id"])
        if len(rows) != len(actual):
            raise ValueError("Forecast and answer lengths differ")
        for truth, row in zip(actual, rows):
            q = row["q"]
            for tau, estimate in zip(LEVELS, q):
                delta = logit(truth) - logit(estimate)
                total += 2 * max(tau * delta, (tau - 1) * delta)
            miss += abs(truth - q[2])
            covered += q[0] <= truth <= q[4]
            count += 1
    return {"loss": total / (5 * count), "typical_miss_pp": miss / count, "coverage_90": covered / count}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("answers", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    result = score(json.loads(args.answers.read_text()), args.output_dir)
    print(" ".join(f"{name}={value:.6f}" for name, value in result.items()))
