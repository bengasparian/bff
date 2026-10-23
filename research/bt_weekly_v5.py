"""BFF research: the version 5 weekly projections vs the FantasyPros weekly expert consensus, 2021-2026, strictly out of
sample, using the site's own code (ff_feat.py builds the features, ff_model.py the model).

Run from the repository folder:   python research/bt_weekly_v5.py   (about 40 minutes; downloads about 350 MB the first time)
For each season S (2021-2026) the model is trained only on seasons 2013..S-1 and predicts every game of S. The weekly
expert consensus comes from the FantasyPros archive kept by DynastyProcess (Friday position ranks). Head-to-head rows are
the players the experts ranked who played, in weeks with a ranking taken before their game (the same rows as
bt_weekly.py, so the numbers line up).
Scores (by season, position and overall): rank accuracy = mean over (week, position) of the Spearman correlation between
the projection and the points scored; pairs = among start/sit-relevant players (consensus top 24 QB, 40 RB, 50 WR, 20 TE),
how often the higher-ranked of two scored more; average miss in PPR points.
The site's weekly projection mixes the model with the consensus by z-scores (40% model, 60% experts); the weight was
chosen on 2021-22 and is reported on 2023-26 as well.
Writes research/results_weekly_v5.json."""
import os, sys, json, itertools, time, urllib.request, numpy as np, pandas as pd
BT = os.path.dirname(os.path.abspath(__file__)); RUN = os.path.dirname(BT); os.chdir(RUN); sys.path.insert(0, RUN)
from scipy.stats import spearmanr
import ff_feat as FX, ff_model as FM
B = 'https://github.com/nflverse/nflverse-data/releases/download/'
FILES = {'pbp_{y}.parquet': 'pbp/play_by_play_{y}.parquet', 'stats_player_week_{y}.parquet': 'stats_player/stats_player_week_{y}.parquet',
         'snap_counts_{y}.parquet': 'snap_counts/snap_counts_{y}.parquet', 'injuries_{y}.parquet': 'injuries/injuries_{y}.parquet',
         'roster_weekly_{y}.parquet': 'weekly_rosters/roster_weekly_{y}.parquet', 'depth_charts_{y}.parquet': 'depth_charts/depth_charts_{y}.parquet'}
for y in range(2012, 2027):
    for f, u in FILES.items():
        f = f.format(y=y)
        if not os.path.exists(f):
            try: urllib.request.urlretrieve(B + u.format(y=y), f); print('downloaded', f, flush=True)
            except Exception as e: print('not available', f, e)
FPECR = os.path.join(BT, 'db_fpecr.parquet')
if not os.path.exists(FPECR): urllib.request.urlretrieve('https://raw.githubusercontent.com/dynastyprocess/data/master/files/db_fpecr.parquet', FPECR)
t0 = time.time()
C = FX.Ctx(list(range(2012, 2027)), [2012, 2013])
SCOL = ['passing_yards', 'passing_tds', 'passing_interceptions', 'rushing_yards', 'rushing_tds', 'receptions', 'receiving_yards', 'receiving_tds']
D = pd.concat([C.season_rows(s) for s in range(2013, 2027)], ignore_index=True)
D = D.merge(C.st[['player_id', 'season', 'week'] + SCOL].drop_duplicates(['player_id', 'season', 'week']), on=['player_id', 'season', 'week'], how='left'); D[SCOL] = D[SCOL].fillna(0)
FC = [c for c in D.columns if c not in SCOL]; print('features built', len(D), round(time.time() - t0), flush=True)
out = []
for S in range(2021, 2027):
    M = FM.Model(D[(D.season < S) & (D.season >= 2013)], FC, seeds=3, ros=False); te = D[D.season == S]
    for pos in FM.POS:
        t = te[te.pos == pos]; out.append(t[['player_id', 'season', 'week', 'pos', 'team', 'y', 'g', 'm_fp', 'p_fp']].assign(model=M.next(pos, t)))
    print('season', S, round(time.time() - t0), flush=True)
P = pd.concat(out, ignore_index=True)
# ---- the weekly consensus, matched to games on or after the ranking date
E = pd.read_parquet(FPECR, columns=['id', 'pos', 'ecr', 'ecr_type', 'scrape_date', 'fp_page'])
E = E[(E.ecr_type == 'wp') & E.pos.isin(FM.POS)].copy(); E['scrape_date'] = pd.to_datetime(E.scrape_date); E = E[E.fp_page.str.contains('ppr', na=False) | (E.pos == 'QB')]
ids = pd.read_csv('db_playerids.csv', low_memory=False); FP2G = {str(int(f)): g for f, g in zip(ids.fantasypros_id, ids.gsis_id) if f == f and isinstance(g, str)}
GM = pd.read_csv('games.csv'); GM = GM[GM.game_type == 'REG']; GM['gameday'] = pd.to_datetime(GM.gameday)
GD = {(g.season, g.week, t): g.gameday for g in GM.itertuples() for t in (g.home_team, g.away_team)}
rows = []
for (S, W), x in P.groupby(['season', 'week']):
    sun = GM[(GM.season == S) & (GM.week == W)].gameday.max(); e = E[(E.scrape_date <= sun) & (E.scrape_date >= sun - pd.Timedelta(days=6))]
    if not len(e): continue
    sd = e.scrape_date.max(); e = e[e.scrape_date == sd]; rk = {FP2G[str(i)]: float(r) for i, r in zip(e.id, e.ecr) if str(i) in FP2G}
    x = x.assign(ecr=x.player_id.map(rk), gd=[GD.get((S, W, t)) for t in x.team]); rows.append(x[x.ecr.notna() & (x.gd >= sd)])
H = pd.concat(rows, ignore_index=True); G = ['season', 'week', 'pos']; g = H.groupby(G)
H['mz'] = (H.model - g.model.transform('mean')) / g.model.transform('std'); H['ez'] = -(H.ecr - g.ecr.transform('mean')) / g.ecr.transform('std'); H['experts'] = -H.ecr
parts = []
for _, x in H.groupby(G):
    x = x.copy(); curve = np.sort(x.model.values)[::-1]
    for w in (.2, .3, .4, .5, .6):
        sc = w * x.mz + (1 - w) * x.ez; x[f'mix{int(w*100)}'] = curve[sc.rank(method='first', ascending=False).astype(int).values - 1]
    x['experts_pts'] = curve[x.ecr.rank(method='first').astype(int).values - 1]; parts.append(x)
H = pd.concat(parts, ignore_index=True)
TOPK = {'QB': 24, 'RB': 40, 'WR': 50, 'TE': 20}


def score(h, col):
    sp = []; mae = []; ok = n = 0
    for (s_, w_, p_), x in h.groupby(G):
        if len(x) > 8: sp.append(spearmanr(x[col], x.y).correlation); mae.append(float(np.mean(np.abs(x[col] - x.y))))
        z = x[x.ecr <= TOPK[p_]]; v = z[col].values; y = z.y.values
        for i, j in itertools.combinations(range(len(z)), 2):
            if y[i] == y[j] or v[i] == v[j]: continue
            n += 1; ok += (v[i] > v[j]) == (y[i] > y[j])
    return {'rank': round(float(np.nanmean(sp)), 4), 'mae': round(float(np.mean(mae)), 3), 'pairs': round(ok / max(n, 1), 4), 'n': int(len(h))}


COLS = {'experts': 'experts', 'bff_model': 'model', 'bff_mix40': 'mix40', 'mix20': 'mix20', 'mix30': 'mix30', 'mix50': 'mix50', 'mix60': 'mix60'}
R = {'by_season': {}, 'periods': {}, 'by_pos': {}, 'experts_mae_on_bff_scale': {}}
for S in range(2021, 2027): R['by_season'][str(S)] = {k: score(H[H.season == S], c) for k, c in COLS.items()}
for nm, (a, b) in {'2021-22 (weight chosen here)': (2021, 2022), '2023-25': (2023, 2025), '2026 so far': (2026, 2026)}.items():
    R['periods'][nm] = {k: score(H[H.season.between(a, b)], c) for k, c in COLS.items()}
    R['experts_mae_on_bff_scale'][nm] = score(H[H.season.between(a, b)], 'experts_pts')['mae']
    R['by_pos'][nm] = {p: {k: score(H[H.season.between(a, b) & (H.pos == p)], c)['rank'] for k, c in (('experts', 'experts'), ('bff_model', 'model'), ('bff_mix40', 'mix40'))} for p in FM.POS}
# must-start calls: the top 10 at each position each week; a hit finishes inside the starter spots among these players
# (top 12 QB, 24 RB, 30 WR, 12 TE); the yardstick is the season average shrunk toward last season (3 games' worth)
H['avg'] = np.where(H.g > 0, (H.m_fp.fillna(0) * H.g + H.p_fp.fillna(H.m_fp.fillna(8)) * 3) / (H.g + 3), H.p_fp.fillna(8))
TH = {'QB': 12, 'RB': 24, 'WR': 30, 'TE': 12}; R['must_start_2023_25'] = {}
for nm, col, asc in (('BFF projection', 'mix40', False), ('BFF model alone', 'model', False), ('FantasyPros experts', 'ecr', True), ('Season average', 'avg', False)):
    hit = n = 0
    for (s_, w_, p_), x in H[H.season.between(2023, 2025)].groupby(G):
        fin = x.y.rank(ascending=False, method='min') <= TH[p_]; top = x.sort_values(col, ascending=asc).head(10); hit += int(fin[top.index].sum()); n += len(top)
    R['must_start_2023_25'][nm] = round(100 * hit / n, 1)
print('must starts', R['must_start_2023_25'])
for k, v in R['periods'].items(): print(k, json.dumps(v))
print(json.dumps(R['by_season']))
json.dump(R, open(os.path.join(BT, 'results_weekly_v5.json'), 'w'), indent=1); print('saved', round(time.time() - t0))
