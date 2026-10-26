"""ESPN's and Sleeper's public weekly projections, stat by stat (passing, rushing and receiving yards, receptions, passing
touchdowns, pass attempts, rush attempts, targets and PPR points), for the weeks BFF has prop lines.

Why: sportsbook and pick'em prop lines track the public projections closely. On the real week-7 2026 lines, the average of
ESPN's and Sleeper's projections (scaled where books set lines) missed by 3.4 receiving yards, 5.5 rushing yards and 9.6
passing yards; BFF's own opportunity model missed by 6.9, 9.1 and 13.3 (research/bt_lines.py). So ff_lines.py sets each line
from these numbers and keeps BFF's model for the picks. Runs with both jobs, right before the lines (every 10 minutes in the
scores job, so lines follow the sites as their projections move); a player keeps his last numbers when a site does not answer.

site_stats.json: {"season": 2026, "at": {"changed": time}, "weeks": {"7": {"<gsis id>": {"e": {...}, "s": {...}}}}}
(written only when a number changed, so the 10-minute job does not save it for nothing)
with keys py (passing yards), ptd (passing TDs), ry (rushing yards), ty (receiving yards), rec (receptions), fp (PPR points),
and (Oct 25 2026, for the new prop markets) patt (pass attempts), car (rush attempts), tg (targets).
Standard library only."""
import json, os, datetime, urllib.request

OUT = 'site_stats.json'
UA = {'User-Agent': 'Mozilla/5.0 (BFF projection tracker)', 'Accept': 'application/json'}
ESPN_ID = {'3': 'py', '4': 'ptd', '24': 'ry', '42': 'ty', '53': 'rec', '0': 'patt', '23': 'car', '58': 'tg'}   # ESPN stat ids (0 pass attempts, 23 rush attempts, 58 targets)
ESPN_PPR = {'3': .04, '4': 4, '20': -2, '24': .1, '25': 6, '42': .1, '43': 6, '53': 1, '72': -2}
SL_KEY = {'pass_yd': 'py', 'pass_td': 'ptd', 'rush_yd': 'ry', 'rec_yd': 'ty', 'rec': 'rec', 'pts_ppr': 'fp', 'pass_att': 'patt', 'rush_att': 'car', 'rec_tgt': 'tg'}


def get_json(url, headers=None, timeout=40):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r: return json.loads(r.read().decode('utf-8'))


def espn(season, week):
    flt = {'players': {'limit': 1200, 'sortPercOwned': {'sortAsc': False, 'sortPriority': 1}, 'filterSlotIds': {'value': [0, 2, 4, 6]},
                       'filterStatsForTopScoringPeriodIds': {'value': 2, 'additionalValue': [f'00{season}', f'10{season}', f'11{season}{week}']}}}
    url = f'https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leaguedefaults/3?scoringPeriodId={week}&view=kona_player_info'
    out = {}
    for x in get_json(url, {'X-Fantasy-Filter': json.dumps(flt)}).get('players', []):
        p = x.get('player') or {}
        for s in p.get('stats') or []:
            if s.get('statSourceId') == 1 and s.get('statSplitTypeId') == 1 and s.get('scoringPeriodId') == week and s.get('seasonId') == season:
                st = s.get('stats') or {}
                if not st: continue
                d = {v: round(float(st[k]), 2) for k, v in ESPN_ID.items() if k in st}
                d['fp'] = round(sum(float(st.get(k, 0) or 0) * w for k, w in ESPN_PPR.items()), 2)
                out[str(p.get('id'))] = d
    return out


def sleeper(season, week):
    url = (f'https://api.sleeper.com/projections/nfl/{season}/{week}?season_type=regular'
           '&position[]=QB&position[]=RB&position[]=WR&position[]=TE&order_by=pts_ppr')
    out = {}
    for x in get_json(url):
        st = x.get('stats') or {}
        if x.get('player_id') is not None and st: out[str(x['player_id'])] = {v: round(float(st[k]), 2) for k, v in SL_KEY.items() if k in st}
    return out


def players_and_weeks():
    """player ids (gsis, ESPN, Sleeper) and the weeks with lines, from the data build or the lines' inputs"""
    for f in ('ff_data.json', 'bet_inputs.json'):
        if not os.path.exists(f): continue
        try: D = json.load(open(f))
        except Exception: continue
        a = D.get('asof') or {}; S = int(a.get('season') or 0); nw = int(a.get('next_week') or D.get('nw') or 0)
        if a.get('phase') != 'season' or not nw: return S, [], []
        weeks = sorted({w for w in (nw, nw + 1, D.get('fw')) if w and 1 <= int(w) <= 18})
        return S, [(p['id'], p.get('eid'), p.get('sid')) for p in D.get('players') or [] if p.get('p', 'QB') in ('QB', 'RB', 'WR', 'TE')], weeks
    return 0, [], []


def main():
    S, P, weeks = players_and_weeks()
    if not P or not weeks: print('site projections: no regular-season week ahead'); return
    try: H = json.load(open(OUT))
    except Exception: H = {}
    if H.get('season') != S: H = {'season': S, 'at': {}, 'weeks': {}}
    before = json.dumps(H.get('weeks'), sort_keys=True)
    H['weeks'] = {w: v for w, v in H['weeks'].items() if int(w) >= min(weeks)}   # drop finished weeks
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='minutes')
    for w in weeks:
        wk = H['weeks'].setdefault(str(w), {})
        for src, fn, idx in (('e', espn, 1), ('s', sleeper, 2)):
            try: got = fn(S, w)
            except Exception as e: print(f'site projections: {"ESPN" if src == "e" else "Sleeper"} week {w} did not answer ({e}); keeping the last numbers'); continue
            n = 0
            for pl in P:
                sid = pl[idx]
                if not sid or str(sid) not in got: continue
                wk.setdefault(pl[0], {})[src] = got[str(sid)]; n += 1
            print(f'site projections: {"ESPN" if src == "e" else "Sleeper"} week {w}: {n} players')
    if json.dumps(H['weeks'], sort_keys=True) == before: print('site projections: no change'); return   # saves only when a number moved
    H['at']['changed'] = now
    json.dump(H, open(OUT, 'w'), separators=(',', ':'))


if __name__ == '__main__':
    try: main()
    except Exception as e: print('site projections skipped:', e)
