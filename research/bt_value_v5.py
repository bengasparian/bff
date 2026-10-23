"""BFF research: rest-of-season trade values from the version 5 projections (the site's own ff_feat.py and ff_model.py),
scored on the same checkpoints, players and simulated-league truth as bt_value_eval.py.

Run from the repository folder after research/bt_value_build.py and research/bt_value_eval.py (they make
value_checkpoints.pkl and value_truth.pkl) and with the 2012-2025 data bt_weekly_v5.py downloads:
    python research/bt_value_v5.py        (about 40 minutes)
    python research/bt_value_v5.py --reuse   (re-scores the saved value_checkpoints_v5.pkl in a few minutes)
At each checkpoint (weeks 4, 6, 8, 10, 12 of 2023-2025) the model is trained only on earlier seasons; a player's
rest-of-season level is the average of his remaining next-game projections, with no betting lines for future weeks (each
team's points scored and allowed so far stand in for them) and this week's depth chart for every week ahead.
Every source is put on the same value scale (BFF's value curve), so only the order of players differs between them.
Two truths: lineups set by the previous projections (value_truth.pkl; does not favor the new model) and by the new ones.
Writes research/results_value_v5.json."""
import os, sys, pickle, random, json, time, numpy as np, pandas as pd
from scipy.stats import spearmanr, norm
BT = os.path.dirname(os.path.abspath(__file__)); RUN = os.path.dirname(BT); os.chdir(RUN); sys.path.insert(0, RUN)
import ff_feat as FX, ff_model as FM
t0 = time.time()
OLD = pickle.load(open(os.path.join(BT, 'value_checkpoints.pkl'), 'rb')); TR_OLD = pickle.load(open(os.path.join(BT, 'value_truth.pkl'), 'rb'))
SCOL = ['passing_yards', 'passing_tds', 'passing_interceptions', 'rushing_yards', 'rushing_tds', 'receptions', 'receiving_yards', 'receiving_tds']
REUSE = '--reuse' in sys.argv and os.path.exists(os.path.join(BT, 'value_checkpoints_v5.pkl'))   # skip the 35-minute rebuild
if not REUSE:
    CA = FX.Ctx(list(range(2012, 2026)), [2012, 2013])
    D = pd.concat([CA.season_rows(s) for s in range(2013, 2026)], ignore_index=True)
    D = D.merge(CA.st[['player_id', 'season', 'week'] + SCOL].drop_duplicates(['player_id', 'season', 'week']), on=['player_id', 'season', 'week'], how='left'); D[SCOL] = D[SCOL].fillna(0)
    FC = [c for c in D.columns if c not in SCOL]; print('features', len(D), round(time.time() - t0), flush=True)
NEW = {}
if REUSE: NEW = pickle.load(open(os.path.join(BT, 'value_checkpoints_v5.pkl'), 'rb'))
for S in (() if REUSE else (2023, 2024, 2025)):
    M = FM.Model(D[(D.season < S) & (D.season >= 2013)], FC, seeds=3, ros=False); SCs = CA.SC[CA.SC.season == S]
    for N in (4, 6, 8, 10, 12):
        cut = OLD[(S, N)]; tt = CA.TT[(CA.TT.season == S) & (CA.TT.week == N)].set_index('team'); games = {}
        for pid, m in cut.items():
            tm = m['team']; gl = []
            for w in range(N, 18):
                g = SCs[(SCs.team == tm) & (SCs.week == w)]
                if not len(g): continue
                g = g.iloc[0]; op = g['opp']
                if tm in tt.index and op in tt.index: it = (tt.loc[tm, 'pts_t'] + tt.loc[op, 'pa_t']) / 2; io = (tt.loc[op, 'pts_t'] + tt.loc[tm, 'pa_t']) / 2
                else: it = io = 22.0
                gl.append((w, tm, op, g['home'], it, it - io, it + io, g['dome'], 0.0, g['div']))
            games[pid] = gl
        U = CA.upcoming(S, N, {p: m['pos'] for p, m in cut.items()}, games)
        now = tt.reset_index(); U = U.drop(columns=[c for c in U.columns if c.endswith('_t')]).merge(now.drop(columns=['week']), on=['season', 'team'], how='left')
        U = U.merge(now.drop(columns=['week']).rename(columns={c: 'o_' + c for c in now.columns if c.endswith('_t')}).rename(columns={'team': 'opp'}), on=['season', 'opp'], how='left')
        U['dvp'] = [CA.dvp(S, N, o, p) for o, p in zip(U.opp, U.pos)]; U['q'] = 0.0; U['prac'] = np.nan
        U['dc'] = U.player_id.map(CA.DC[(CA.DC.season == S) & (CA.DC.week == N)].set_index('gsis_id').dc).astype(float)
        mu = {}
        for pos in FM.POS:
            u = U[U.pos == pos]
            if len(u): mu.update(pd.Series(M.next(pos, u), index=u.player_id.values).groupby(level=0).mean().to_dict())
        NEW[(S, N)] = {p: dict(m, mu_old=m['mu'], mu=float(mu.get(p, m['mu']))) for p, m in cut.items()}
        print(S, N, len(cut), round(time.time() - t0), flush=True)
if not REUSE: pickle.dump(NEW, open(os.path.join(BT, 'value_checkpoints_v5.pkl'), 'wb'))
# ---- scoring (the same value formula as the site: spread 0.5 x R, 15% waiver-level VORP, 60% experts)
src = open(os.path.join(BT, 'bt_value_eval.py')).read(); src = src[:src.index('TR = {}')].replace("C = pickle.load(open(os.path.join(BT, 'value_checkpoints.pkl'), 'rb'))", 'C = {}')
G_ = {'__file__': os.path.join(BT, 'bt_value_eval.py')}; exec(src, G_)   # the truth simulation from bt_value_eval.py
simulate, POS, SLOTS, COMP, NT, NL = (G_[k] for k in ('simulate', 'POS', 'SLOTS', 'COMP', 'NT', 'NL'))
C_OLD = {k: {p: dict(m, mu=m['mu_old']) for p, m in c.items()} for k, c in NEW.items()}
TR_NEW = {}
for key, cut in sorted(NEW.items()):
    acc = {}
    for L in range(NL):
        for p, v in simulate(key, cut, hash((key, L)) % 10**6).items(): acc.setdefault(p, []).append(v)
    TR_NEW[key] = {p: float(np.mean(v)) for p, v in acc.items() if len(v) >= NL // 2}
def posPart(d, s): z = d / s; return d * norm.cdf(z) + s * norm.pdf(z)
def levels(cut):
    mb = {p: m['mu'] for p, m in cut.items()}; by = {q: sorted([p for p in cut if cut[p]['pos'] == q], key=lambda p: -mb[p]) for q in POS}
    cnt = {q: min(len(by[q]), NT*SLOTS[q]) for q in POS}
    for p in sorted([p for q in ('RB', 'WR', 'TE') for p in by[q][cnt[q]:]], key=lambda p: -mb[p])[:NT]: cnt[cut[p]['pos']] += 1
    return {q: mb[by[q][min(len(by[q]) - 1, cnt[q])]] for q in POS}, {q: mb[by[q][min(len(by[q]) - 1, NT*COMP[q])]] for q in POS}
def val(cut, base):
    Rs, Rw = levels(cut); R = Rs if base == 's' else Rw
    return {p: sum(.98 * .985**h * posPart(m['mu'] - R[m['pos']], max(.5, .5 * Rs[m['pos']])) for h, pl in enumerate(m['play']) if pl) for p, m in cut.items()}
def scale(V): top = sorted(V.values(), reverse=True)[:3]; ref = sum(top)/3 or 1; return {p: 100*v/ref for p, v in V.items()}
def on_curve(cut, V):
    ve = {}
    for q in POS:
        curve = sorted([V[p] for p in cut if cut[p]['pos'] == q], reverse=True); rk = sorted([p for p in cut if cut[p]['pos'] == q and cut[p]['ecr_p']], key=lambda p: cut[p]['ecr_p'])
        for i, p in enumerate(rk): ve[p] = curve[min(i, len(curve) - 1)]
        fl = curve[min(len(rk), len(curve) - 1)]
        for p in cut:
            if cut[p]['pos'] == q and p not in ve: ve[p] = min(V[p], fl)
    return ve
def bff(cut, w=.6):
    A = scale(val(cut, 's')); B = scale(val(cut, 'w')); V = {p: .85*A[p] + .15*B[p] for p in cut}
    if w == 0 or not any(m['ecr_p'] for m in cut.values()): return V
    ve = on_curve(cut, V); wp = lambda m: min(.95, w * (.85/.6 if m['g'] <= 2 else .72/.6 if m['pos'] == 'RB' else 1))
    return {p: (1 - wp(m))*V[p] + wp(m)*ve[p] for p, m in cut.items()}
def experts(cut): return on_curve(cut, bff(cut, 0))
def metrics(CC, TR, f):
    R2 = []; SP = []; dirs = []; BY = {}
    for key, cut in sorted(CC.items()):
        V = scale(f(cut)); T = TR[key]; ps = [p for p in T if p in V]; v = np.array([V[p] for p in ps]); t = np.array([T[p] for p in ps])
        r2 = float(np.corrcoef(v, t)[0, 1]**2); sp = float(spearmanr(v, t).correlation); R2.append(r2); SP.append(sp); rng = random.Random(1); d0 = len(dirs); n = len(ps)
        for _ in range(4000):
            i, j = rng.randrange(n), rng.randrange(n)
            if i != j and min(v[i], v[j]) >= 3 and (v[i] / v[j] >= 2 or v[j] / v[i] >= 2): dirs.append((v[i] > v[j]) == (t[i] > t[j]))
        BY.setdefault(str(key[0]), []).append((r2, sp, float(np.mean(dirs[d0:]))))
    return {'rank': round(float(np.mean(SP)), 4), 'lopsided_pct': round(100*float(np.mean(dirs)), 1), 'r2': round(float(np.mean(R2)), 4),
            'by_season': {s: {'r2': round(float(np.mean([x[0] for x in L])), 4), 'rank': round(float(np.mean([x[1] for x in L])), 4), 'lopsided': round(float(np.mean([x[2] for x in L])), 4)} for s, L in BY.items()}}
RES = {}
for tn, TR in (('truth: lineups by the previous projections', TR_OLD), ('truth: lineups by the new projections', TR_NEW)):
    RES[tn] = {'FantasyPros experts alone (same value scale)': metrics(NEW, TR, experts), 'BFF model alone (no experts)': metrics(NEW, TR, lambda c: bff(c, 0)),
               'BFF value, previous projections': metrics(C_OLD, TR, bff), 'BFF value (site)': metrics(NEW, TR, bff)}
    for k, v in RES[tn].items(): print(tn, '|', k, v, flush=True)
json.dump(RES, open(os.path.join(BT, 'results_value_v5.json'), 'w'), indent=1); print('saved', round(time.time() - t0))
