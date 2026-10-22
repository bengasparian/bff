"""BFF research, part 2 of the trade-value backtest: scores value formulas against simulated-league truth.
Run after research/bt_value_build.py:   python research/bt_value_eval.py   (about 5 minutes)
Originally: score value formulas against the simulated-league truth. Prints, per variant:
R2 / Spearman with truth, position bias (truth minus value-implied truth, % of a top-50 player's truth),
QB-vs-others coin flip on near-equal values (50% = unbiased), and the share of 2x-lopsided calls the truth agrees with."""
import os, pickle, random, numpy as np, json
from scipy.stats import spearmanr, norm
BT = os.path.dirname(os.path.abspath(__file__))
C = pickle.load(open(os.path.join(BT, 'value_checkpoints.pkl'), 'rb'))
POS = ['QB', 'RB', 'WR', 'TE']; SLOTS = {'QB': 1, 'RB': 2, 'WR': 2, 'TE': 1}; COMP = json.loads(os.environ.get('COMP', '{"QB": 2, "RB": 5, "WR": 6, "TE": 2}')); NT = 12; NL = 10
def lineup(players, cut, w):
    """points of the best projected lineup in week index w (players: list of ids)"""
    av = [p for p in players if cut[p]['play'][w]]; tot = 0.0; used = set()
    for q, k in SLOTS.items():
        c = sorted([p for p in av if cut[p]['pos'] == q], key=lambda p: -cut[p]['mu'])[:k]
        for p in c: tot += cut[p]['y'][w]; used.add(p)
    fl = sorted([p for p in av if p not in used and cut[p]['pos'] != 'QB'], key=lambda p: -cut[p]['mu'])[:1]
    for p in fl: tot += cut[p]['y'][w]
    return tot
def simulate(key, cut, seed):
    rng = random.Random(seed); ids = list(cut)
    # market rank: consensus overall rank, else after the ranked players by projection
    ranked = sorted([p for p in ids if cut[p]['ecr_o']], key=lambda p: cut[p]['ecr_o'])
    rest = sorted([p for p in ids if not cut[p]['ecr_o']], key=lambda p: -cut[p]['mu'])
    if len(ranked) < 150: ranked = sorted(ids, key=lambda p: -cut[p]['mu']); rest = []
    order = ranked + rest; mr = {p: i + 1 for i, p in enumerate(order)}
    noisy = sorted(ids, key=lambda p: mr[p] + rng.gauss(0, .15*mr[p] + 3))
    teams = [[] for _ in range(NT)]; cnt = [{q: 0 for q in POS} for _ in range(NT)]; pool = list(noisy)
    for rnd in range(sum(COMP.values())):
        for t in (range(NT) if rnd % 2 == 0 else range(NT - 1, -1, -1)):
            for k, p in enumerate(pool):
                if cnt[t][cut[p]['pos']] < COMP[cut[p]['pos']]: teams[t].append(p); cnt[t][cut[p]['pos']] += 1; pool.pop(k); break
    fa = {q: max([p for p in pool if cut[p]['pos'] == q], key=lambda p: cut[p]['mu']) for q in POS}
    W = len(cut[ids[0]]['play']); truth = {}
    for T in teams:
        base = sum(lineup(T, cut, w) for w in range(W))
        for p in T:
            T2 = [x for x in T if x != p] + [fa[cut[p]['pos']]]
            truth[p] = base - sum(lineup(T2, cut, w) for w in range(W))
    return truth
TR = {}
for key, cut in sorted(C.items()):
    acc = {}
    for L in range(NL):
        for p, v in simulate(key, cut, hash((key, L)) % 10**6).items(): acc.setdefault(p, []).append(v)
    TR[key] = {p: float(np.mean(v)) for p, v in acc.items() if len(v) >= NL // 2}
pickle.dump(TR, open(os.path.join(BT, 'value_truth.pkl'), 'wb'))
def posPart(d, s): z = d / s; return d * norm.cdf(z) + s * norm.pdf(z)
def levels(cut):
    mb = {p: m['mu'] for p, m in cut.items()}; by = {q: sorted([p for p in cut if cut[p]['pos'] == q], key=lambda p: -mb[p]) for q in POS}
    cnt = {q: min(len(by[q]), NT*SLOTS[q]) for q in POS}
    rest = sorted([p for q in ('RB', 'WR', 'TE') for p in by[q][cnt[q]:]], key=lambda p: -mb[p])[:NT]
    for p in rest: cnt[cut[p]['pos']] += 1
    Rs = {q: mb[by[q][min(len(by[q]) - 1, cnt[q])]] for q in POS}
    Rw = {q: mb[by[q][min(len(by[q]) - 1, NT*COMP[q])]] for q in POS}
    return Rs, Rw
def val(cut, base, s_rel=.2, s_abs=None, mode='pp'):
    Rs, Rw = levels(cut); R = Rs if base == 's' else Rw; out = {}
    for p, m in cut.items():
        r = R[m['pos']]; s = (s_abs[m['pos']] if isinstance(s_abs, dict) else s_abs) if s_abs else max(.5, s_rel * (Rs[m['pos']]))
        per = posPart(m['mu'] - r, s) if mode == 'pp' else max(0.0, m['mu'] - r)
        out[p] = sum(.98 * .985**h * per for h, pl in enumerate(m['play']) if pl)
    return out
def scale(V):
    top = sorted(V.values(), reverse=True)[:3]; ref = sum(top)/3 or 1; return {p: 100*v/ref for p, v in V.items()}
def consensus(cut, V, wbase=.6):
    ve = {}
    for q in POS:
        curve = sorted([V[p] for p in cut if cut[p]['pos'] == q], reverse=True)
        rk = sorted([p for p in cut if cut[p]['pos'] == q and cut[p]['ecr_p']], key=lambda p: cut[p]['ecr_p'])
        for i, p in enumerate(rk): ve[p] = curve[min(i, len(curve) - 1)]
        fl = curve[min(len(rk), len(curve) - 1)]
        for p in cut:
            if cut[p]['pos'] == q and p not in ve: ve[p] = min(V[p], fl)
    if not any(cut[p]['ecr_p'] for p in cut): return V
    wp = lambda m: min(.95, wbase * (.85/.6 if m['g'] <= 2 else .72/.6 if m['pos'] == 'RB' else 1))
    return {p: (1 - wp(cut[p]))*V[p] + wp(cut[p])*ve[p] for p in cut}
PER = []
def metrics(Vf):
    R2 = []; SP = []; bias = {q: [] for q in POS}; qb = []; dirs = []; cdir = []
    for key, cut in sorted(C.items()):
        V = scale(Vf(cut)); T = TR[key]; ps = [p for p in T if p in V]; d0 = len(dirs)
        v = np.array([V[p] for p in ps]); t = np.array([T[p] for p in ps])
        R2.append(np.corrcoef(v, t)[0, 1]**2); SP.append(spearmanr(v, t).correlation)
        b = (v @ t) / (v @ v); top = np.sort(t)[-50:].mean()
        for q in POS:
            m_ = np.array([cut[p]['pos'] == q for p in ps])
            if m_.sum(): bias[q].append(float(np.mean(t[m_] - b*v[m_]) / top * 100))
        rng = random.Random(1); n = len(ps)
        for _ in range(4000):
            i, j = rng.randrange(n), rng.randrange(n)
            if i == j: continue
            vi, vj = v[i], v[j]
            if min(vi, vj) < 3: continue
            qi, qj = cut[ps[i]]['pos'] == 'QB', cut[ps[j]]['pos'] == 'QB'
            if qi != qj and .9 <= vi / vj <= 1.1: qb.append((t[i] > t[j]) == qi)
            if vi / vj >= 2 or vj / vi >= 2: dirs.append((vi > vj) == (t[i] > t[j]))
        cdir.append(float(np.mean(dirs[d0:])))
    PER.append(R2)
    return dict(r2=round(float(np.mean(R2)), 4), rho=round(float(np.mean(SP)), 4), qb_wins=round(float(np.mean(qb)), 3), qb_n=len(qb),
                dir=round(float(np.mean(dirs)), 4), dir_pct=round(100 * float(np.mean(dirs)), 1), n_pairs=len(dirs), dir_checkpoints=[round(x, 4) for x in cdir],
                bias={q: round(float(np.mean(bias[q])), 1) for q in POS})
def blend(cut, lam, s_rel=.2, cons=False, wbase=.6, mode='pp', s_abs=None):
    A = scale(val(cut, 's', s_rel, s_abs=s_abs, mode=mode)); B = scale(val(cut, 'w', s_rel, s_abs=s_abs, mode=mode)); V = {p: (1 - lam)*A[p] + lam*B[p] for p in cut}
    return consensus(cut, V, wbase) if cons else V

def cons_only(cut, overall=False):
    """the expert consensus alone, put on BFF's value scale (k-th ranked gets the k-th highest BFF value)"""
    V = blend(cut, .15)
    if overall:
        curve = sorted(V.values(), reverse=True); rk = sorted([p for p in cut if cut[p]['ecr_o']], key=lambda p: cut[p]['ecr_o'])
        out = {p: curve[min(i, len(curve) - 1)] for i, p in enumerate(rk)}; fl = curve[min(len(rk), len(curve) - 1)]
        return {p: out.get(p, min(V[p], fl)) for p in cut}
    ve = {}
    for q in POS:
        curve = sorted([V[p] for p in cut if cut[p]['pos'] == q], reverse=True)
        rk = sorted([p for p in cut if cut[p]['pos'] == q and cut[p]['ecr_p']], key=lambda p: cut[p]['ecr_p'])
        for i, p in enumerate(rk): ve[p] = curve[min(i, len(curve) - 1)]
        fl = curve[min(len(rk), len(curve) - 1)]
        for p in cut:
            if cut[p]['pos'] == q and p not in ve: ve[p] = min(V[p], fl)
    return ve


def per_season(Vf):
    out = {}
    for S in (2023, 2024, 2025):
        R2 = []; SP = []; D = []
        for key, cut in sorted(C.items()):
            if key[0] != S: continue
            V = scale(Vf(cut)); T = TR[key]; ps = [p for p in T if p in V]; v = np.array([V[p] for p in ps]); t = np.array([T[p] for p in ps])
            R2.append(np.corrcoef(v, t)[0, 1]**2); SP.append(spearmanr(v, t).correlation); rng = random.Random(1); n = len(ps)
            for _ in range(4000):
                i, j = rng.randrange(n), rng.randrange(n)
                if i == j or min(v[i], v[j]) < 3: continue
                if v[i] / v[j] >= 2 or v[j] / v[i] >= 2: D.append((v[i] > v[j]) == (t[i] > t[j]))
        out[S] = {'r2': round(float(np.mean(R2)), 4), 'rho': round(float(np.mean(SP)), 4), 'dir': round(float(np.mean(D)), 4), 'dir_pct': round(100 * float(np.mean(D)), 1)}
    return out
VAR = [('FantasyPros experts alone', cons_only), ('BFF model alone (no experts)', lambda c: blend(c, .15)),
       ('BFF value, old spread 0.2 x R', lambda c: blend(c, .15, cons=True)), ('BFF value (site: spread 0.5 x R)', lambda c: blend(c, .15, s_rel=.5, cons=True))] + \
      [(f'spread {s} x R', (lambda s: lambda c: blend(c, .15, s_rel=s, cons=True))(s)) for s in (.1, .3, .75, 1.0)] + \
      [(f'experts {int(w*100)}% (spread 0.5 x R)', (lambda w: lambda c: blend(c, .15, s_rel=.5, cons=True, wbase=w))(w)) for w in (.4, .5, .7, .8)] + \
      [(f'VORP {int(l*100)}% (spread 0.5 x R)', (lambda l: lambda c: blend(c, l, s_rel=.5, cons=True))(l)) for l in (0, .3)]
res = {}
for nm, f in VAR:
    res[nm] = metrics(f); res[nm]['by_season'] = per_season(f); print(f"{nm:42s} {res[nm]}", flush=True)
# at how many of the 15 checkpoints each version called more lopsided trades right than the experts / the old spread
for nm in res:
    for ref, lab in (('FantasyPros experts alone', 'dir_beats_experts'), ('BFF value, old spread 0.2 x R', 'dir_beats_old_spread')):
        res[nm][lab] = sum(a > b for a, b in zip(res[nm]['dir_checkpoints'], res[ref]['dir_checkpoints']))
    print(f"{nm:42s} lopsided trades {res[nm]['dir']:.1%} ({res[nm]['n_pairs']} pairs); beats experts at {res[nm]['dir_beats_experts']} of 15"
          f" checkpoints, old spread at {res[nm]['dir_beats_old_spread']} of 15", flush=True)
json.dump(res, open(os.path.join(BT, 'results_value.json'), 'w'), indent=1)
