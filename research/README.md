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
| `bt_weekly_v5.py` | Weekly projections (version 5) vs the FantasyPros weekly expert consensus, 2021-2026, on the same player-games (about 24,000); the expert weight; the must-start calls | about 40 minutes |
| `bt_value_build.py` then `bt_value_eval.py` | The rest-of-season value formula (spread, expert weight, waiver-wire share) at 15 checkpoints (weeks 4, 6, 8, 10, 12 of 2023-2025), scored against 10 simulated 12-team leagues per checkpoint | about 20 minutes |
| `bt_value_v5.py` | The same checkpoints and truth with the version 5 projections | about 40 minutes (`--reuse` re-scores in a few) |
| `bt_weekly.py` | The previous model (version 4), kept for comparison | about 10 minutes |
| `brain/` | How Ask BFF's own model (BFF Brain) is trained: `corpus.py` (training questions), `train.py` (the classifier, writes brain.json), `kb.py` and `kb_export.py` (the football knowledge base, writes kb.json) | about 2 minutes |

```
python research/bt_weekly_v5.py       # writes research/results_weekly_v5.json
python research/bt_value_build.py     # writes research/value_checkpoints.pkl
python research/bt_value_eval.py      # writes research/results_value.json and value_truth.pkl
python research/bt_value_v5.py        # writes research/results_value_v5.json
```

## Results (October 2026)

### Weekly projections

Rank accuracy = mean weekly Spearman correlation between the projection and the points scored, by position (1 =
perfect order). Pairs = among start/sit-relevant players (consensus top 24 QB, 40 RB, 50 WR, 20 TE), how often the
higher-ranked of two really scored more. The expert weight (60% experts, 40% BFF's model, mixed by z-scores) was chosen
on 2021-22; 2023 onward is a clean test.

| 2023-2025 (13,120 player-games) | Rank accuracy | Pairs | Average miss (PPR) |
| --- | --- | --- | --- |
| Season average, shrunk (baseline) | 0.572 | 59.9% | 4.79 |
| BFF model alone | 0.622 | 61.6% | 4.58 |
| FantasyPros experts alone | 0.631 | 62.1% | 4.55 (on BFF's scale) |
| **BFF projection** | **0.635** | **62.2%** | **4.53** |

| Season | Experts | BFF projection | BFF model alone |
| --- | --- | --- | --- |
| 2021 | 0.581 | 0.589 | 0.575 |
| 2022 | 0.614 | 0.619 | 0.605 |
| 2023 | 0.629 | 0.630 | 0.614 |
| 2024 | 0.616 | 0.623 | 0.612 |
| 2025 | 0.647 | 0.651 | 0.638 |
| 2026 (weeks 1-6) | 0.633 | 0.637 | 0.633 |

By position, 2023-2025: QB 0.489 vs experts 0.485, RB 0.734 vs 0.728, WR 0.685 vs 0.682, TE 0.633 vs 0.630. The BFF
projection ranks better than the experts in every season and at every position; the margin is small (about 0.004),
which is what beating a consensus of 100+ experts looks like. BFF's own model has closed most of the gap to the experts
(0.030 behind with version 4, 0.010 behind with version 5, level in 2026).

Must-start calls, 2023-2025 (each week's top 10 at each position by the projection; a hit finishes as a starter: top 12
QB, 24 RB, 30 WR, 12 TE): BFF projection 66.5%, FantasyPros experts 66.4%, BFF model alone 64.8%, season average 63.6%.

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
