"""BFF research, part 1 of the trade-value backtest (part 2: bt_value_eval.py).
Run from the repository folder after `python fetch_data.py`:   python research/bt_value_build.py   (about 15 minutes)

Original purpose: should BFF value also count points over a WAIVER-level replacement (VORP, like basketball's value over
replacement player), not only over the best non-starter (the current 'replacement starter')?

Seasons 2023-2025, checkpoints before weeks 4, 6, 8, 10, 12. Projections come from the site's model trained only on
earlier seasons. Truth: in 10 simulated 12-team leagues per checkpoint (rosters drafted from the FantasyPros
consensus with noise, 15 players: 2 QB, 5 RB, 6 WR, 2 TE; starters 1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX chosen each week by
projection), the real lineup points a player added over the best free agent at his position, rest of season.
Output: bt_vorp_cut.pkl (inputs, reused by bt_vorp_eval.py)."""
import os, sys, pickle, numpy as np, pandas as pd
BT = os.path.dirname(os.path.abspath(__file__)); RUN = os.path.dirname(BT)
import urllib.request
FPECR = os.path.join(BT, 'db_fpecr.parquet')
if not os.path.exists(FPECR): urllib.request.urlretrieve('https://raw.githubusercontent.com/dynastyprocess/data/master/files/db_fpecr.parquet', FPECR)
os.chdir(RUN); sys.path.insert(0, RUN); sys.argv = ['x']
from ff_build2 import POS, F, EWF, st, SC, prev, feats, draft_feats, build, HIST, ids
from sklearn.linear_model import HuberRegressor
from sklearn.ensemble import HistGradientBoostingRegressor as HGBR
DA = build(HIST)
mk_lin = lambda: HuberRegressor(max_iter=500, epsilon=1.6)
mk_tree = lambda: HGBR(max_iter=250, learning_rate=.04, max_leaf_nodes=15, min_samples_leaf=80, l2_regularization=2.0, random_state=0)
def bk(x, y):
    if y == y and y >= 2: return None
    return 'u' if x != x else ('1' if x <= 32 else '2' if x <= 64 else '3' if x <= 100 else '4')
def mkprep(pavg, dpri):
    def prep(d):
        d = d.copy(); pv = d.prev.copy(); pv = pv.fillna(pd.Series([dpri.get((p_, bk(x, y)), np.nan) for p_, x, y in zip(d.pos, d.dpick, d.yrs)], index=d.index)); pv = pv.fillna(d.pos.map(pavg))
        d['b'] = np.where(d.g > 0, (d.ppg.fillna(0)*d.g + pv*3)/(d.g + 3), pv); d['bx'] = np.where(d.g > 0, (d.xpg.fillna(0)*d.g + pv*3)/(d.g + 3), pv)
        d['l3f'] = d.l3.fillna(d.b); d['dv'] = d.dvp.fillna(1.0) - 1; d['iv'] = d.it.fillna(22.5)/22.5 - 1; d['bd'] = d.b*d.dv; d['bi'] = d.b*d.iv
        for c in ('bump', 'qbm', 'vac_all', 'ew'): d[c] = d[c].fillna(0.0)
        d['bq'] = d.b*d.qbm; w = d.ew
        d['be'] = (d.efp.fillna(0)*w + pv*3)/(w + 3); d['bxe'] = (d.exf.fillna(0)*w + pv*3)/(w + 3); d['bed'] = d.be*d.dv; d['bei'] = d.be*d.iv
        d['dsn'] = (d.esn - d.snap).fillna(0); d['dts'] = (d.ets - d.ts).fillna(0); d['dcs'] = (d.ecs - d.cs).fillna(0); return d
    return prep
def FEAT(pos):
    LL = ['b', 'bx', 'l3f', 'bd', 'bi', 'bq'] + ([] if pos == 'QB' else ['bump']) + ['be', 'bxe', 'bed', 'bei']
    FF = F + ['b', 'bx', 'qbm'] + ([] if pos == 'QB' else ['bump', 'vac_all']) + EWF + ['be', 'bxe', 'dsn', 'dts', 'dcs', 'dpick', 'yrs']; return LL, FF
def ros_target(d):
    d = d.sort_values(['player_id', 'season', 'week']).copy(); yr = []; nr = []
    for _, g_ in d.groupby(['player_id', 'season'], sort=False):
        y_ = g_.y.values; n_ = len(y_); yr += [float(np.mean(y_[k:k+6])) for k in range(n_)]; nr += [min(6, n_-k) for k in range(n_)]
    d['yr'] = yr; d['nr'] = nr; return d[d.nr >= 3]
# consensus history (FantasyPros, via DynastyProcess): positional rest-of-season PPR ranks
E = pd.read_parquet(FPECR, columns=['id', 'pos', 'ecr', 'ecr_type', 'scrape_date', 'fp_page'])
E = E[E.ecr_type.isin(['rp', 'ro'])].copy(); E['scrape_date'] = pd.to_datetime(E.scrape_date)
fp2g = {str(int(f)): g for f, g in zip(ids.fantasypros_id, ids.gsis_id) if f == f and isinstance(g, str)}
GM = pd.read_csv('games.csv'); GM = GM[GM.game_type == 'REG']
def ecr_at(S, N):
    kick = pd.to_datetime(GM[(GM.season == S) & (GM.week == N)].gameday.min())
    out = {}
    for t in ('rp', 'ro'):
        e = E[(E.ecr_type == t) & (E.scrape_date <= kick) & (E.scrape_date >= kick - pd.Timedelta(days=12))]
        if t == 'rp': e = e[e.fp_page.str.contains('ppr', na=False) | e.pos.isin(['QB'])]
        if not len(e): continue
        d = e[e.scrape_date == e.scrape_date.max()]
        for i_, pos, ecr in zip(d.id, d.pos, d.ecr):
            g = fp2g.get(str(i_));
            if g and pos in POS: out.setdefault(g, {})[t] = float(ecr)
    return out
# weekly roster status (injured reserve at the checkpoint)
def res_at(S, N):
    f = f'roster_weekly_{S}.parquet'
    if not os.path.exists(f): return set()
    w = pd.read_parquet(f, columns=['gsis_id', 'week', 'status']); w = w[(w.week == N - 1) | (w.week == N)]
    return set(w[w.status == 'RES'].gsis_id)
OUT = {}
for S in (2023, 2024, 2025):
    tr = DA[DA.season < S]; pavg = {p: float(tr[tr.pos == p].y.mean()) for p in POS}
    t_ = tr[tr.prev.isna()].copy(); t_['bk'] = [bk(x, y) for x, y in zip(t_.dpick, t_.yrs)]; dpri = t_.dropna(subset=['bk']).groupby(['pos', 'bk']).y.mean().to_dict()
    prep = mkprep(pavg, dpri); trr = ros_target(tr); M = {}
    for pos in POS:
        a = prep(tr[tr.pos == pos]); b_ = prep(trr[trr.pos == pos]); LL, FF = FEAT(pos)
        M[pos] = (mk_lin().fit(a[LL], a.y), mk_tree().fit(a[FF], a.y), mk_lin().fit(b_[LL], b_.yr, sample_weight=b_.nr), mk_tree().fit(b_[FF], b_.yr, sample_weight=b_.nr))
    def mu_of(pos, d):
        out = []
        for hm in (0, 1):
            q = prep(d.assign(dvp=np.nan, it=np.nan, home=hm)); LL, FF = FEAT(pos); l1, t1, l2, t2 = M[pos]
            out.append(.5*np.maximum(0, (l1.predict(q[LL]) + t1.predict(q[FF]))/2) + .5*np.maximum(0, (l2.predict(q[LL]) + t2.predict(q[FF]))/2))
        return (out[0] + out[1])/2
    s = st[st.season == S]; sc = SC[SC.season == S]
    games = {(t, int(w)) for t, w in zip(sc.team, sc.week)}
    Y = {(p, int(w)): float(y) for p, w, y in zip(s.player_id, s.week, s.fp)}
    for N in (4, 6, 8, 10, 12):
        h = s[s.week < N]; pl = h.groupby('player_id').agg(pos=('position', 'first'), team=('team', 'last'), g=('week', 'nunique')).reset_index()
        pl = pl[pl.pos.isin(POS)]; res = res_at(S, N); pl = pl[~pl.player_id.isin(res)]
        # current team: his latest team this season
        rows = []
        for pid, pos in zip(pl.player_id, pl.pos):
            hh = h[h.player_id == pid].sort_values('week'); f = feats(S, N, hh); dp, yr = draft_feats(pid, S)
            f.update(player_id=pid, pos=pos, prev=prev.get((pid, S), np.nan), dvp=np.nan, it=np.nan, home=0, bump=0.0, qbm=0, vac_all=0.0, dpick=dp, yrs=yr); rows.append(f)
        R = pd.DataFrame(rows); mu = {}
        for pos in POS:
            d = R[R.pos == pos]
            if len(d): mu.update(dict(zip(d.player_id, mu_of(pos, d))))
        E_ = ecr_at(S, N); cut = {}
        for pid, pos, tm, g in zip(pl.player_id, pl.pos, pl.team, pl.g):
            wk = [w for w in range(N, 18)]
            cut[pid] = dict(pos=pos, team=tm, g=int(g), mu=float(mu[pid]), play=[(tm, w) in games for w in wk], y=[Y.get((pid, w), 0.0) for w in wk],
                            ecr_o=E_.get(pid, {}).get('ro'), ecr_p=E_.get(pid, {}).get('rp'))
        OUT[(S, N)] = cut; print(S, N, len(cut), 'with consensus', sum(1 for m in cut.values() if m['ecr_p']), flush=True)
pickle.dump(OUT, open(os.path.join(BT, 'value_checkpoints.pkl'), 'wb')); print('saved')
