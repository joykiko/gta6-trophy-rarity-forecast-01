"""Run practice plausibility, strict shape, timing and byte identity checks."""

import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def validate(path):
    raw = path.read_bytes()
    assert len(raw) <= 65536 and raw.endswith(b"\n")
    data = json.loads(raw)
    assert set(data) == {"trophies"}
    rows = data["trophies"]
    assert len(rows) == 55
    assert [row["id"] for row in rows] == list(range(1, 56))
    for row in rows:
        assert set(row) == {"id", "q"}
        q = row["q"]
        assert len(q) == 5 and q == sorted(q)
        assert all(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 100 for value in q)
        assert all(abs(value * 10000 - round(value * 10000)) < 1e-6 for value in q)
    return rows, raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kit", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="trophy-repeat-") as temp:
        directories = [root / "out-local", Path(temp) / "second"]
        for number, directory in enumerate(directories, 1):
            begin = time.perf_counter()
            subprocess.run([sys.executable, "-P", "-s", str(root / "main.py")], check=True, timeout=8,
                           env=dict(os.environ, MAKEFUN_INPUT_DIR=str(args.kit / "input"), MAKEFUN_OUTPUT_DIR=str(directory)))
            elapsed = time.perf_counter() - begin
            print(f"run {number}: {elapsed:.6f} seconds for both practice cases")
            assert elapsed < 1.0
        for path in sorted((args.kit / "input").glob("*.in")):
            case = json.loads(path.read_text())
            rows, raw = validate(directories[0] / (path.stem + ".out"))
            _, again = validate(directories[1] / (path.stem + ".out"))
            assert raw == again
            last = case["history"][-1]["rates"]
            medians = [row["q"][2] for row in rows]
            fell = sum(m < r for m, r in zip(medians, last))
            rose = sum(m > r for m, r in zip(medians, last))
            universal = [row for row, r in zip(rows, last) if r == 100]
            assert all(row["q"] == [100] * 5 for row in universal)
            assert sum(medians) < sum(last)
            print(f"{path.stem}: median_sum={sum(medians):.4f} last_sum={sum(last):.4f} fell={fell} rose={rose} unchanged={55-fell-rose}; bytes={len(raw)}; deterministic=PASS; format=PASS")
            print("100% trophy:", json.dumps(universal, separators=(",", ":")))


if __name__ == "__main__":
    main()
