# Cohort-Dilution Logit-Growth Trophy Forecaster

[![make.fun · gta6-trophy-rarity-forecast-01](https://make.fun/badge/gta6-trophy-rarity-forecast-01.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![rank](https://make.fun/badge/gta6-trophy-rarity-forecast-01/joykiko/gta6-trophy-rarity-forecast-01/rank.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![reward](https://make.fun/badge/gta6-trophy-rarity-forecast-01/joykiko/gta6-trophy-rarity-forecast-01/reward.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)

An offline, standard-library Python forecaster for the earn rates of all 55 GTA VI PlayStation 5 trophies on Exophase. It emits the 5%, 25%, 50%, 75% and 95% quantiles at each case's target. The competition's final target is 2026-11-26T00:00:00Z; its checkpoint is 2026-11-21T11:30:00Z, 6,510 minutes earlier.

## Run

```sh
MAKEFUN_INPUT_DIR=/path/to/input MAKEFUN_OUTPUT_DIR=/path/to/output python3 main.py
```

The defaults are `/input` and `/output`. Every `*.in` is processed in filename order, producing the matching `<id>.out`. The grader invokes `python3 -P -s /bot/main.py` under Python 3.13. No dependencies, installation, network, or adjacent Python modules are required. Local measurements below used Python 3.12.3; Python 3.13 was not installed on the build machine.

## Model

Consecutive reads with identical player counts and rates become one snapshot, retaining its first timestamp. Time is `ln(1 + hours since 2026-11-19T00:00:00Z)`; early pre-release reads remain valid. Null observations are excluded per trophy, with 0.01% as the fallback when every observation is null.

With at least three distinct snapshots (Case A), an ordinary least-squares line fits each trophy's logit rate. Three pseudo-observations shrink its slope toward the mean raw slope for its tier. The earners/players decomposition supplies a second view: independent log-player and log-earner regressions project the denominator and numerator, using `earners + 0.5` for zeros. A disagreement exceeding one logit moves the trend median 25% toward that ratio forecast.

The first validation exposed long-horizon overshoot. The revised model retains the fitted history but projects only 40% of the future log-time movement beyond the last distinct snapshot. This is an explicit change from the initial undamped design, selected in-session on the synthetic worlds below. The earners/players cross-check still projects to the actual target.

With fewer than three distinct snapshots (Case B), a refresh prior replaces curve fitting. The rules publish 638 initial players and 943 trophies earned, then 3,868 players and 4,276 trophies earned. The player multiplier is `3868 / 638 = 6.062696`, approximated by 6.06 in the forecast. There are 3,230 new players: the initial average is 1.478056 trophies/player, while the increase in trophies per new player is at most 1.031889, because existing players can also progress. This supports expecting dilution.

New holders have a fraction kappa of the previous holding rate: 1.0 for the universal trophy, 0.70 for early-story bronze, 0.25 for other story/default bronze, 0.10 for silver, 0.05 for counter/collection/grind bronze, and 0.02 for gold/platinum. Classification uses trophy metadata and description patterns, including Chapter 1, opening, large counters, stunts, races, locations, vehicles and challenges. Tiers take priority over bronze description rules. No practice answers or post-checkpoint rates are embedded, and there are no case-id branches.

The spread combines a 0.35 logit floor, `0.5 * sqrt(horizon_days)`, and the sample standard deviation of trend residuals (0.6 in Case B). It is bounded to 0.4–2.5. Validation calibrated a 0.85 multiplier for Case A, with the 0.4 lower bound retained; Case B is unchanged. Thus uncertainty still widens with horizon and fit residual, aiming for an honest 90% band rather than padding it. The simulator does not establish real-world coverage. Standard-normal offsets generate ordered quantiles, clamped to 0.01–99.99%, rounded half-up to four decimals. The universal 100% trophy stays exactly 100 in every quantile.

## Validation evidence

All checks were run in the recorded build session. `scripts/score_local.py ANSWERS.json OUTPUT_DIR` implements the rules' exact loss: `2 * max(tau*d, (tau-1)*d)`, with `d = logit(actual) - logit(forecast)` after clamping both rates to 0.01–99.99. It averages all trophy/quantile items, and also reports mean absolute median miss in points and inclusive 90% coverage. Answers use the shape `{"p00": [rates...], "p01": [rates...]}`. No actual practice answer file is shipped.

Reproduce the stress test and practice checks with an absolute kit path:

```sh
python3 scripts/sim_backtest.py --kit /path/to/kit
python3 scripts/verify_local.py --kit /path/to/kit
```

The simulation has 20 seeded worlds, reads every 10 minutes, approximately three-hour refreshes, an initial roughly 6x player jump, then jumps decaying from about 1.3x toward 1.05x. Old cohorts progress by 3% of the remaining story gap or 0.5% of the grind gap per refresh, with modest seeded variation. New cohorts use the specified kappa mechanism. Each world is cut at 48 hours; the same simulation continues to the target 4.5 days later. Cases, generated truth and forecast files are temporary and stay outside this repository. No truth is passed to the forecaster. These are calibration results on assumed worlds, not held-out estimates of final performance.

| Run / model | Mean logit pinball loss | Wins over persistence |
| --- | ---: | ---: |
| Initial entry: undamped trend, original spread | 0.379163 | 16/20 |
| Revised entry: 0.40 projection, 0.85 fitted spread | 0.272347 | 20/20 |
| Kit persistence starter | 0.404624 | — |
| Local last-24h house-curve approximation | 0.348667 | — |

The revised mean is **32.69% below the starter**, clearing the required 25% improvement and 16/20 wins. It is **21.89% below the curve approximation**, winning 16/20 against it. The actual house curve code is not in the kit; that comparison is an independent implementation of its published description, not a measured run of the sealed house entry. Stronger shrinkage alone (weights 6, 12, 24, 48) gave means 0.374223, 0.367945, 0.360728, 0.356363, missing the required margin. The final calibration tested trend projection fractions 0.25 and 0.40 and fitted spread multipliers 0.70, 0.85 and 1.00; the selected 0.40/0.85 preserves more uncertainty than the narrowest tested setting.

The untouched kit starter ran successfully on both practice cases and produced valid outputs in `/tmp/starter-out`; its outputs were not copied. After the real edit to `main.py`, practice plausibility and repeat-run checks were repeated:

| Case | Sum of last rates | Sum of forecast medians | Fell / rose / unchanged |
| --- | ---: | ---: | --- |
| p00 | 147.7800 | 116.8073 | 54 / 0 / 1 |
| p01 | 147.7800 | 116.8073 | 54 / 0 / 1 |

Both retain trophy 2 as `{"id":2,"q":[100,100,100,100,100]}`. Each output is 2,768 bytes, with exactly 55 rows, ids 1–55 in ascending order, five finite ordered quantiles in [0,100], and a trailing newline. Two runs were byte-identical. The final measured runs took 0.064744 and 0.064537 seconds for **both** practice cases, comfortably under one second per case and the eight-second cap. These timings are local, not grader timings.

The local scorer also reproduces the rules' worked example: loss 0.403404337857, typical miss 7 points, coverage 0.5. Additional checks passed for consecutive duplicate collapse and an all-null trophy in a multi-snapshot case (median 0.01%, all quantiles finite).

The kit's `check --worktree` reported every local source check passing, with only the expected missing-transcript failure. It verifies source intake rather than running the sealed scorer. Full row status:

| Check | Status |
| --- | --- |
| competition_open | pass |
| snapshot | pass: 8 files, 30,701 bytes at that check |
| license_osi | pass: MIT |
| entrypoint | pass: main.py / python3.13 |
| strategy_note | skip: not required |
| committed_secret | skip: no dotenv supplied; no credentials are shipped |
| transcripts_present | FAIL: no transcripts supplied to this local check |
| transcripts_recorded | skip: no session parsed |
| thinking_wellformed | skip: no session parsed |
| thinking_in_window | skip: no session parsed |
| thinking_committed | skip: unsigned local check |
| thinking_reproduces | skip: no session parsed |
| thinking_on_task | skip: no session parsed |
| thinking_turns | skip: no session parsed |
| thinking_priced | skip: no session parsed |
| thinking_revised | skip: no session parsed |
| thinking_fresh | skip: no session parsed |
| transcripts_run_record | skip: no session parsed |
| repo_public | checked at submission |
| repo_owner | checked at submission |
| repo_created_after_open | checked at submission |
| commit_in_repo | checked at submission |
| duplicate_snapshot | checked at submission |

Totals: 4 passed, 1 failed, 13 skipped, 5 checked at submission. The CLI warned that the supplied kit is level 26 while the site is level 27. A recorded-session bundle, run record and submission-time checks remain necessary before entering; this local check does not certify transcript eligibility. The anchor root and generated MIT license remain intact.

## Submission reasoning

The entrant's supplied dev leaderboard observation, read 19 Nov at approximately 21:00 WIB, has 2,949 entries: rank 1 loss 0.0238, rank 10 0.0776, rank 20 0.0892, rank 50 0.113, and rank 100 0.123. These figures are supplied context, not a live lookup during this offline build. The rules put the house persistence baseline at about 1.51 on practice.

The pot is $250 USDC in escrow, paying 20 places: $50/$35/$25, then $10 x7, then $7 x10. The deadline is 2026-11-21T11:30:00Z (21 Nov 18:30 WIB). Force Last means the last submission counts. The published quota is at most 10/day and 20 total; the entrant reports an effective account cap in practice of about 3. This is probe 1 of a maximum of 2 probes plus 1 final.

**Rubric to evidence.** The only score is mean pinball loss on the logit scale over 55 trophies x 5 quantiles on the FINAL case f00. Evidence: `main.py` fits each trophy's logit trend on the case's own history with tier shrinkage (Case A), now with calibrated extrapolation damping, and falls back to a refresh prior calibrated on the rules' published launch-night totals (Case B). Its spread widens with horizon and residual. Its output is deterministic: two runs were byte-identical, verified in-session, and it runs in under one second per case locally.

**Leader/baseline beaten and how.** The house persistence baseline says every rate stays put (practice about 1.51); the house curve baseline fits the logit line over only the last 24 hours, with no shrinkage and no refresh prior. This entry beats persistence and our approximation of that curve on the synthetic backtest by 32.69% and 21.89%, respectively. It uses the full distinct history, shrinks noisy slopes toward tier means, checks the trend against an earners-over-players forecast, and expects the dilution an Exophase refresh can bring. No actual dev leader, sealed house curve or house model has been shown beaten by this local test; the target is to beat the three house entries on the final.

**Honest weakness.** The supplied dev observation describes the top as dominated by entries that reproduce the practice refresh outcome almost exactly (rank 1: loss 0.0238, typical miss 0.00 points). That degree of exact reconstruction is not a signal a general forecaster can infer from the flat case histories, and it does not transfer to the final, whose answer nobody has. This probe's practice loss is expected to sit well above 0.1 and is NOT the target metric. The target is beating the three house entries on the final, where the program reads about two days of 10-minute refreshes and extrapolates them. The final answer is unknowable until 26 Nov, so no rank is promised. Synthetic assumptions and calibration on these same worlds are additional weaknesses; they can miss actual cohort dynamics.

**Quota decision.** Probe 1: submit now to lock a valid, scored entry before the deadline; iterate only if the provisional result shows the refresh prior working (practice loss clearly below the about-1.51 baseline) AND a concrete model change beats it on the synthetic backtest. Otherwise stop at one submission and keep the remaining slots. This is the intended submission strategy; the build session itself commits locally without pushing or submitting.
