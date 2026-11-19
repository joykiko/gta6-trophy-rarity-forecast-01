"""Cohort-Dilution Logit-Growth Trophy Forecaster.
Read each supplied case and emit five ordered percentage quantiles.
Repeated unchanged pages are collapsed before fitting any curve.
Time is log one plus hours since the release epoch.
Each trophy receives an ordinary least-squares logit trend.
Tier averages stabilize slopes with three pseudo-observations.
Future log-time movement is damped to limit launch-curve overshoot.
Separate players and earners curves cross-check extrapolation.
A large disagreement moves the trend one quarter toward that check.
Flat short histories instead receive a cohort-dilution refresh prior.
Trophy descriptions and tiers determine new-cohort holding rates.
Residual noise and forecast horizon determine logit uncertainty.
All computation is offline, deterministic, and standard library only.
"""

import json
import math
import os
import re
import statistics
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

RELEASE = datetime(2026, 11, 19, tzinfo=timezone.utc)
NORMAL_SCORES = (-1.645, -0.674, 0.0, 0.674, 1.645)
TREND_PROJECTION = 0.40
FITTED_SPREAD_SCALE = 0.85


def bounded(rate):
    return max(0.01, min(float(rate), 99.99))


def odds_log(rate):
    value = bounded(rate)
    return math.log(value) - math.log(100.0 - value)


def percentage(value):
    # The two forms keep extreme but finite extrapolations numerically safe.
    if value >= 0:
        return 100.0 / (1.0 + math.exp(-value))
    e = math.exp(value)
    return 100.0 * e / (1.0 + e)


def clock_value(iso):
    hours = (datetime.fromisoformat(iso.replace("Z", "+00:00")) - RELEASE).total_seconds() / 3600
    return math.log1p(max(hours, -0.999999))


def line_fit(pairs):
    if not pairs:
        return odds_log(0.01), 0.0
    cx = statistics.fmean(x for x, _ in pairs)
    cy = statistics.fmean(y for _, y in pairs)
    denominator = math.fsum((x - cx) ** 2 for x, _ in pairs)
    slope = math.fsum((x - cx) * (y - cy) for x, y in pairs) / denominator if denominator else 0.0
    return cy - slope * cx, slope


def distinct_reads(history):
    result = []
    for read in history:
        if not result or (read["players_tracked"], read["rates"]) != (result[-1]["players_tracked"], result[-1]["rates"]):
            result.append(read)
    return result


def cohort_fraction(trophy, last_rate):
    if last_rate >= 99.5:
        return 1.0
    tier = trophy.get("tier") or {300: "platinum", 90: "gold", 30: "silver", 15: "bronze"}.get(trophy.get("points"), "bronze")
    if tier in ("gold", "platinum"):
        return 0.02
    if tier == "silver":
        return 0.10
    description = trophy.get("description", "").casefold()
    if re.search(r"\bchapter\s+1\b|\bopening\b|\bcomplete the first\b", description):
        return 0.70
    counts = re.findall(r"\b(?:collect|win|complete)\s+(\d+)\b", description)
    if any(int(count) >= 20 for count in counts) or re.search(r"stunt|races|locations|vehicles|challenges", description):
        return 0.05
    # Secret bronzes usually represent story beats; unspecified bronze kinds
    # share the same conservative story prior rather than an invented tier.
    if trophy.get("secret", False):
        return 0.25
    return 0.25


def rounded_rate(value):
    return float(Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def predict(case):
    reads = distinct_reads(case["history"])
    if not reads:
        raise ValueError("A forecast requires at least one historical read")
    trophies = case["trophies"]
    last_rates = []
    observed = []
    for index in range(len(trophies)):
        values = [(clock_value(r["at"]), r["rates"][index], r["players_tracked"]) for r in reads if r["rates"][index] is not None]
        observed.append(values)
        last_rates.append(values[-1][1] if values else 0.01)
    target_x = clock_value(case["target"])
    horizon_days = max(0.0, case["horizon_minutes"] / 1440)
    fits = [line_fit([(x, odds_log(rate)) for x, rate, _ in values]) for values in observed]
    tier_slopes = {}
    for trophy, (_, slope) in zip(trophies, fits):
        tier_slopes.setdefault(trophy["tier"], []).append(slope)
    tier_slopes = {tier: statistics.fmean(slopes) for tier, slopes in tier_slopes.items()}
    player_a, player_b = line_fit([(clock_value(r["at"]), math.log(max(1, r["players_tracked"]))) for r in reads])
    predicted_log_players = player_a + player_b * target_x
    rows = []
    for index, trophy in enumerate(trophies):
        last = last_rates[index]
        if last == 100 or (len(reads) < 3 and last >= 99.5):
            quantiles = [100] * 5
        else:
            values = observed[index]
            if len(reads) >= 3:
                a, b = fits[index]
                n = len(values)
                shrunk = (n * b + 3 * tier_slopes[trophy["tier"]]) / (n + 3) if n else 0.0
                # First backtest: 0.379163 loss, with story medians overshooting.
                # Damping extrapolation and scaling spread gave 0.272347 on
                # the same 20 synthetic worlds; this is simulator calibration.
                last_x = clock_value(reads[-1]["at"])
                projection_x = last_x + TREND_PROJECTION * (target_x - last_x)
                median_logit = a + shrunk * projection_x
                if values:
                    ea, eb = line_fit([(x, math.log(rate * players / 100 + 0.5)) for x, rate, players in values])
                    log_ratio = ea + eb * target_x - predicted_log_players
                    ep = bounded(100 * math.exp(min(700.0, log_ratio)))
                    check = odds_log(ep)
                    if abs(check - median_logit) > 1.0:
                        median_logit += 0.25 * (check - median_logit)
                residuals = [odds_log(rate) - (a + b * x) for x, rate, _ in values]
                residual_spread = statistics.stdev(residuals) if n >= 3 else 0.0
                median = bounded(percentage(median_logit))
            else:
                # Published totals: 3868/638 = 6.0626959 (~6.06), 3230 new
                # players; 943/638 = 1.4781 initial trophies/player versus
                # (4276-943)/3230 = 1.0319 per joiner (an upper bound, since
                # existing holders can progress): the new cohort holds less.
                players = reads[-1]["players_tracked"]
                future_players = 6.06 * players
                holder_rate = cohort_fraction(trophy, last) * last
                median = bounded((players * last + (future_players - players) * holder_rate) / future_players)
                residual_spread = 0.6
            spread = min(2.5, max(0.4, math.sqrt(0.35 ** 2 + 0.25 * horizon_days + residual_spread ** 2)))
            if len(reads) >= 3:
                spread = max(0.4, spread * FITTED_SPREAD_SCALE)
            center = odds_log(median)
            quantiles = []
            for z in NORMAL_SCORES:
                value = rounded_rate(bounded(percentage(center + z * spread)))
                quantiles.append(max(quantiles[-1] if quantiles else 0, value))
        rows.append({"id": trophy["id"], "q": quantiles})
    return {"trophies": sorted(rows, key=lambda row: row["id"])}


def run():
    source = Path(os.getenv("MAKEFUN_INPUT_DIR", "/input"))
    destination = Path(os.getenv("MAKEFUN_OUTPUT_DIR", "/output"))
    destination.mkdir(parents=True, exist_ok=True)
    for case_path in sorted(source.glob("*.in")):
        case = json.loads(case_path.read_bytes())
        payload = json.dumps(predict(case), separators=(",", ":"), allow_nan=False) + "\n"
        (destination / (case_path.stem + ".out")).write_text(payload, encoding="utf-8")


if __name__ == "__main__":
    run()
