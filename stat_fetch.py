"""One-off research fetch (runs on GitHub, where these sites are reachable): ESPN's and Sleeper's public weekly
projections stat by stat (passing, rushing and receiving yards, receptions, passing touchdowns) for 2025 and 2026, the same
public endpoints the site's projection tracker already reads. Used to test whether they predict prop lines. Saved under stats/."""
import json, os, gzip, time, urllib.request
os.makedirs('stats', exist_ok=True)
UA = {'User-Agent': 'Mozilla/5.0 (BFF projection tracker)', 'Accept': 'application/json'}
ESPN_ID = {'3': 'py', '4': 'ptd', '0': 'patt', '23': 'car', '24': 'ry', '42': 'ty', '53': 'rec', '58': 'tg'}
SL_KEY = {'pass_yd': 'py', 'pass_td': 'ptd', 'pass_att': 'patt', 'rush_att': 'car', 'rush_yd': 'ry', 'rec_yd': 'ty', 'rec': 'rec', 'rec_tgt': 'tg', 'pts_ppr': 'pts'}


def get(url, headers=None):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=40) as r: return json.loads(r.read().decode('utf-8'))


def espn(season, week):
    flt = {'players': {'limit': 1200, 'sortPercOwned': {'sortAsc': False, 'sortPriority': 1}, 'filterSlotIds': {'value': [0, 2, 4, 6]},
                       'filterStatsForTopScoringPeriodIds': {'value': 2, 'additionalValue': [f'00{season}', f'10{season}', f'11{season}{week}']}}}
    url = f'https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leaguedefaults/3?scoringPeriodId={week}&view=kona_player_info'
    out = {}
    for x in get(url, {'X-Fantasy-Filter': json.dumps(flt)}).get('players', []):
        p = x.get('player') or {}
        for s in p.get('stats') or []:
            if s.get('statSourceId') == 1 and s.get('statSplitTypeId') == 1 and s.get('scoringPeriodId') == week and s.get('seasonId') == season:
                st = s.get('stats') or {}
                out[str(p.get('id'))] = {v: round(float(st[k]), 2) for k, v in ESPN_ID.items() if k in st}
    return out


def sleeper(season, week):
    url = (f'https://api.sleeper.com/projections/nfl/{season}/{week}?season_type=regular'
           '&position[]=QB&position[]=RB&position[]=WR&position[]=TE&order_by=pts_ppr')
    out = {}
    for x in get(url):
        st = x.get('stats') or {}
        if x.get('player_id') is not None: out[str(x['player_id'])] = {v: round(float(st[k]), 2) for k, v in SL_KEY.items() if k in st}
    return out


log = []
for S, W0, W1 in ((2026, 1, 8), (2025, 1, 18)):
    for nm, fn in (('espn', espn), ('sleeper', sleeper)):
        out = {}
        for W in range(W0, W1 + 1):
            for t in range(3):
                try: out[str(W)] = fn(S, W); break
                except Exception as e: err = str(e); time.sleep(3)
            else: out[str(W)] = {}; log.append(f'{nm} {S} w{W}: {err}')
            time.sleep(.4)
        json.dump(out, gzip.open(f'stats/{nm}_{S}.json.gz', 'wt'), separators=(',', ':'))
        log.append(f'{nm} {S}: ' + ' '.join(f'{w}:{len(v)}' for w, v in out.items())); print(log[-1], flush=True)
open('stats/log.txt', 'w').write('\n'.join(log))
