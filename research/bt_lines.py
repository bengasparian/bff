"""BFF research: how close BFF's predicted prop lines are to real posted lines, the market calibration that sets them, and
whether BFF's picks hold up against lines like these.

Data (all in research/props/):
  real_lines_2026_w7.json          sample A: real week-7 2026 lines read from a public props page (Oct 21-23; passing,
                                   receiving and rushing yards; one number per player, book not named)
  real_lines_2026_w7_sun.json      sample B: real week-7 lines read Sunday Oct 25 before kickoff from scoresandodds.com: for
                                   each player the lowest and the highest line posted across books (passing, receiving and
                                   rushing yards, receptions), and the main passing-TD line with its odds
  espn_<season>.json.gz, sleeper_<season>.json.gz   ESPN's and Sleeper's weekly stat projections (sample A and 2025)
  site_2026_w7_sun.json            ESPN's and Sleeper's week-7 projections when sample B was read
  bff_lines_2026_w7_before.json, bff_lines_2026_w7_sun_before.json   BFF's lines as published at each read (the 'before')
A line = the market's projection (the average of ESPN's and Sleeper's) put through a rule fit to the real lines:
  receiving yards: k x market; receptions: slope x market + intercept; rushing yards: also the player's season average
  (books lean on what he has done); passing yards: also the season average and the Vegas implied team total (Oct 25
  second refit: both cut the gap to the books on players and lines the fit never saw); rounded down to .5;
  passing TDs: 0.5 below a market projection of t1, 2.5 from t2, else 1.5 (books post 0.5 for low-scoring passers).
BFF's own model stays out of the line, so the picks test BFF's view against the market's.
Checks:
  1. both week-7 samples: every rule is scored on players it never saw (leave one out) against the real lines; sample B
     also counts how often a line lands inside the range the books posted;
  2. 2025: how often the overs hit at lines built this way (real books' prop overs hit a little under half the time);
  3. 2025: whether BFF's picks (BFF's own model 10%+ below or above ESPN and Sleeper) beat lines like these, and how far
     below the line an under pick still holds (a book's line can be lower than ours).
python research/bt_lines.py   (writes research/results_lines.json; a few seconds)"""
import os, sys, json, gzip, math, re, unicodedata, numpy as np, pandas as pd
BT = os.path.dirname(os.path.abspath(__file__)); RUN = os.path.dirname(BT); os.chdir(RUN); sys.path.insert(0, RUN)
PR = os.path.join(BT, 'props')
ids = pd.read_csv('db_playerids.csv', low_memory=False)
key = lambda v: str(int(v)) if isinstance(v, float) else str(v)
ME = {key(s): g for s, g in zip(ids.espn_id, ids.gsis_id) if s == s and isinstance(g, str)}
MS = {key(s): g for s, g in zip(ids.sleeper_id, ids.gsis_id) if s == s and isinstance(g, str)}
NAME = {g: n for g, n in zip(ids.gsis_id, ids.name) if isinstance(g, str)}
POS = {g: p for g, p in zip(ids.gsis_id, ids.position) if isinstance(g, str)}
norm = lambda s: re.sub(r'[^a-z]', '', re.sub(r'\b(jr|sr|ii|iii|iv|v)\b', '', unicodedata.normalize('NFKD', s).lower().replace('.', '')))
BYNAME = {}
for g, n in NAME.items(): BYNAME.setdefault(norm(n), []).append(g)
MK = ('py', 'ty', 'ry', 'rec')
OLD_K = {'py': .989, 'ty': .919, 'ry': .862, 'rec': .95}   # the rule before Oct 25 (k x market for every stat)
fl = lambda v: math.floor(v) + .5
# what each rule uses besides the market projection: sa = the player's average for the stat in his games this season
# before the line's week (the market's projection when he has none), it = his team's Vegas implied points (22 = typical)
FEAT = {'py': ['mk', 'sa', 'mkit'], 'ry': ['mk', 'sa'], 'rec': ['mk'], 'ty': None}
COLS = {'py': 'passing_yards', 'ty': 'receiving_yards', 'ry': 'rushing_yards', 'rec': 'receptions'}
def feats(mk, sa, it):
    sa = mk if sa is None or (isinstance(sa, float) and math.isnan(sa)) else sa; it = 22.0 if it is None or (isinstance(it, float) and math.isnan(it)) else it
    return {'mk': mk, 'sa': sa, 'mkit': mk * (it / 22 - 1)}


def site(season, src):
    D = json.load(gzip.open(os.path.join(PR, f'{src}_{season}.json.gz'), 'rt')); M = ME if src == 'espn' else MS
    return {int(w): {M[i]: v for i, v in d.items() if i in M} for w, d in D.items()}


def market(e, s, k):
    """the market's projection: the average of ESPN's and Sleeper's (either one alone if only one projects him)"""
    xs = [d[k] for d in (e, s) if d and (d.get(k) or 0) > 0]
    return sum(xs) / len(xs) if xs else None


def fit(rows, k):
    """the rule's constants from real lines, rows = [(features, real), ...]: receiving yards k = the median ratio of real
    line to market projection; the others by least squares on FEAT[k] plus an intercept: a x market + c x season
    average + d x market x (implied total / 22 - 1) + b. (Fitting the constants to the smallest average gap directly
    scored worse on players left out: it chases the rounding.)"""
    y = np.array([r[1] for r in rows], float)
    if FEAT[k] is None: m = np.array([r[0]['mk'] for r in rows], float); return {'k': round(float(np.median(y / m)), 4)}
    X = np.array([[r[0][f] for f in FEAT[k]] + [1.0] for r in rows], float); w, *_ = np.linalg.lstsq(X, y, rcond=None)
    out = {'a': round(float(w[0]), 4)}
    if 'sa' in FEAT[k]: out['c'] = round(float(w[FEAT[k].index('sa')]), 4)
    if 'mkit' in FEAT[k]: out['d'] = round(float(w[FEAT[k].index('mkit')]), 4)
    out['b'] = round(float(w[-1]), 3); return out


def line(rule, f):
    """the line from a rule and the features (a dict from feats, or just the market projection)"""
    if not isinstance(f, dict): f = feats(f, None, None)
    if 'k' in rule: return fl(rule['k'] * f['mk'])
    return fl(rule['a'] * f['mk'] + rule.get('c', 0) * f['sa'] + rule.get('d', 0) * f['mkit'] + rule['b'])


def ptd_line(t, mk):
    return .5 if mk < t['t1'] else 2.5 if mk >= t['t2'] else 1.5


def pover(lam, ln_):
    """chance of more than ln_ touchdowns when they arrive at rate lam (Poisson)"""
    return 1 - sum(math.exp(-lam) * lam ** i / math.factorial(i) for i in range(int(ln_) + 1))


def find(n, have):
    return next((g for g in BYNAME.get(norm(n), []) if g in have), None)


if __name__ == '__main__':
    R = {}
    # ---- 1. week 7 2026 against the real lines
    A = json.load(open(os.path.join(PR, 'real_lines_2026_w7.json'))); B = json.load(open(os.path.join(PR, 'real_lines_2026_w7_sun.json')))
    EA, SA = site(2026, 'espn')[7], site(2026, 'sleeper')[7]
    SB = json.load(open(os.path.join(PR, 'site_2026_w7_sun.json')))['p']
    BLA = {(l['pid'], l['k']): l for l in json.load(open(os.path.join(PR, 'bff_lines_2026_w7_before.json')))['lines']}
    BLB = {(l['pid'], l['k']): l for l in json.load(open(os.path.join(PR, 'bff_lines_2026_w7_sun_before.json')))['lines']}
    # season averages before week 7 (2026 weekly stats) and each team's week-7 implied total (nflverse schedule)
    S26 = pd.read_parquet('stats_player_week_2026.parquet'); S26 = S26[(S26.season_type == 'REG') & (S26.week < 7)]
    SA26 = S26.groupby('player_id')[list(COLS.values())].mean()
    tcol = 'team' if 'team' in S26.columns else 'recent_team'; TEAM26 = S26.sort_values('week').groupby('player_id')[tcol].last().to_dict()
    GM = pd.read_csv('games.csv', low_memory=False); GM = GM[GM.game_type == 'REG']
    def implied(season, week):
        o = {}
        for g_ in GM[(GM.season == season) & (GM.week == week)].itertuples():
            if pd.isna(g_.total_line) or pd.isna(g_.spread_line): continue
            o[g_.home_team] = g_.total_line / 2 + g_.spread_line / 2; o[g_.away_team] = g_.total_line / 2 - g_.spread_line / 2
        return o
    IT7 = implied(2026, 7)
    def f7(g, k, mk):
        sa = float(SA26.loc[g, COLS[k]]) if g in SA26.index else None
        return feats(mk, sa, IT7.get(TEAM26.get(g)))
    rows = []   # (sample, stat, gsis, features, real (mid), lo, hi, BFF line before)
    for k in MK:
        for n, v in (A.get(k) or {}).items():
            g = find(n, set(EA) | set(SA))
            mk = market(EA.get(g), SA.get(g), k) if g else None
            if mk: rows.append(('A', k, g, f7(g, k, mk), float(v), None, None, (BLA.get((g, k)) or {}).get('line')))
        for n, (lo, hi) in B[k].items():
            g = find(n, SB)
            mk = market((SB.get(g) or {}).get('e'), (SB.get(g) or {}).get('s'), k) if g else None
            if mk: rows.append(('B', k, g, f7(g, k, mk), (lo + hi) / 2, lo, hi, (BLB.get((g, k)) or {}).get('line')))
    X = pd.DataFrame(rows, columns=['smp', 'k', 'g', 'f', 'real', 'lo', 'hi', 'before']); X['mk'] = [f['mk'] for f in X.f]
    RULE = {}; R['week7'] = {'samples': {'A': A['source'], 'B': B['source']}}
    for k in MK:
        z = X[X.k == k].reset_index(drop=True)
        RULE[k] = fit(list(zip(z.f, z.real)), k)
        pred = []
        for i in z.index:
            r_ = fit(list(zip(z.f.drop(i), z.real.drop(i))), k); pred.append(line(r_, z.f[i]))
        z['after'] = pred; z['old'] = [fl(OLD_K[k] * m) for m in z.mk]
        out = {'rule': RULE[k], 'n': int(len(z))}
        for s_ in ('A', 'B'):
            q = z[z.smp == s_]
            if not len(q): continue
            d = {'n': int(len(q)), 'gap_after_leave_one_out': round(float((q.after - q.real).abs().mean()), 2), 'bias_after': round(float((q.after - q.real).mean()), 2),
                 'gap_old_rule': round(float((q.old - q.real).abs().mean()), 2)}
            pb = q[q.before.notna()]
            if len(pb): d['published_before'] = {'n': int(len(pb)), 'gap': round(float((pb.before - pb.real).abs().mean()), 2), 'bias': round(float((pb.before - pb.real).mean()), 2)}
            if s_ == 'B':
                d['inside_books_range'] = {'after': int(((q.after >= q.lo) & (q.after <= q.hi)).sum()), 'old_rule': int(((q.old >= q.lo) & (q.old <= q.hi)).sum())}
                d['books_range_width'] = round(float((q.hi - q.lo).mean()), 2)
            out[s_] = d
        R['week7'][k] = out
        print('week 7', k, json.dumps(out))
    # passing touchdowns (sample B: main line with odds)
    T = []
    for n, (ln_, oo, uo) in B['ptd'].items():
        g = find(n, SB); mk = market((SB.get(g) or {}).get('e'), (SB.get(g) or {}).get('s'), 'ptd') if g else None
        if mk: T.append((n, mk, ln_, (BLB.get((g, 'ptd')) or {}).get('line')))
    best = None
    for t1 in np.arange(.70, 1.21, .01):
        for t2 in np.arange(1.9, 2.81, .01):
            ok_ = sum(ptd_line({'t1': t1, 't2': t2}, m) == l for _, m, l, _ in T)
            if best is None or ok_ > best[0]: best = (ok_, [t1], [t2])
            elif ok_ == best[0]: best[1].append(t1); best[2].append(t2)
    # the middle of the best-scoring band (the cutoffs sit halfway between the closest real 0.5 and 1.5 lines)
    lo1 = max(m for _, m, l, _ in T if l == .5 and m < 1.0); hi1 = min(m for _, m, l, _ in T if l == 1.5)
    t1 = round((lo1 + hi1) / 2, 2)
    hi2 = max(m for _, m, l, _ in T if l == 1.5); t2 = round(max(hi2 + .05, 2.3), 2)
    RULE['ptd'] = {'t1': t1, 't2': t2}
    loo_ok = 0
    for i, (n, m, l, _) in enumerate(T):
        Ti = T[:i] + T[i + 1:]
        a1 = [mm for _, mm, ll, _ in Ti if ll == .5 and mm < 1.0]; b1 = [mm for _, mm, ll, _ in Ti if ll == 1.5]
        r_ = {'t1': (max(a1) + min(b1)) / 2, 't2': max(max(b1) + .05, 2.3)}
        loo_ok += ptd_line(r_, m) == l
    R['week7']['ptd'] = {'rule': RULE['ptd'], 'n': len(T), 'match': sum(ptd_line(RULE['ptd'], m) == l for _, m, l, _ in T), 'match_leave_one_out': loo_ok,
                         'published_before_match': sum(b == l for _, _, l, b in T if b is not None), 'published_before_n': sum(b is not None for *_, b in T),
                         'misses': [n for n, m, l, _ in T if ptd_line(RULE['ptd'], m) != l]}
    # the books' expected passing TDs, read from the odds (no-vig Poisson rate at the posted line), against the market projection
    imp = lambda o: -o / (-o + 100) if o < 0 else 100 / (o + 100)
    lam = []
    for n, (ln_, oo, uo) in B['ptd'].items():
        g = find(n, SB); mk = market((SB.get(g) or {}).get('e'), (SB.get(g) or {}).get('s'), 'ptd') if g else None
        if not mk: continue
        po = imp(oo) / (imp(oo) + imp(uo)); lo_, hi_ = .01, 8.0
        for _ in range(80):
            mid = (lo_ + hi_) / 2
            if pover(mid, ln_) < po: lo_ = mid
            else: hi_ = mid
        lam.append((mk, (lo_ + hi_) / 2))
    b1, b0 = np.polyfit([x for x, _ in lam], [y for _, y in lam], 1)
    R['week7']['ptd']['books_rate'] = {'a': round(float(b0), 3), 'b': round(float(b1), 3), 'n': len(lam),
                                       'note': "books' expected TDs = a + b x market projection (no-vig odds at the posted line, Poisson)"}
    print('week 7 ptd', R['week7']['ptd'])
    R['rule'] = RULE
    # ---- 2. 2025: overs at lines built this way
    st = pd.read_parquet('stats_player_week_2025.parquet'); st = st[st.season_type == 'REG']
    ACT = {(r.player_id, int(r.week)): r for r in st.itertuples()}
    COL = {'py': 'passing_yards', 'ty': 'receiving_yards', 'ry': 'rushing_yards', 'rec': 'receptions', 'ptd': 'passing_tds'}
    THR = {'py': 150, 'ty': 15, 'ry': 7, 'rec': 1.5}
    E25, S25 = site(2025, 'espn'), site(2025, 'sleeper')
    EP = {int(w): {ME[i]: v for i, v in d.items() if i in ME} for w, d in json.load(gzip.open(os.path.join(BT, 'hist', 'espn_2025.json.gz'), 'rt')).items()}
    SP = {int(w): {MS[i]: v for i, v in d.items() if i in MS} for w, d in json.load(gzip.open(os.path.join(BT, 'hist', 'sleeper_2025.json.gz'), 'rt')).items()}
    H = pd.read_parquet(os.path.join(BT, 'h_weekly_v5.parquet')); H = H[H.season == 2025].set_index(['player_id', 'week'])
    tc25 = 'team' if 'team' in st.columns else 'recent_team'; st = st.sort_values('week')
    PRIOR = {}   # (player, week) -> his averages for each stat over his 2025 games before that week
    for g_, q_ in st.groupby('player_id'):
        cs = q_[list(COLS.values())].fillna(0).cumsum(); n_ = np.arange(1, len(q_) + 1)
        for i_, w_ in enumerate(q_.week.tolist()): PRIOR[(g_, w_ + 1)] = (cs.iloc[i_] / n_[i_]).to_dict()
    # a week's averages are the ones after his last game before it (bye weeks in between carry them over)
    last_w = {}
    for (g_, w_) in sorted(PRIOR, key=lambda x: x[1]): last_w.setdefault(g_, []).append(w_)
    def prior(g_, w_):
        ws = [x for x in last_w.get(g_, []) if x <= w_]; return PRIOR[(g_, ws[-1])] if ws else None
    IT25 = {w_: implied(2025, w_) for w_ in range(1, 19)}
    rows = []
    for w in range(2, 19):
        for g in set(E25.get(w, {})) | set(S25.get(w, {})):
            e = E25[w].get(g) or {}; s = S25[w].get(g) or {}
            if (g, w) not in ACT: continue
            fp = [x for x in ((EP.get(w) or {}).get(g), (SP.get(w) or {}).get(g)) if x and x > 0]
            mod = float(H.loc[(g, w)].model) if (g, w) in H.index else np.nan
            for k in MK + ('ptd',):
                if not ((e.get(k) or 0) > 0 and (s.get(k) or 0) > 0): continue   # both sites project him (as books would post)
                av = (e[k] + s[k]) / 2
                if k == 'ptd':
                    if (e.get('py') or 0) + (s.get('py') or 0) < 2 * THR['py']: continue
                    ln_ = ptd_line(RULE['ptd'], av)
                else:
                    if av < THR[k]: continue
                    pa = prior(g, w); ln_ = line(RULE[k], feats(av, pa[COLS[k]] if pa else None, IT25[w].get(getattr(ACT[(g, w)], tc25))))
                    if k == 'py' and ln_ < 150.5: continue
                rows.append((w, k, POS.get(g), av, ln_, float(getattr(ACT[(g, w)], COL[k]) or 0), mod, np.mean(fp) if len(fp) == 2 else np.nan))
    Z = pd.DataFrame(rows, columns=['w', 'k', 'pos', 'avg', 'line', 'act', 'model', 'sitefp'])
    R['overs_2025'] = {k: {'n': int((Z.k == k).sum()), 'over_pct': round(float((Z[Z.k == k].act > Z[Z.k == k].line).mean() * 100), 1)} for k in COL}
    R['ptd_lines_2025'] = {str(l): {'n': int((Z[Z.k == 'ptd'].line == l).sum()), 'over_pct': round(float((Z[(Z.k == 'ptd') & (Z.line == l)].act > l).mean() * 100), 1)}
                           for l in (.5, 1.5, 2.5) if ((Z.k == 'ptd') & (Z.line == l)).any()}
    print('2025 overs at these lines', R['overs_2025'], R['ptd_lines_2025'])
    # ---- 3. picks: BFF's model vs ESPN and Sleeper (fantasy points), 2025
    P = Z[Z.model.notna() & Z.sitefp.notna()].copy(); P['r'] = P.model / P.sitefp
    YD = ('py', 'ty', 'ry')
    R['picks_2025'] = {}
    for t in (.1, .15):
        o = P[P.r > 1 + t]; u = P[P.r < 1 - t]; uy = u[u.k.isin(YD)]; ally = P[P.k.isin(YD)]
        R['picks_2025'][f'gap_{int(t*100)}'] = {
            'overs': {'n': len(o), 'hit_pct': round(float((o.act > o.line).mean() * 100), 1)},
            'unders_all': {'n': len(u), 'hit_pct': round(float((u.act < u.line).mean() * 100), 1)},
            'unders_yards': {'n': len(uy), 'hit_pct': round(float((uy.act < uy.line).mean() * 100), 1),
                             'by': {k: round(float((uy[uy.k == k].act < uy[uy.k == k].line).mean() * 100), 1) for k in YD}},
            'unders_by_stat': {k: {'n': int((u.k == k).sum()), 'hit_pct': round(float((u[u.k == k].act < u[u.k == k].line).mean() * 100), 1)} for k in MK + ('ptd',)},
            'overs_by_stat': {k: {'n': int((o.k == k).sum()), 'hit_pct': round(float((o[o.k == k].act > o[o.k == k].line).mean() * 100), 1)} for k in MK + ('ptd',)},
            'every_yards_under': round(float((ally.act < ally.line).mean() * 100), 1)}
    print('2025 picks', json.dumps(R['picks_2025']))
    # how far below our line an under pick still holds (55%+): a book's line can sit lower than ours
    u = P[(P.r < .9) & P.k.isin(YD)]; R['hold'] = {}
    for k in YD:
        q = u[u.k == k]; best_d = 0.0; curve = {}
        for d in np.arange(0, .1001, .005):
            h = float((q.act < np.floor(q.line * (1 - d)) + .5).mean()); curve[f'{d:.3f}'] = round(h, 3)
            if h >= .55: best_d = round(float(d), 3)
            else: break
        R['hold'][k] = {'n': int(len(q)), 'pct_below_line': best_d, 'curve': curve}
    print('under picks hold down to', {k: v['pct_below_line'] for k, v in R['hold'].items()})
    # ---- 4. how often the over hit, by stat and by BFF's model vs ESPN and Sleeper (the 'chance' each line shows)
    P['rb'] = pd.cut(P.r, [0, .9, 1.1, 99], labels=['below', 'level', 'above'])
    R['over_rate_2025'] = {k: {str(b): {'n': int(len(g_)), 'over': round(float((g_.act > g_.line).mean()), 3)} for b, g_ in P[P.k == k].groupby('rb', observed=True)} for k in COL}
    R['over_rate_2025_ptd_by_line'] = {f'{l}': {str(b): {'n': int(len(g_)), 'over': round(float((g_.act > g_.line).mean()), 3)} for b, g_ in P[(P.k == 'ptd') & (P.line == l)].groupby('rb', observed=True)}
                                       for l in (.5, 1.5, 2.5) if ((P.k == 'ptd') & (P.line == l)).any()}
    print('over rate by BFF vs sites', json.dumps(R['over_rate_2025']), json.dumps(R['over_rate_2025_ptd_by_line']))
    # passing-TD chance: the books' rate scaled per bin so the predicted overs match 2025 (any line: 0.5, 1.5 or 2.5)
    bk = R['week7']['ptd']['books_rate']; q = P[P.k == 'ptd'].copy(); q['lam'] = bk['a'] + bk['b'] * q.avg; R['ptd_scale'] = {}
    for b_, g_ in q.groupby('rb', observed=True):
        lo_, hi_ = .3, 2.0; want = float((g_.act > g_.line).mean())
        for _ in range(60):
            mid = (lo_ + hi_) / 2; got = float(np.mean([pover(l * mid, ln_) for l, ln_ in zip(g_.lam, g_.line)]))
            if got < want: lo_ = mid
            else: hi_ = mid
        R['ptd_scale'][str(b_)] = {'n': int(len(g_)), 'scale': round((lo_ + hi_) / 2, 3), 'over': round(want, 3)}
    unscaled = float(np.mean([pover(l, ln_) for l, ln_ in zip(q.lam, q.line)]))
    R['ptd_scale']['books_rate_alone'] = {'predicted_over': round(unscaled, 3), 'actual_over': round(float((q.act > q.line).mean()), 3)}
    print('passing-TD rate scale by bin', R['ptd_scale'])
    json.dump(R, open(os.path.join(BT, 'results_lines.json'), 'w'), indent=1)
