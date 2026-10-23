"""One-off research fetch (runs on GitHub, where these sites are reachable): Sleeper's and ESPN's public weekly
projections for past seasons, plus a sample of FFToday's weekly projection pages, saved under hist/ for BFF's
head-to-head backtest. Standard library only."""
import json, os, sys, time, gzip, urllib.request
sys.path.insert(0, '.')
from proj_compare import espn, sleeper, get_json
os.makedirs('hist', exist_ok=True)
SEASONS = [int(x) for x in os.environ.get('SEASONS', '2019 2020 2021 2022 2023 2024 2025 2026').split()]
log = []
for S in SEASONS:
    for nm, fn in (('sleeper', sleeper), ('espn', espn)):
        out = {}
        for W in range(1, 19):
            if S == 2026 and W > 7: break
            for t in range(3):
                try: out[str(W)] = fn(S, W); break
                except Exception as e: err = str(e); time.sleep(3)
            else: out[str(W)] = {}; log.append(f'{nm} {S} w{W}: {err}')
            time.sleep(.4)
        json.dump(out, gzip.open(f'hist/{nm}_{S}.json.gz', 'wt'), separators=(',', ':'))
        log.append(f'{nm} {S}: ' + ' '.join(f'{w}:{len(v)}' for w, v in out.items()))
        print(log[-1], flush=True)
# FFToday sample pages (HTML), to see their format
for S, W, pos in ((2024, 5, 10), (2024, 5, 20), (2024, 5, 30), (2024, 5, 40)):
    url = f'https://www.fftoday.com/rankings/playerwkproj.php?Season={S}&GameWeek={W}&PosID={pos}&LeagueID=107644'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=40) as r: open(f'hist/fftoday_{S}_{W}_{pos}.html', 'wb').write(r.read())
        log.append(f'fftoday sample {S} {W} {pos} ok')
    except Exception as e: log.append(f'fftoday sample {S} {W} {pos}: {e}')
open('hist/log.txt', 'w').write('\n'.join(log)); print('\n'.join(log[-6:]))
