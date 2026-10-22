"""BFF research: weekly projections vs the FantasyPros weekly expert consensus, 2023-2025, strictly out of sample.
Run from the repository folder after `python fetch_data.py`:   python research/bt_weekly.py   (about 10 minutes)
Downloads the FantasyPros ranking archive (DynastyProcess, ~40 MB) into research/ the first time.
For each test season S the models are trained only on seasons before S (2023: 2021-22; 2024: 2021-23; 2025: 2021-24).
Compared on the same player-games: a simple baseline (season average shrunk toward last season), BFF's model alone,
the FantasyPros weekly expert consensus alone (Friday rankings, via DynastyProcess), and the BFF blend (35% model,
65% consensus, the live site's weights). Also: the blend weight chosen leave-one-season-out, and sensitivity of the
hand-set constants (games of last season used for shrinking, games of league average in the matchup factor).
Writes bt_weekly_results.json."""
import os, sys, json, itertools, numpy as np, pandas as pd
BT = os.path.dirname(os.path.abspath(__file__)); RUN = os.path.dirname(BT); os.chdir(RUN); sys.path.insert(0, RUN); sys.argv = ['x']
import urllib.request
FPECR = os.path.join(BT, 'db_fpecr.parquet')
if not os.path.exists(FPECR): urllib.request.urlretrieve('https://raw.githubusercontent.com/dynastyprocess/data/master/files/db_fpecr.parquet', FPECR)
from ff_build2 import POS, F, EWF, st, build, HIST, ids, dvp_factor
from sklearn.linear_model import HuberRegressor
from sklearn.ensemble import HistGradientBoostingRegressor as HGBR
from scipy.stats import spearmanr
DA = build(HIST)
opp = st[['player_id', 'season', 'week', 'opponent_team', 'team']].drop_duplicates(['player_id', 'season', 'week'])
DA = DA.merge(opp, on=['player_id', 'season', 'week'], how='left')
mk_lin = lambda: HuberRegressor(max_iter=500, epsilon=1.6)
mk_tree = lambda: HGBR(max_iter=250, learning_rate=.04, max_leaf_nodes=15, min_samples_leaf=80, l2_regularization=2.0, random_state=0)
CHOICE = {p: 'ensemble' for p in ('QB', 'RB', 'WR', 'TE')}   # the site: the average of both models at every position
def bk(x, y):
    if y == y and y >= 2: return None
    return 'u' if x != x else ('1' if x <= 32 else '2' if x <= 64 else '3' if x <= 100 else '4')
def mkprep(pavg, dpri, K=3):
    def prep(d):
        d = d.copy(); pv = d.prev.copy(); pv = pv.fillna(pd.Series([dpri.get((p_, bk(x, y)), np.nan) for p_, x, y in zip(d.pos, d.dpick, d.yrs)], index=d.index)); pv = pv.fillna(d.pos.map(pavg))
        d['b'] = np.where(d.g > 0, (d.ppg.fillna(0)*d.g + pv*K)/(d.g + K), pv); d['bx'] = np.where(d.g > 0, (d.xpg.fillna(0)*d.g + pv*K)/(d.g + K), pv)
        d['l3f'] = d.l3.fillna(d.b); d['dv'] = d.dvp.fillna(1.0) - 1; d['iv'] = d.it.fillna(22.5)/22.5 - 1; d['bd'] = d.b*d.dv; d['bi'] = d.b*d.iv
        for c in ('bump', 'qbm', 'vac_all', 'ew'): d[c] = d[c].fillna(0.0)
        d['bq'] = d.b*d.qbm; w = d.ew
        d['be'] = (d.efp.fillna(0)*w + pv*K)/(w + K); d['bxe'] = (d.exf.fillna(0)*w + pv*K)/(w + K); d['bed'] = d.be*d.dv; d['bei'] = d.be*d.iv
        d['dsn'] = (d.esn - d.snap).fillna(0); d['dts'] = (d.ets - d.ts).fillna(0); d['dcs'] = (d.ecs - d.cs).fillna(0); return d
    return prep
def FEAT(pos):
    LL = ['b', 'bx', 'l3f', 'bd', 'bi', 'bq'] + ([] if pos == 'QB' else ['bump']) + ['be', 'bxe', 'bed', 'bei']
    FF = F + ['b', 'bx', 'qbm'] + ([] if pos == 'QB' else ['bump', 'vac_all']) + EWF + ['be', 'bxe', 'dsn', 'dts', 'dcs', 'dpick', 'yrs']; return LL, FF
def predict_season(D, S, K=3, choice=CHOICE):
    """train on seasons before S, predict every player-game of S; returns test frame with columns base, model"""
    tr = D[D.season < S]; te = D[D.season == S].copy(); pavg = {p: float(tr[tr.pos == p].y.mean()) for p in POS}
    t_ = tr[tr.prev.isna()].copy(); t_['bk'] = [bk(x, y) for x, y in zip(t_.dpick, t_.yrs)]; dpri = t_.dropna(subset=['bk']).groupby(['pos', 'bk']).y.mean().to_dict()
    prep = mkprep(pavg, dpri, K); parts = []
    for pos in POS:
        a = prep(tr[tr.pos == pos]); t = prep(te[te.pos == pos]); LL, FF = FEAT(pos)
        pl = mk_lin().fit(a[LL], a.y).predict(t[LL]); pt = mk_tree().fit(a[FF], a.y).predict(t[FF])
        m = {'linear': pl, 'tree': pt, 'ensemble': (pl + pt)/2}[choice[pos]]
        t = t.assign(base=t.b.values, model=np.maximum(0, m), lin=pl, tree=pt); parts.append(t)
    return pd.concat(parts)
def wk_metrics(T, col):
    """mean over (season, week, position) of Spearman with points, and mean absolute error"""
    sp = []; mae = []
    for _, x in T.groupby(['season', 'week', 'pos']):
        if len(x) > 8: sp.append(spearmanr(x[col], x.y).correlation); mae.append(float(np.mean(np.abs(x[col] - x.y))))
    return float(np.nanmean(sp)), float(np.mean(mae))
# ---------------- 1. hand-set constants (model alone, all players, 2023-2025 rolling)
SENS = {}
for K in (1, 2, 3, 5, 8):
    T = pd.concat([predict_season(DA, S, K) for S in (2023, 2024, 2025)])
    SENS[f'prior_games={K}'] = {pos: [round(v, 4) for v in wk_metrics(T[T.pos == pos], 'model')] for pos in POS}
    SENS[f'prior_games={K}']['all'] = [round(v, 4) for v in wk_metrics(T, 'model')]; print('prior', K, SENS[f'prior_games={K}']['all'], flush=True)
for k in (2, 4, 8):
    D2 = DA.copy(); D2['dvp'] = [dvp_factor(s, w, o, p, k) if w > 2 else np.nan for s, w, o, p in zip(D2.season, D2.week, D2.opponent_team, D2.pos)]
    T = pd.concat([predict_season(D2, S) for S in (2023, 2024, 2025)])
    SENS[f'matchup_games={k}'] = {pos: [round(v, 4) for v in wk_metrics(T[T.pos == pos], 'model')] for pos in POS}
    SENS[f'matchup_games={k}']['all'] = [round(v, 4) for v in wk_metrics(T, 'model')]; print('dvp k', k, SENS[f'matchup_games={k}']['all'], flush=True)
for ch in ('linear', 'tree', 'ensemble'):
    T = pd.concat([predict_season(DA, S, 3, {p: ch for p in POS}) for S in (2023, 2024, 2025)])
    SENS[f'model={ch}'] = {pos: [round(v, 4) for v in wk_metrics(T[T.pos == pos], 'model')] for pos in POS}; print('model', ch, SENS[f'model={ch}'], flush=True)
# ---------------- 2. head to head with the FantasyPros weekly consensus
T = pd.concat([predict_season(DA, S) for S in (2023, 2024, 2025)])
E = pd.read_parquet(FPECR, columns=['id', 'pos', 'ecr', 'ecr_type', 'scrape_date', 'fp_page'])
E = E[(E.ecr_type == 'wp') & E.pos.isin(POS)].copy(); E['scrape_date'] = pd.to_datetime(E.scrape_date)
E = E[E.fp_page.str.contains('ppr', na=False) | (E.pos == 'QB')]
fp2g = {str(int(f)): g for f, g in zip(ids.fantasypros_id, ids.gsis_id) if f == f and isinstance(g, str)}
GM = pd.read_csv('games.csv'); GM = GM[GM.game_type == 'REG']; GM['gameday'] = pd.to_datetime(GM.gameday)
gday = {}
for g in GM.itertuples():
    for t_ in (g.home_team, g.away_team): gday[(g.season, g.week, t_)] = g.gameday
rows = []
for (S, W), x in T.groupby(['season', 'week']):
    sun = GM[(GM.season == S) & (GM.week == W)].gameday.max()
    e = E[(E.scrape_date <= sun) & (E.scrape_date >= sun - pd.Timedelta(days=6))]
    if not len(e): continue
    sd = e.scrape_date.max(); e = e[e.scrape_date == sd]; rk = {}
    for i_, p_, r_ in zip(e.id, e.pos, e.ecr):
        g_ = fp2g.get(str(i_))
        if g_: rk[g_] = float(r_)
    x = x.copy(); x['ecr'] = x.player_id.map(rk); x['gd'] = [gday.get((S, W, t_)) for t_ in x.team]
    x = x[x.ecr.notna() & (x.gd >= sd)]   # ranked before his game (Thursday games before the Friday rankings are left out)
    rows.append(x)
H = pd.concat(rows); print('head-to-head player-games', len(H), 'weeks', H.groupby(['season', 'week']).ngroups, flush=True)
# consensus on our scale: the k-th ranked player at a position that week gets the k-th highest model projection
parts = []
for _, x in H.groupby(['season', 'week', 'pos']):
    x = x.copy(); curve = np.sort(x.model.values)[::-1]; order = x.ecr.rank(method='first').astype(int).values - 1
    x['cons'] = curve[order]; parts.append(x)
H = pd.concat(parts)
TOPK = {'QB': 24, 'RB': 40, 'WR': 50, 'TE': 20}
def pairwise(x, col):
    """among start/sit-relevant players (consensus top 24 QB, 40 RB, 50 WR, 20 TE), how often the higher-ranked of two scored more"""
    x = x[x.ecr <= TOPK[x.pos.iloc[0]]]; v = x[col].values; y = x.y.values; ok = n = 0
    for i, j in itertools.combinations(range(len(x)), 2):
        if y[i] == y[j] or v[i] == v[j]: continue
        n += 1; ok += (v[i] > v[j]) == (y[i] > y[j])
    return ok, n
def score(Hs, col):
    sp, mae = wk_metrics(Hs, col); ok = n = 0
    for _, x in Hs.groupby(['season', 'week', 'pos']):
        a, b = pairwise(x, col); ok += a; n += b
    return {'rank': round(sp, 4), 'mae': round(mae, 3), 'pairs': round(ok / max(n, 1), 4), 'n_pairs': n}
H['negecr'] = -H.ecr
WS = [round(w, 2) for w in np.arange(0, 1.0001, .05)]
for w in WS: H[f'b{w}'] = (1 - w)*H.model + w*H.cons
RES = {'n_player_games': int(len(H)), 'weeks': int(H.groupby(['season', 'week']).ngroups), 'by_pos': {}, 'by_season': {}, 'grid': {}, 'loso': {}}
cols = {'baseline': 'base', 'bff_model': 'model', 'consensus': 'negecr', 'bff_blend_65': 'b0.65', 'bff_blend_85': 'b0.85'}
for nm, c in cols.items():
    RES[nm] = score(H, c); print(nm, RES[nm], flush=True)
    for pos in POS: RES['by_pos'].setdefault(pos, {})[nm] = score(H[H.pos == pos], c)
    for S in (2023, 2024, 2025): RES['by_season'].setdefault(str(S), {})[nm] = score(H[H.season == S], c)
RES['consensus_mae_on_our_scale'] = score(H, 'cons')['mae']
for w in WS: RES['grid'][str(w)] = list(wk_metrics(H, f'b{w}'))
for S in (2023, 2024, 2025):
    other = H[H.season != S]; best = max(WS, key=lambda w: wk_metrics(other, f'b{w}')[0]); RES['loso'][str(S)] = {'w': best, **score(H[H.season == S], f'b{best}')}
print(json.dumps(RES['loso']), flush=True)
RES['sensitivity'] = SENS
json.dump(RES, open(os.path.join(BT, 'results_weekly.json'), 'w'), indent=1, default=float); print('saved', flush=True)
