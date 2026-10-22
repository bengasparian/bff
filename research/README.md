# BFF research: the accuracy tests

These scripts reproduce every accuracy number BFF publishes about itself. They are not part of the site and the
workflows never run them. Run them from the repository folder after `python fetch_data.py` (which downloads the
2021-2025 data they need). The first run also downloads the FantasyPros ranking archive kept by DynastyProcess
(`db_fpecr.parquet`, about 40 MB) into this folder.

Every test is out of sample: each season (2023, 2024, 2025) is predicted by models trained only on earlier seasons,
using only what was known before each game.

| Script | What it tests | Time |
| --- | --- | --- |
| `bt_weekly.py` | Weekly projections vs the FantasyPros weekly expert consensus on the same player-games (46 weeks, about 13,000 player-games); the expert weight chosen leaving one season out; the hand-set constants (games of last season used for shrinking, games of league average in the matchup factor, which model) | about 10 minutes |
| `bt_value_build.py` then `bt_value_eval.py` | Rest-of-season trade values (BFF value) vs the FantasyPros rest-of-season consensus, at 15 checkpoints (weeks 4, 6, 8, 10, 12 of 2023-2025), scored against 10 simulated 12-team leagues per checkpoint; the spread, expert weight and waiver-wire share | about 20 minutes |

```
python research/bt_weekly.py          # writes research/results_weekly.json
python research/bt_value_build.py     # writes research/value_checkpoints.pkl
python research/bt_value_eval.py      # writes research/results_value.json
```

## Results (October 2026)

Weekly projections, 2023-2025 (rank accuracy = mean weekly Spearman correlation by position; pairs = how often the
higher-ranked of two start/sit-relevant players at a position really scored more):

| | Rank accuracy | Pairs | Average miss (PPR) |
| --- | --- | --- | --- |
| Season average, shrunk (baseline) | 0.572 | 59.9% | 4.79 |
| BFF model alone | 0.601 | 60.5% | 4.61 |
| FantasyPros experts alone | 0.631 | 62.1% | 4.51 (on BFF's scale) |
| BFF projection (85% experts) | 0.633 | 62.2% | 4.51 |

Rest-of-season value, 15 checkpoints:

| | Rank accuracy | Lopsided trades called right | R² |
| --- | --- | --- | --- |
| FantasyPros experts alone | 0.429 | 69.8% | 0.218 |
| BFF model alone | 0.387 | 67.2% | 0.184 |
| BFF value with the old spread (0.2 x R) | 0.421 | 69.5% | 0.218 |
| BFF value (spread 0.5 x R) | 0.446 | 73.2% | 0.241 |

Lopsided trades are random pairs of players (4,000 draws per checkpoint) whose values are at least 2x apart; the
percentage pools every such pair. By season, BFF value vs the experts: 2023 73.1% vs 72.1%, 2024 77.2% vs 69.9%, 2025
69.5% vs 67.3%. BFF value called more of them right than the experts at 10 of the 15 checkpoints and than the old
spread at 12 of 15 (`dir_beats_experts` and `dir_beats_old_spread` in `results_value.json`).

Small differences in the last digit are expected if the data files have been updated since (nflverse corrects stats
now and then).
