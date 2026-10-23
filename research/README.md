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
| `hist_fetch.py` | Fetches ESPN's and Sleeper's past weekly projections into `hist/` (run on GitHub Actions or anywhere those sites are reachable; already done, the files are here) | about 15 minutes |
| `bt_value_build.py` then `bt_value_eval.py` | The rest-of-season value formula (spread, expert weight, waiver-wire share) at 15 checkpoints (weeks 4, 6, 8, 10, 12 of 2023-2025), scored against 10 simulated 12-team leagues per checkpoint | about 20 minutes |
| `bt_value_v5.py` | The same checkpoints and truth with the version 5 projections | about 40 minutes (`--reuse` re-scores in a few) |
| `bt_weekly.py` | The previous model (version 4), kept for comparison | about 10 minutes |
| `brain/` | How Ask BFF's own model (BFF Brain) is trained: `corpus.py` (training questions), `train.py` (the classifier, writes brain.json), `kb.py` and `kb_export.py` (the football knowledge base, writes kb.json) | about 2 minutes |

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
