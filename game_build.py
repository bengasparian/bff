#!/usr/bin/env python3
"""Spin Draft data for BFF: every NFL team's fantasy scorers in every completed regular season since 1999.

For each team and season: the quarterbacks, running backs (fullbacks count as running backs), receivers and tight ends
who scored fantasy points for that team, with their regular-season totals in PPR and standard scoring (half PPR is the
average of the two) and the games in which they recorded a stat. A player traded during a season counts for each team
with the points he scored there. Points are nflverse's own weekly fantasy points added up (PPR: 1 per catch; standard:
none; both 0.04 a passing yard, 4 a passing TD, -2 an interception, 0.1 a rushing or receiving yard, 6 a rushing,
receiving or kick/punt return TD, 2 a two-point conversion, -2 a fumble lost, sack fumbles included). tests/gametest.py
re-adds every weekly row of every season from its stat line with these rules and checks famous seasons against their
published totals (Cooper Kupp 2021: 439.5 PPR; Christian McCaffrey 2023: 391.3).

Completed seasons never change, so game.json is built once and only rebuilt when a newly completed season is missing.
python game_build.py            (needs stats_player_week_<season>.parquet for 1999 to the last completed season; it
                                 downloads the missing ones from nflverse)"""
import csv, datetime, json, os, sys, urllib.request
import pandas as pd

FIRST = 1999
POS = {'QB': 0, 'RB': 1, 'FB': 1, 'WR': 2, 'TE': 3}
KEEP = 14          # players kept per team and season (by PPR points); every position present is kept
URL = 'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{y}.parquet'


def last_complete():
    rows = [g for g in csv.DictReader(open('games.csv', newline='')) if g.get('game_type') == 'REG']
    done = lambda y: all(g['home_score'] not in ('', 'NA') for g in rows if int(g['season']) == y) and any(int(g['season']) == y for g in rows)
    y = max(int(g['season']) for g in rows)
    while y >= FIRST and not done(y): y -= 1
    return y


def stats(y):
    for f in (f'stats_player_week_{y}.parquet', f'.cache/stats_player_week_{y}.parquet'):
        if os.path.exists(f): return pd.read_parquet(f)
    os.makedirs('.cache', exist_ok=True); f = f'.cache/stats_player_week_{y}.parquet'
    with urllib.request.urlopen(URL.format(y=y), timeout=300) as r: open(f, 'wb').write(r.read())
    print('downloaded', f, flush=True); return pd.read_parquet(f)


def build(last):
    names, nix, T = [], {}, {}
    for y in range(FIRST, last + 1):
        s = stats(y); s = s[(s.season_type == 'REG') & s.position.isin(list(POS))].copy()
        tcol = 'team' if 'team' in s.columns else 'recent_team'
        nm = 'player_display_name' if 'player_display_name' in s.columns else 'player_name'
        s['fantasy_points'] = s.fantasy_points.fillna(0); s['fantasy_points_ppr'] = s.fantasy_points_ppr.fillna(0)
        g = s.groupby([tcol, 'player_id']).agg(n=(nm, 'last'), pos=('position', lambda x: x.mode().iat[0]), ppr=('fantasy_points_ppr', 'sum'),
                                               std=('fantasy_points', 'sum'), g=('week', 'nunique')).reset_index()
        g = g[g.ppr.round(1) != 0]
        T[str(y)] = {}
        for tm, x in g.groupby(tcol):
            x = x.sort_values('ppr', ascending=False)
            keep = pd.concat([x.head(KEEP)] + [x[x.pos.map(POS) == c].head(1) for c in range(4)]).drop_duplicates('player_id').sort_values('ppr', ascending=False)
            rows = []
            for r in keep.itertuples():
                k = (r.player_id, r.n)
                if k not in nix: nix[k] = len(names); names.append(r.n)
                rows.append([nix[k], POS[r.pos], int(round(r.ppr * 10)), int(round(r.std * 10)), int(r.g)])
            T[str(y)][tm] = rows
        print(y, len(T[str(y)]), 'teams', flush=True)
    ids = {v: k[0] for k, v in nix.items()}
    return {'v': 1, 'first': FIRST, 'last': last, 'built': datetime.date.today().isoformat(),
            'src': "nflverse weekly player stats (regular season), each team's QBs, RBs, WRs and TEs", 'names': names, 'pid': [ids[i] for i in range(len(names))], 't': T}


if __name__ == '__main__':
    try:
        last = last_complete()
        old = json.load(open('game.json')) if os.path.exists('game.json') else {}
        if old.get('last') == last and old.get('v') == 1 and '--force' not in sys.argv:
            print(f'game.json is current (seasons {old["first"]}-{last})'); sys.exit(0)
        G = build(last); json.dump(G, open('game.json', 'w'), separators=(',', ':'))
        print(f'game.json: seasons {FIRST}-{last}, {sum(len(v) for v in G["t"].values())} team-seasons, {len(G["names"])} players, {os.path.getsize("game.json") // 1024} KB')
    except Exception as e:   # never break the data job: the game keeps the last data it had
        print('Spin Draft data not rebuilt:', e)
