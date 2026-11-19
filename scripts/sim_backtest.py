"""Twenty reproducible cohort worlds; all generated cases stay in a temp dir.

This is a model-based stress test, not a measurement on real future rates.
The simulator never imports the entry's forecasting or classification code.
"""

import argparse
import copy
import json
import math
import os
from pathlib import Path
import random
import statistics
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

from score_local import logit, score

ROOT = Path(__file__).resolve().parents[1]
EPOCH = datetime(2026, 11, 19, tzinfo=timezone.utc)
Z_SCORES = (-1.645, -0.674, 0, 0.674, 1.645)


def stamp(hours):
    return (EPOCH + timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


def kind(trophy, rate):
    text = trophy["description"].lower()
    if rate >= 99.5:
        return "universal", 1.0
    if trophy["tier"] in ("gold", "platinum"):
        return "grind", 0.02
    if trophy["tier"] == "silver":
        return "grind", 0.10
    if "chapter 1" in text or "opening" in text or "complete the first" in text:
        return "story", 0.70
    if any(word in text for word in ("collect", "stunt", "races", "locations", "vehicles", "challenges")):
        return "grind", 0.05
    return "story", 0.25


def simulate(template, seed):
    rng = random.Random(71000 + seed)
    types = [kind(t, r) for t, r in zip(template["trophies"], template["history"][0]["rates"])]
    rates = [min(100, r * rng.uniform(0.8, 1.2)) if r < 99.5 else 100 for r in template["history"][0]["rates"]]
    players = 638
    history = []
    refresh = rng.uniform(2.8, 3.2)
    refresh_index = 0
    speed = rng.uniform(0.85, 1.15)
    # The very same transition loop spans both observed and forecast periods.
    for tick in range(6 * 156 + 1):
        hour = tick / 6
        if hour >= refresh:
            jump = rng.uniform(5.8, 6.3) if refresh_index == 0 else max(1.05, 1 + 0.30 * math.exp(-0.19 * (refresh_index - 1)))
            next_players = round(players * jump)
            new_players = next_players - players
            updated = []
            for rate, (category, kappa) in zip(rates, types):
                if category == "universal":
                    updated.append(100.0)
                    continue
                progress = (0.03 if category == "story" else 0.005) * speed
                old_earners = players * (rate + progress * (100 - rate)) / 100
                joining_earners = new_players * kappa * rate / 100
                updated.append(100 * (old_earners + joining_earners) / next_players)
            rates = updated
            players = next_players
            refresh_index += 1
            refresh += rng.uniform(2.8, 3.2)
        printed = [round(rate, 2) for rate in rates]
        if hour < 48:
            history.append({"slot": stamp(hour), "at": stamp(hour), "players_tracked": players,
                            "trophies_earned": round(sum(rates) * players / 100), "rates": printed})
    case = copy.deepcopy(template)
    case.update(id=f"world{seed:02d}", at=stamp(48), target=stamp(156), horizon_minutes=6480, history=history)
    return case, printed


def execute(program, source, destination):
    env = dict(os.environ, MAKEFUN_INPUT_DIR=str(source), MAKEFUN_OUTPUT_DIR=str(destination))
    subprocess.run([sys.executable, "-P", "-s", str(program)], env=env, check=True, timeout=8)


def curve_forecast(case):
    # Independent implementation of the published last-24h house curve,
    # including repeated reads; this is a local approximation, not house code.
    reads = [r for r in case["history"] if datetime.fromisoformat(r["at"].replace("Z", "+00:00")) >= EPOCH + timedelta(hours=24)]
    xs = [math.log1p((datetime.fromisoformat(r["at"].replace("Z", "+00:00")) - EPOCH).total_seconds() / 3600) for r in reads]
    xm = statistics.fmean(xs)
    variance = sum((x - xm) ** 2 for x in xs)
    rows = []
    for i, trophy in enumerate(case["trophies"]):
        ys = [logit(r["rates"][i]) for r in reads]
        ym = statistics.fmean(ys)
        slope = sum((x - xm) * (y - ym) for x, y in zip(xs, ys)) / variance
        center = ym + slope * (math.log1p(156) - xm)
        residual = statistics.pstdev([y - ym - slope * (x - xm) for x, y in zip(xs, ys)])
        spread = math.sqrt(0.25 * 4.5 + residual ** 2)
        quantiles = [100 / (1 + math.exp(-max(-700, min(700, center + z * spread)))) for z in Z_SCORES]
        rows.append({"id": trophy["id"], "q": quantiles})
    return {"trophies": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kit", type=Path, required=True)
    args = parser.parse_args()
    template = json.loads((args.kit / "input/p00.in").read_text())
    losses = [[], [], []]
    print("world  entry_loss  starter_loss  curve_loss")
    with tempfile.TemporaryDirectory(prefix="trophy-worlds-") as temp:
        base = Path(temp)
        for seed in range(20):
            source = base / str(seed) / "input"
            source.mkdir(parents=True)
            case, truth = simulate(template, seed)
            case_id = case["id"]
            (source / (case_id + ".in")).write_text(json.dumps(case))
            entry, starter, curve = [source.parent / name for name in ("entry", "starter", "curve")]
            execute(ROOT / "main.py", source, entry)
            execute(args.kit / "starter/main.py", source, starter)
            curve.mkdir()
            (curve / (case_id + ".out")).write_text(json.dumps(curve_forecast(case)))
            measured = [score({case_id: truth}, folder)["loss"] for folder in (entry, starter, curve)]
            for series, value in zip(losses, measured):
                series.append(value)
            print(f"{seed:02d}     " + "    ".join(f"{value:.6f}" for value in measured))
    means = [statistics.fmean(series) for series in losses]
    wins = sum(a < b for a, b in zip(losses[0], losses[1]))
    curve_wins = sum(a < b for a, b in zip(losses[0], losses[2]))
    print("mean   " + "    ".join(f"{value:.6f}" for value in means))
    print(f"Improvement over starter: {100 * (1 - means[0] / means[1]):.2f}%; wins {wins}/20")
    print(f"Improvement over curve approximation: {100 * (1 - means[0] / means[2]):.2f}%; wins {curve_wins}/20")
    assert means[0] <= 0.75 * means[1] and wins >= 16, "Synthetic acceptance threshold failed"


if __name__ == "__main__":
    main()
