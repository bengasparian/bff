"""BFF research: fetch ESPN's and Sleeper's past weekly projections (2019-2026) into research/hist/ for the head-to-head
backtest (research/bt_sites.py). Uses the same fetchers as the live tracker (proj_compare.py): ESPN's projected stats
re-scored to full PPR, and Sleeper's PPR projection. Standard library only.

Run from the repository folder where those sites are reachable (they were fetched on GitHub Actions; the files are already
in research/hist/, so this only needs running again to refresh them):
  python research/hist_fetch.py              (SEASONS="2025 2026" to fetch some seasons only)
Each file maps week -> {site player id: PPR points}."""
import json, os, sys, time, gzip
RUN = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, RUN)
from proj_compare import espn, sleeper
OUT = os.path.join(RUN, 'research', 'hist'); os.makedirs(OUT, exist_ok=True)
SEASONS = [int(x) for x in os.environ.get('SEASONS', '2019 2020 2021 2022 2023 2024 2025 2026').split()]
LAST = int(os.environ.get('LAST_WEEK', '18'))   # for the season in progress, the last week to fetch
for S in SEASONS:
    for nm, fn in (('sleeper', sleeper), ('espn', espn)):
        out = {}
        for W in range(1, 19):
            if S == max(SEASONS) and W > LAST: break
            err = ''
            for t in range(3):
                try: out[str(W)] = fn(S, W); break
                except Exception as e: err = str(e); time.sleep(3)
            else: out[str(W)] = {}; print(f'{nm} {S} week {W}: {err}')
            time.sleep(.4)
        json.dump(out, gzip.open(os.path.join(OUT, f'{nm}_{S}.json.gz'), 'wt'), separators=(',', ':'))
        print(f'{nm} {S}: ' + ' '.join(f'{w}:{len(v)}' for w, v in out.items()), flush=True)
