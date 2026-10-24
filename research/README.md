# BFF research: the accuracy tests

These scripts reproduce every accuracy number BFF publishes about itself. They are not part of the site and the
workflows never run them. Run them from the repository folder. The first run downloads what it needs: the nflverse
data files for 2012-2026 (about 350 MB) and the FantasyPros ranking archive kept by DynastyProcess
(`db_fpecr.parquet`, about 40 MB) into this folder.

Every test is out of sample: each season is predicted by models trained only on earlier seasons, using only what was
known before each game. The version 5 scripts use the site's own code (`ff_feat.py` builds the inputs, `ff_model.py`
the model), so what is tested is what the site runs.

| Script | What it tests | Time |
| --- | --- | --- |
| `bt_weekly_v5.py` | Weekly projections (version 5) vs the FantasyPros weekly expert consensus, 2021-2026, on the same player-games (about 24,000); the expert weight; the must-start calls. With `BT_FROM=2020 BT_SAVE=1` it also saves `h_weekly_v5.parquet` for the next script | about 40 minutes |
| `bt_sites.py` | The weekly stack BFF publishes (its model + the experts + ESPN + Sleeper) head to head with ESPN, Sleeper and the experts on the same player-games, 2020-2026; the stack weights (chosen on 2020-22); by position; hindsight bounds on how much room any projection has (`--ceiling` adds the perfect-usage bound) | about 5 minutes (10 with `--ceiling`) |
| `bt_lines.py` | Predicted prop lines against real posted week-7 2026 lines (before and after setting them from ESPN's and Sleeper's stat projections), over rates in 2025, and the picks against lines built that way. Data in `props/` | seconds |
| `bt_fillin.py` | Fill-ins (backups who took a hurt starter's snaps) and returning starters: BFF's model vs what happened once the starter was back, 2020-25; the scaling the site uses | seconds |
| `bt_commonsense.py` | Buy-low and sell-high calls with and without the common-sense checks (fill-ins, two games, falling snaps, top-6 usage), 2020-25 | seconds |
| `hist_fetch.py` | Fetches ESPN's and Sleeper's past weekly projections into `hist/` (run on GitHub Actions or anywhere those sites are reachable; already done, the files are here) | about 15 minutes |
| `bt_value_build.py` then `bt_value_eval.py` | The rest-of-season value formula (spread, expert weight, waiver-wire share) at 15 checkpoints (weeks 4, 6, 8, 10, 12 of 2023-2025), scored against 10 simulated 12-team leagues per checkpoint | about 20 minutes |
| `bt_value_v5.py` | The same checkpoints and truth with the version 5 projections | about 40 minutes (`--reuse` re-scores in a few) |
| `bt_weekly.py` | The previous model (version 4), kept for comparison | about 10 minutes |
| `brain/` | How Ask BFF's own model (BFF Brain) is trained: `corpus.py` (training questions), `train.py` (the classifier, writes brain.json), `voice.py` (how it talks: Ben's voice, shipped inside brain.json), `kb.py` and `kb_export.py` (the football knowledge base, writes kb.json) | about 2 minutes |

```
python research/bt_weekly_v5.py       # writes research/results_weekly_v5.json
BT_FROM=2020 BT_SAVE=1 python research/bt_weekly_v5.py && python research/bt_sites.py --ceiling   # writes research/results_sites.json
python research/bt_value_build.py     # writes research/value_checkpoints.pkl
python research/bt_value_eval.py      # writes research/results_value.json and value_truth.pkl
python research/bt_value_v5.py        # writes research/results_value_v5.json
```

## Results (October 2026)

### Weekly projections

Rank accuracy = mean weekly Spearman correlation between the projection and the points scored, by position (1 =
perfect order). Pairs = among start/sit-relevant players (consensus top 24 QB, 40 RB, 50 WR, 20 TE), how often the
higher-ranked of two really scored more. Average miss = mean absolute error in PPR points.

**What BFF publishes now: a stack of four forecasts** (`bt_sites.py`, the same rule as `ff_produce.py`). Within each
position and week, every forecast becomes a z-score among the players the experts ranked: BFF's model 30%, the
FantasyPros weekly expert rank 10%, Sleeper 30%, ESPN 30%, re-weighted over the forecasts a player has. The k-th
strongest player gets the k-th highest of the players' average projected points (BFF, Sleeper, ESPN). The weights are
the best of every 10% split on 2020-22 (0.563; next best 0.563 and 0.563, so the choice is flat near the top); 2023
onward is a clean test.

Head to head, on the player-games every source projected (ESPN re-scored to full PPR from its projected stats):

| 2023-2025 (11,636 player-games) | Rank accuracy | Pairs | Average miss (PPR) |
| --- | --- | --- | --- |
| FantasyPros experts | 0.565 | 62.1% | 4.80 (on BFF's scale) |
| ESPN | 0.565 | 62.3% | 4.75 |
| Sleeper | 0.561 | 62.1% | 4.86 |
| BFF model alone | 0.556 | 61.6% | 4.82 |
| BFF previous mix (40% model, 60% experts) | 0.570 | 62.3% | 4.79 |
| **BFF stack** | **0.577** | **62.7%** | **4.71** |

2026 weeks 1-6 (1,631 player-games): experts 0.552 / 63.8%, ESPN 0.554 / 63.4% / 4.81, Sleeper 0.560 / 63.6% / 4.81,
BFF model 0.550 / 63.8% / 4.86, **BFF stack 0.574 / 64.1% / 4.76**. 2020-22 (where the weights were chosen): stack
0.563, best other (Sleeper) 0.551. By position, 2023-25, stack vs the best other source: QB 0.381 vs 0.369 (experts),
RB 0.684 vs 0.680 (Sleeper), WR 0.643 vs 0.638 (ESPN), TE 0.601 vs 0.594 (experts); 2026: QB 0.390 vs 0.366, RB 0.698
vs 0.691, WR 0.650 vs 0.644, TE 0.556 vs 0.554. With one site missing (2023-26, all ranked players) the stack still
beats the previous mix: without ESPN 0.638, without Sleeper 0.639, previous mix 0.635.

Every player the experts ranked who played (some lack an ESPN or Sleeper projection; the stack uses what he has):

| 2023-2025 (13,119 player-games) | Rank accuracy | Pairs | Average miss (PPR) |
| --- | --- | --- | --- |
| Season average, shrunk (baseline) | 0.569 | 59.8% | 4.79 |
| BFF model alone | 0.622 | 61.6% | 4.58 |
| FantasyPros experts alone | 0.631 | 62.1% | 4.55 (on BFF's scale) |
| BFF previous mix | 0.635 | 62.2% | 4.53 |
| **BFF stack** | **0.641** | **62.7%** | **4.46** |

| Season | Experts | BFF stack | BFF previous mix | BFF model alone |
| --- | --- | --- | --- | --- |
| 2021 (weights chosen on 2020-22) | 0.581 | 0.597 | 0.589 | 0.575 |
| 2022 (weights chosen on 2020-22) | 0.614 | 0.622 | 0.619 | 0.605 |
| 2023 | 0.629 | 0.634 | 0.630 | 0.614 |
| 2024 | 0.615 | 0.638 | 0.623 | 0.611 |
| 2025 | 0.647 | 0.651 | 0.651 | 0.638 |
| 2026 (weeks 1-6) | 0.631 | 0.648 | 0.636 | 0.631 |

Must-start calls, 2023-2025 (each week's top 10 at each position; a hit finishes as a starter: top 12 QB, 24 RB, 30
WR, 12 TE): BFF stack 66.2%, previous mix 66.5%, FantasyPros experts 66.4%, BFF model alone 64.8%, season average
63.6%. These differ by less than their noise (about 1,840 calls, so about 1.1 points either way).

**Can any projection be 10% more accurate than the best site? No, and here is the evidence** (2023-25, the same
player-games):

- Re-weighting is used up: weights picked on the 2023-25 answers themselves reach 0.578; the stack (weights from
  2020-22) has 0.577. Ridge regression, gradient-boosted trees (with expert disagreement, roster share, games played)
  and per-position weights as the stacker all did the same or worse (0.549-0.577).
- The sources agree with each other at 0.90-0.94 rank correlation (ESPN~Sleeper 0.921, model~ESPN 0.905, experts~model
  0.935), so most of their misses are the same misses.
- Hindsight: ranking each player by his real average in all his other games that season, future games included,
  scores 0.531 with a 4.92-point miss; ESPN's pre-game projection scores 0.561 and 4.75 on the same games. Knowing the
  future season average does not beat the sites.
- Only knowing each player's usage in that very game (expected points from his real targets and carries and where
  they came) reaches 0.718 (pairs 75.3%). A 10% lead over the best site (0.565) would need 0.622: more than a third of
  the way from today's best sites to that clairvoyant mark, with nothing more than pre-game information.

The version 5 model alone (`bt_weekly_v5.py`) has closed most of its gap to the experts (0.030 behind with version 4,
0.010 behind with version 5, level in 2026).

### Prop lines (`bt_lines.py`)

Real week-7 2026 lines for passing, receiving and rushing yards were read from a public props page (122 matched players;
`props/real_lines_2026_w7.json`). Average gap to the real line, each new line scored on players the fit did not use:

| Stat | Before (opportunity model) | Now (ESPN + Sleeper, scaled) | Scale |
| --- | --- | --- | --- |
| Passing yards | 13.3 (15 lines) | 9.6 (17) | 0.989 |
| Receiving yards | 6.9 (49) | 3.4 (57) | 0.919 |
| Rushing yards | 9.1 (31) | 5.5 (48) | 0.862 |

The old lines aimed at the typical outcome and squeezed players toward the middle; the public projections, scaled to
where books set lines, follow the real lines far more closely (correlation 0.91, 0.98 and 0.97 for the average of ESPN
and Sleeper, against 0.81, 0.93 and 0.81 for the old lines). In 2025, overs at lines built this way hit 46% (passing),
43% (receiving), 46% (rushing) and 46% (receptions, scale 0.95), about what real prop overs do. Picks: unders when BFF's
own model is at least 10% below ESPN and Sleeper hit 57.2% of 1,511 (every yardage under: 55.1%; overs where BFF was
higher: 48.5%). These used lines built from ESPN and Sleeper, not real book lines.

### Common sense: fill-ins, buy low and sell high (`bt_fillin.py`, `bt_commonsense.py`)

`python research/bt_fillin.py` (writes `results_fillin.json`, a few seconds). A **fill-in** took a starter's snaps (40%+,
and 15+ points more than beside the starter) while the starter (.55+ snap share for RBs, .70+ for WRs/TEs in his best 2 of his last 3
games) missed 1-6 games, and ranks below him (fewer targets + carries together, or, never together, fewer in the games he
filled than the starter's best 2). For the starter's return week and the 3 after (2020-25 regular seasons), BFF's weekly
model against what happened:

| | Fit 2020-22 | Check 2023-25 |
|---|---|---|
| Fill-ins: actual / projected (RB, WR, TE) | 0.74, 0.83, 0.84 | 0.85, 0.76, 0.58 |
| Fill-ins over-projected | 72% (521 games) | 74% (379 games) |
| Returning starters: actual / projected | 1.00 (558) | 1.04 (386) |

Scaling fill-ins by the 2020-22 ratios on 2023-25: average miss 3.82 -> 3.44 points, bias +1.37 -> +0.13. The site uses
the ratios pooled over all six seasons (RB 0.786, WR 0.803, TE 0.754), weighted by the chance the starter plays each week.

`python research/bt_commonsense.py` (writes `results_commonsense.json`). Buy-low calls (usage 8+ a game, scoring 2.5+
below it) and sell-high calls (10+ a game, 3+ above usage) in weeks 4-13, judged on the rest of the season against the
player's average so far:

| | Calls | Right | Points a game after vs before |
|---|---|---|---|
| Buy low, every call | 496 | 60% | +1.12 |
| Buy low, fill-in whose starter is back | 11 | 27% | -1.49 |
| Buy low, two games played | 34 | 56% | +0.98 |
| Buy low, snaps falling (last 2 under 75% of season) | 19 | 37% | -0.59 |
| Buy low, usage already top 6 at his position | 114 | 40% | -1.11 |
| Buy low, after all four checks | 327 | 69% | +1.96 |
| Buy low, returning starter | 50 | 72% | +2.73 |
| Fill-in scoring 8+ once his starter is back (a sell) | 148 | 68% | -1.67 |
| Sell high, every call | 1,240 | 75% | -3.08 |
| Sell high, top-6 usage (stud) | 312 | 80% | -4.17 (still 17.9 a game after) |

### Rest-of-season value (BFF value)

15 checkpoints; every source is put on the same value curve so only the order of players differs. Truth = what each
player added to his team over the rest of the season in simulated leagues, with lineups set by the previous
projections (so the test does not favor the new model).

| | Rank accuracy | Lopsided trades called right | R² |
| --- | --- | --- | --- |
| BFF model alone (no experts) | 0.432 | 72.0% | 0.225 |
| BFF value with the previous projections | 0.446 | 73.2% | 0.241 |
| FantasyPros experts alone (same value curve) | 0.448 | 73.4% | 0.257 |
| **BFF value** | **0.454** | **73.5%** | **0.259** |

By season, BFF value vs the experts (rank accuracy): 2023 0.468 vs 0.460, 2024 0.518 vs 0.504, 2025 0.376 vs 0.380.
Lopsided trades are random pairs of players (4,000 draws per checkpoint) whose values are at least 2x apart. With
lineups set by the new projections instead: BFF value 0.448 / 72.5% / 0.293, experts 0.440 / 72.5% / 0.290. In short,
BFF value orders players a little better than the experts in two of three seasons and overall, and calls lopsided
trades as well as they do.

**Correction (October 2026).** An earlier version of this page compared BFF value (0.446, 73.2%) with the experts
mapped onto the old value curve (0.429, 69.8%). On the same curve the experts score 0.448 and 73.4%, so the old formula
was level with the experts, not ahead. The numbers above are the fair comparison.

Small differences in the last digit are expected if the data files have been updated since (nflverse corrects stats
now and then).
