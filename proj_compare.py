"""Head-to-head tracking: BFF's weekly projections vs ESPN's and Sleeper's public projections (and the FantasyPros weekly
expert ranks), saved before every game and frozen at kickoff, so after the games everyone is graded on the same players
with the same information cutoff. Runs with the frequent scores job (standard library only).

proj_compare.json: {"season": 2026, "weeks": {"7": {"<gsis id>": {"b": BFF, "o": BFF model alone, "r": FantasyPros rank,
"e": ESPN, "s": Sleeper, "k": kickoff (ISO), "p": position}}}, "at": {...}}
ESPN PPR points are re-scored here from ESPN's projected stats (catches, yards, touchdowns, interceptions), so every
source uses the same scoring. Grading (actual PPR points from the official stats) happens in ff_produce.py.
"""
import json, os, datetime, urllib.request

OUT = 'proj_compare.json'
UA = {'User-Agent': 'Mozilla/5.0 (BFF projection tracker)', 'Accept': 'application/json'}


def page_data():
    if os.path.exists('ff_data.json') and os.environ.get('BFF_USE_FF_DATA'): return json.load(open('ff_data.json'))
    h = open('index.html', encoding='utf-8').read(); i = h.index('const D=') + 8; j = h.index(';\n', i)
    return json.loads(h[i:j].replace('<\\/', '</'))


def get_json(url, headers=None, timeout=40):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r: return json.loads(r.read().decode('utf-8'))


# ESPN projected-stat ids -> PPR points (3 passing yards, 4 passing TDs, 20 interceptions, 24 rushing yards, 25 rushing TDs,
# 42 receiving yards, 43 receiving TDs, 53 receptions, 72 fumbles lost)
ESPN_PPR = {'3': .04, '4': 4, '20': -2, '24': .1, '25': 6, '42': .1, '43': 6, '53': 1, '72': -2}


def espn(season, week):
    flt = {'players': {'limit': 1200, 'sortPercOwned': {'sortAsc': False, 'sortPriority': 1}, 'filterSlotIds': {'value': [0, 2, 4, 6]},
                       'filterStatsForTopScoringPeriodIds': {'value': 2, 'additionalValue': [f'00{season}', f'10{season}', f'11{season}{week}']}}}
    url = f'https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leaguedefaults/3?scoringPeriodId={week}&view=kona_player_info'
    J = get_json(url, {'X-Fantasy-Filter': json.dumps(flt)}); out = {}
    for x in J.get('players', []):
        p = x.get('player') or {}; pid = p.get('id')
        for s in p.get('stats') or []:
            if s.get('statSourceId') == 1 and s.get('statSplitTypeId') == 1 and s.get('scoringPeriodId') == week and s.get('seasonId') == season:
                st = s.get('stats') or {}
                pts = sum(float(st.get(k, 0) or 0) * w for k, w in ESPN_PPR.items()) if st else s.get('appliedTotal')
                if pid is not None and pts is not None: out[str(pid)] = round(float(pts), 2)
    return out


def sleeper(season, week):
    url = (f'https://api.sleeper.com/projections/nfl/{season}/{week}?season_type=regular'
           '&position[]=QB&position[]=RB&position[]=WR&position[]=TE&order_by=pts_ppr')
    out = {}
    for x in get_json(url):
        st = x.get('stats') or {}; pid = x.get('player_id')
        if pid is not None and st.get('pts_ppr') is not None: out[str(pid)] = round(float(st['pts_ppr']), 2)
    return out


def main():
    D = page_data(); S = int(D['asof']['season']); W = int(D['asof'].get('next_week') or 0)
    if not W or D['asof'].get('phase') != 'season': print('projection tracker: no regular-season week ahead'); return
    try: H = json.load(open(OUT))
    except Exception: H = {}
    if H.get('season') != S: H = {'season': S, 'weeks': {}, 'at': {}}
    now = datetime.datetime.now(datetime.timezone.utc); wk = H['weeks'].setdefault(str(W), {})
    kick = {}
    for tm, L in (D.get('sched') or {}).items():
        for g in L:
            if g[0] == W and len(g) > 5 and g[5]: kick[tm] = g[5]
    src = {}
    for nm, fn in (('e', espn), ('s', sleeper)):
        try: src[nm] = fn(S, W); print(f'projection tracker: {nm} {len(src[nm])} players')
        except Exception as e: print(f'projection tracker: {nm} unavailable ({e})'); src[nm] = {}
    n = 0
    for p in D.get('players', []):
        if p.get('nw') != W or p.get('p') not in ('QB', 'RB', 'WR', 'TE') or p.get('t') not in kick: continue
        k = kick[p['t']]
        try:
            if datetime.datetime.fromisoformat(k) <= now: continue   # kicked off: frozen
        except Exception: continue
        e_ = src['e'].get(str(p.get('eid'))) if p.get('eid') else None; s_ = src['s'].get(str(p.get('sid'))) if p.get('sid') else None
        own = None if p.get('proj') is None else round(p['proj'] - (p.get('adjc') or 0), 1)
        rec = {'b': p.get('proj'), 'o': own, 'r': p.get('wkr'), 'p': p['p'], 'k': k}
        if e_ is not None: rec['e'] = e_
        elif 'e' in wk.get(p['id'], {}): rec['e'] = wk[p['id']]['e']   # keep ESPN's last number if this fetch missed him
        if s_ is not None: rec['s'] = s_
        elif 's' in wk.get(p['id'], {}): rec['s'] = wk[p['id']]['s']
        wk[p['id']] = rec; n += 1
    H['at'][str(W)] = now.isoformat(timespec='minutes')
    json.dump(H, open(OUT, 'w'), separators=(',', ':')); print(f'projection tracker: week {W}, {n} players updated before kickoff')


if __name__ == '__main__':
    try: main()
    except Exception as e: print('projection tracker skipped:', e)
