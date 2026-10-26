"""BFF research: the new prop markets (Oct 25 2026): pass attempts, completions, interceptions, rush attempts, targets,
anytime and first-half touchdowns. (Pass+rush and rush+rec yards: the real-line pages had no rows for week 7, so those
combos wait for real lines to check them against.)

Data: ESPN's and Sleeper's weekly projections for 2025 and 2026 (research/props/espn_*.json.gz, sleeper_*.json.gz:
pass attempts, carries, targets and the yardage stats), nflverse weekly stats (what happened), nflverse play-by-play
(which quarter each touchdown came in), the nflverse schedule (Vegas implied team totals) and real week-7 2026 lines
read by hand (research/props/real_lines_2026_w7_more.json).

1. Count lines (pass attempts, rush attempts, completions, targets): the market's projection (the average
   of ESPN's and Sleeper's; completions = projected attempts x the passer's completion rate) through a rule fit to the
   real lines, every rule scored on players it never saw (leave one out). Targets: books rarely post them, so the rule
   is the one that makes 2025's overs hit as often as receptions' do at BFF's receptions lines.
2. 2025 (weeks 2-18) and 2026 (weeks 2-7): how often the over hit at those lines, and whether BFF's picks signal (its
   own model 10%+ below or above ESPN and Sleeper) beats them; a market gets picks only at 55%+ in BOTH seasons.
3. Interceptions and touchdowns (yes/no markets): a rate per game (interceptions: projected attempts x the passer's
   interception rate, shrunk to the league's; touchdowns: projected carries and targets x touchdown rates by position,
   the Vegas team total and the player's own touchdowns per opportunity, shrunk), fit on 2025 by Poisson likelihood and
   checked on 2026 (it never saw): predicted vs actual by tenths. First-half touchdowns: the share of each position's
   touchdowns scored in the first half (2024-2025 play-by-play) times the game rate.
4. The spread of outcomes around each count projection (actual / projection, 5th to 95th percentile), for chances at
   other lines.
python research/bt_props_more.py   (writes research/results_props_more.json; under a minute)"""
import os, sys, json, gzip, math, re, unicodedata, numpy as np, pandas as pd
from scipy.optimize import minimize
BT = os.path.dirname(os.path.abspath(__file__)); RUN = os.path.dirname(BT); os.chdir(RUN); sys.path.insert(0, RUN)
PR = os.path.join(BT, 'props'); PBP = '/home/claude/work/bt3/data' if os.path.isdir('/home/claude/work/bt3/data') else os.path.join(BT, 'pbp')
ids = pd.read_csv('db_playerids.csv', low_memory=False)
key = lambda v: str(int(v)) if isinstance(v, float) else str(v)
ME = {key(s): g for s, g in zip(ids.espn_id, ids.gsis_id) if s == s and isinstance(g, str)}
MS = {key(s): g for s, g in zip(ids.sleeper_id, ids.gsis_id) if s == s and isinstance(g, str)}
NAME = {g: n for g, n in zip(ids.gsis_id, ids.name) if isinstance(g, str)}
norm = lambda s: re.sub(r'[^a-z]', '', re.sub(r'\b(jr|sr|ii|iii|iv|v)\b', '', unicodedata.normalize('NFKD', s).lower().replace('.', '')))
BYNAME = {}
for g, n in NAME.items(): BYNAME.setdefault(norm(n), []).append(g)
fl = lambda v: math.floor(v) + .5
R = {}


def site(season, src):
    D = json.load(gzip.open(os.path.join(PR, f'{src}_{season}.json.gz'), 'rt')); M = ME if src == 'espn' else MS
    return {int(w): {M[i]: v for i, v in d.items() if i in M} for w, d in D.items()}


def market(e, s, k):
    xs = [d[k] for d in (e, s) if d and (d.get(k) or 0) > 0]
    return sum(xs) / len(xs) if xs else None


def fpsite(season):
    """ESPN's and Sleeper's PPR projections (research/hist), for BFF's picks signal"""
    out = {}
    for src, M in (('espn', ME), ('sleeper', MS)):
        D = json.load(gzip.open(os.path.join(BT, 'hist', f'{src}_{season}.json.gz'), 'rt'))
        for w, d in D.items():
            for i, v in d.items():
                if i in M and v: out.setdefault((M[i], int(w)), []).append(float(v))
    return {k: sum(v) / len(v) for k, v in out.items() if len(v) == 2}


GM = pd.read_csv('games.csv', low_memory=False); GM = GM[GM.game_type == 'REG']
def implied(season):
    o = {}
    for g in GM[GM.season == season].itertuples():
        if pd.isna(g.total_line) or pd.isna(g.spread_line): continue
        o[(g.home_team, g.week)] = g.total_line / 2 + g.spread_line / 2; o[(g.away_team, g.week)] = g.total_line / 2 - g.spread_line / 2
    return o


def stats(season):
    s = pd.read_parquet(f'stats_player_week_{season}.parquet'); s = s[s.season_type == 'REG'].copy()
    for c in ('completions', 'attempts', 'passing_interceptions', 'carries', 'targets', 'rushing_tds', 'receiving_tds', 'special_teams_tds', 'passing_yards', 'rushing_yards', 'receiving_yards', 'receptions'):
        s[c] = s[c].fillna(0)
    s['td'] = s.rushing_tds + s.receiving_tds + s.special_teams_tds
    s['team_'] = s['team'] if 'team' in s.columns else s['recent_team']
    return s


def first_half_tds(season):
    p = pd.read_parquet(os.path.join(PBP, f'pbp_{season}.parquet'), columns=['season_type', 'week', 'qtr', 'td_player_id'])
    p = p[(p.season_type == 'REG') & p.td_player_id.notna()]
    return {'h1': p[p.qtr <= 2].groupby(['td_player_id', 'week']).size().to_dict(), 'all': p.groupby(['td_player_id', 'week']).size().to_dict()}


def build(season, prev):
    """one row per player and week with both sites' projections, the actual stats, the Vegas total and his priors"""
    E, S_ = site(season, 'espn'), site(season, 'sleeper'); ST = stats(season); PV = stats(prev); IT = implied(season); FH = first_half_tds(season)
    FP = fpsite(season)
    H = pd.read_parquet(os.path.join(BT, 'h_weekly_v5.parquet')); H = H[H.season == season].set_index(['player_id', 'week'])
    pv = PV.groupby('player_id')[['completions', 'attempts', 'passing_interceptions', 'carries', 'targets', 'td']].sum()
    pos = ST.drop_duplicates('player_id', keep='last').set_index('player_id').position.to_dict()
    pos.update({g: p for g, p in PV.drop_duplicates('player_id', keep='last').set_index('player_id').position.items() if g not in pos})
    ST = ST.sort_values('week'); rows = []
    cum = {}
    for w in range(1, 19):
        wk = ST[ST.week == w]
        for r in wk.itertuples():
            e = (E.get(w) or {}).get(r.player_id); s = (S_.get(w) or {}).get(r.player_id)
            c = cum.get(r.player_id, dict(n=0, completions=0, attempts=0, passing_interceptions=0, carries=0, targets=0, td=0, passing_yards=0, rushing_yards=0, receiving_yards=0, receptions=0))
            if w >= 2 and (e or s):
                pr = pv.loc[r.player_id].to_dict() if r.player_id in pv.index else {}
                mod = float(H.loc[(r.player_id, w)].model) if (r.player_id, w) in H.index else np.nan
                rows.append(dict(season=season, w=w, g=r.player_id, pos=pos.get(r.player_id, r.position), team=r.team_, it=IT.get((r.team_, w), np.nan),
                                 patt=market(e, s, 'patt'), car=market(e, s, 'car'), tg=market(e, s, 'tg'), py=market(e, s, 'py'), ry=market(e, s, 'ry'), ty=market(e, s, 'ty'), rec=market(e, s, 'rec'),
                                 a_att=r.attempts, a_cmp=r.completions, a_int=r.passing_interceptions, a_car=r.carries, a_tg=r.targets, a_td=r.td,
                                 a_td1=FH['h1'].get((r.player_id, w), 0), a_py=r.passing_yards, a_ry=r.rushing_yards, a_ty=r.receiving_yards,
                                 c_n=c['n'], c_att=c['attempts'], c_cmp=c['completions'], c_int=c['passing_interceptions'], c_car=c['carries'], c_tg=c['targets'], c_td=c['td'],
                                 c_py=c['passing_yards'], c_ry=c['rushing_yards'], c_ty=c['receiving_yards'],
                                 p_att=pr.get('attempts', 0), p_cmp=pr.get('completions', 0), p_int=pr.get('passing_interceptions', 0), p_car=pr.get('carries', 0), p_tg=pr.get('targets', 0), p_td=pr.get('td', 0),
                                 model=mod, sitefp=FP.get((r.player_id, w), np.nan)))
            for k in c:
                if k == 'n': c[k] += 1
                else: c[k] += float(getattr(r, k))
            cum[r.player_id] = c
    return pd.DataFrame(rows)


if __name__ == '__main__':
    X = pd.concat([build(2025, 2024), build(2026, 2025)], ignore_index=True)
    X['r'] = X.model / X.sitefp; X['bin'] = pd.cut(X.r, [0, .9, 1.1, 99], labels=['below', 'level', 'above'])
    print('rows', len(X), X.groupby('season').size().to_dict())
    # ---------------- interceptions: a Poisson rate per game
    LG = {}
    q25 = X[(X.season == 2025) & (X.pos == 'QB') & (X.patt >= 20)]
    LG['int'] = float(q25.a_int.sum() / q25.a_att.sum()); LG['cmp'] = float(q25.a_cmp.sum() / q25.a_att.sum())
    def int_rate(d, W, pw):
        return (d.c_int + pw * d.p_int + LG['int'] * W) / (d.c_att + pw * d.p_att + W)
    def nll_int(par, d):
        W, pw, sc = math.exp(par[0]), 1 / (1 + math.exp(-par[1])), math.exp(par[2])
        lam = sc * d.patt * int_rate(d, W, pw); return float((lam - d.a_int * np.log(lam)).sum())
    QB = X[(X.pos == 'QB') & (X.patt >= 20) & (X.a_att >= 10)]
    fit = minimize(nll_int, [math.log(150), 0.0, 0.0], args=(QB[QB.season == 2025],), method='Nelder-Mead', options={'maxiter': 4000, 'xatol': 1e-6, 'fatol': 1e-6})
    W_, pw_, sc_ = math.exp(fit.x[0]), 1 / (1 + math.exp(-fit.x[1])), math.exp(fit.x[2])
    def calib(p, y, n=5):
        o = pd.DataFrame({'p': p, 'y': y}).sort_values('p'); o['b'] = pd.qcut(o.p, n, labels=False, duplicates='drop')
        return [[round(float(g.p.mean()), 3), round(float(g.y.mean()), 3), int(len(g))] for _, g in o.groupby('b')]
    out = {'league_rate_2025': round(LG['int'], 4), 'shrink_attempts': round(W_, 1), 'last_season_weight': round(pw_, 3), 'scale': round(sc_, 3)}
    for ss in (2025, 2026):
        d = QB[QB.season == ss]; lam = sc_ * d.patt * int_rate(d, W_, pw_); p1 = 1 - np.exp(-lam); y = (d.a_int >= 1).astype(float)
        base = float(y.mean()); brier = float(((p1 - y) ** 2).mean()); brier0 = float(((base - y) ** 2).mean())
        out[str(ss)] = {'n': int(len(d)), 'predicted_any': round(float(p1.mean()), 3), 'actual_any': round(base, 3), 'brier': round(brier, 4), 'brier_flat': round(brier0, 4),
                        'by_fifths': calib(p1, y)}
    # against the books' week-7 prices (no-vig chance of 1+ interception), BFF's chance for the same passers
    imp = lambda o: -o / (-o + 100) if o < 0 else 100 / (o + 100)
    RLi = json.load(open(os.path.join(PR, 'real_lines_2026_w7_more.json'))).get('int') or {}
    E7_, S7_ = site(2026, 'espn')[7], site(2026, 'sleeper')[7]
    st26_ = stats(2026); c26_ = st26_[st26_.week < 7].groupby('player_id')[['passing_interceptions', 'attempts']].sum(); p25_ = stats(2025).groupby('player_id')[['passing_interceptions', 'attempts']].sum()
    cmpb = []
    for n, (l0, oo, l1, uo) in RLi.items():
        g = next((g for g in BYNAME.get(norm(n), []) if g in set(E7_) | set(S7_)), None); a = market(E7_.get(g), S7_.get(g), 'patt') if g else None
        if not a: continue
        cc = c26_.loc[g] if g in c26_.index else {'passing_interceptions': 0, 'attempts': 0}; pp = p25_.loc[g] if g in p25_.index else {'passing_interceptions': 0, 'attempts': 0}
        ir = (cc['passing_interceptions'] + pw_ * pp['passing_interceptions'] + LG['int'] * W_) / (cc['attempts'] + pw_ * pp['attempts'] + W_)
        bk = imp(oo) / (imp(oo) + imp(uo)); cmpb.append((n, round(1 - math.exp(-sc_ * a * ir), 3), round(bk, 3)))
    if cmpb:
        out['books_week7'] = {'n': len(cmpb), 'bff_mean': round(float(np.mean([b for _, b, _ in cmpb])), 3), 'books_mean': round(float(np.mean([k for *_, k in cmpb])), 3),
                              'mean_gap': round(float(np.mean([abs(b - k) for _, b, k in cmpb])), 3), 'books_spread': [round(min(k for *_, k in cmpb), 3), round(max(k for *_, k in cmpb), 3)],
                              'rows': cmpb}
    R['int'] = out; print('int', json.dumps({k: v for k, v in out.items() if k != 'books_week7'}), json.dumps({k: v for k, v in (out.get('books_week7') or {}).items() if k != 'rows'}))
    # ---------------- touchdowns (rushing + receiving + returns): a Poisson rate per game
    TP = X[X.pos.isin(['QB', 'RB', 'WR', 'TE'])].copy(); TP['car'] = TP.car.fillna(0); TP['tg'] = TP.tg.fillna(0)
    TP = TP[(TP.car + TP.tg) >= 1.5]
    POSI = {'QB': 0, 'RB': 1, 'WR': 2, 'TE': 3}
    def td_lam(par, d):
        ac = np.exp(np.array(par[0:4]))[d.pos.map(POSI).values]; at = np.exp(np.array(par[4:8]))[d.pos.map(POSI).values]
        gam = par[8]; W = math.exp(par[9]); pw = 1 / (1 + math.exp(-par[10]))
        exp0 = ac * d.car.values + at * d.tg.values                                   # league-rate expectation from projected volume
        # the player's own touchdowns against what his past opportunities would give at league rates (shrunk)
        e_c = ac * (d.c_car.values + pw * d.p_car.values) + at * (d.c_tg.values + pw * d.p_tg.values)
        own = (d.c_td.values + pw * d.p_td.values + W) / (e_c + W)
        it = np.nan_to_num(d.it.values, nan=22.0)
        return exp0 * (it / 22) ** gam * own
    def nll_td(par, d):
        lam = np.maximum(td_lam(par, d), 1e-4); return float((lam - d.a_td.values * np.log(lam)).sum())
    p0 = [math.log(.03)] * 4 + [math.log(.04)] * 4 + [1.0, math.log(3), 0.0]
    fit = minimize(nll_td, p0, args=(TP[TP.season == 2025],), method='Powell', options={'maxiter': 20000, 'xtol': 1e-5, 'ftol': 1e-7})
    fit = minimize(nll_td, fit.x, args=(TP[TP.season == 2025],), method='Nelder-Mead', options={'maxiter': 20000, 'xatol': 1e-6, 'fatol': 1e-7})
    par = [float(v) for v in fit.x]
    # first-half share of touchdowns by position (2024 + 2025 play-by-play)
    h1 = {}
    for q in POSI:
        a = b = 0
        for ss in (2024, 2025):
            p = pd.read_parquet(os.path.join(PBP, f'pbp_{ss}.parquet'), columns=['season_type', 'qtr', 'td_player_id']); p = p[(p.season_type == 'REG') & p.td_player_id.notna()]
            st_ = stats(ss); pmap = st_.drop_duplicates('player_id').set_index('player_id').position
            pp = p.td_player_id.map(pmap); a += int(((pp == q) & (p.qtr <= 2)).sum()); b += int((pp == q).sum())
        h1[q] = round(a / b, 3)
    out = {'rates': {'carry': {q: round(math.exp(par[i]), 4) for q, i in POSI.items()}, 'target': {q: round(math.exp(par[4 + i]), 4) for q, i in POSI.items()}},
           'vegas_power': round(par[8], 3), 'shrink': round(math.exp(par[9]), 2), 'last_season_weight': round(1 / (1 + math.exp(-par[10])), 3), 'first_half_share': h1, 'par': [round(v, 5) for v in par]}
    for ss in (2025, 2026):
        d = TP[TP.season == ss]; lam = td_lam(par, d); p1 = 1 - np.exp(-lam); y = (d.a_td >= 1).astype(float)
        hh = d.pos.map(h1).values; ph = 1 - np.exp(-lam * hh); yh = (d.a_td1 >= 1).astype(float)
        out[str(ss)] = {'n': int(len(d)), 'anytime': {'predicted': round(float(p1.mean()), 3), 'actual': round(float(y.mean()), 3), 'brier': round(float(((p1 - y) ** 2).mean()), 4),
                                                     'brier_flat_by_position': round(float(((d.pos.map(y.groupby(d.pos).mean()) - y) ** 2).mean()), 4), 'by_fifths': calib(p1, y)},
                        'first_half': {'predicted': round(float(ph.mean()), 3), 'actual': round(float(yh.mean()), 3), 'brier': round(float(((ph - yh) ** 2).mean()), 4), 'by_fifths': calib(ph, yh)}}
    R['td'] = out; print('td', json.dumps(out))
    # ---------------- count lines and combos: over rates at simple rules (refit on real lines when they are read)
    X['cp'] = (X.c_cmp + .5 * X.p_cmp + LG['cmp'] * 100) / (X.c_att + .5 * X.p_att + 100); X['cmp'] = X.patt * X.cp
    X['pr'] = X.py.fillna(0) + X.ry.fillna(0); X['rr'] = X.ry.fillna(0) + X.ty.fillna(0); X['a_pr'] = X.a_py + X.a_ry; X['a_rr'] = X.a_ry + X.a_ty
    MKT = {'patt': ('patt', 'a_att', 'QB', 20), 'cmp': ('cmp', 'a_cmp', 'QB', 12), 'car': ('car', 'a_car', None, 2), 'tg': ('tg', 'a_tg', None, 2.5)}   # market, actual, position, smallest projection
    RL = json.load(open(os.path.join(PR, 'real_lines_2026_w7_more.json')))
    E7, S7 = site(2026, 'espn')[7], site(2026, 'sleeper')[7]
    st26 = stats(2026); c26 = st26[st26.week < 7].groupby('player_id')[['completions', 'attempts']].sum(); st25 = stats(2025).groupby('player_id')[['completions', 'attempts']].sum()
    def find(n, have): return next((g for g in BYNAME.get(norm(n), []) if g in have), None)
    def mk7(g, k):
        e, s = E7.get(g), S7.get(g)
        if k == 'cmp':
            a = market(e, s, 'patt')
            if not a: return None
            cc = c26.loc[g] if g in c26.index else {'completions': 0, 'attempts': 0}; pp = st25.loc[g] if g in st25.index else {'completions': 0, 'attempts': 0}
            return a * (cc['completions'] + .5 * pp['completions'] + LG['cmp'] * 100) / (cc['attempts'] + .5 * pp['attempts'] + 100)
        if k == 'pr': a, b = market(e, s, 'py'), market(e, s, 'ry'); return (a or 0) + (b or 0) if a else None
        if k == 'rr': a, b = market(e, s, 'ry'), market(e, s, 'ty'); return (a or 0) + (b or 0) if (a or b) else None
        return market(e, s, k)
    RULES = {}; R['lines'] = {}
    for k, (col, act, ps, mn) in MKT.items():
        out = {}
        rows = []
        for n, v in (RL.get(k) or {}).items():
            g = find(n, set(E7) | set(S7)); m = mk7(g, k) if g else None
            if m and m >= mn: rows.append((n, m, (v[0] + v[2]) / 2, v[0], v[2]))
        if len(rows) >= 8:
            m = np.array([r[1] for r in rows]); y = np.array([r[2] for r in rows])
            def fitk(mm, yy): return {'k': round(float(np.median(yy / mm)), 4)}
            def fitab(mm, yy): b, a = np.polyfit(mm, yy, 1); return {'a': round(float(b), 4), 'b': round(float(a), 3)}
            def ln(rule, x): return fl(rule['k'] * x) if 'k' in rule else fl(rule['a'] * x + rule['b'])
            best = None
            def fitflat(mm, yy): return {'k': 1.0}
            for nm, f_ in (('flat', fitflat), ('k', fitk), ('ab', fitab)):
                pred = [ln(f_(np.delete(m, i), np.delete(y, i)), m[i]) for i in range(len(m))]
                gap = float(np.mean(np.abs(np.array(pred) - y))); inr = int(sum(lo <= p <= hi for p, (_, _, _, lo, hi) in zip(pred, rows)))
                out[f'rule_{nm}'] = {'gap_leave_one_out': round(gap, 2), 'inside_books_range': inr, 'n': len(rows)}
                if best is None or gap < best[0] - .02: best = (gap, nm, f_(m, y))   # a fitted rule must beat the simpler one by more than 0.02
            RULES[k] = best[2]; out['rule'] = best[2]; out['books_range_width'] = round(float(np.mean([hi - lo for *_, lo, hi in rows])), 2)
            out['flat_market_gap'] = round(float(np.mean(np.abs(np.array([fl(x) for x in m]) - y))), 2)
        else:
            out['note'] = 'no real lines read yet'
        R['lines'][k] = out
    # targets: no real lines; the k that makes 2025 overs hit like receptions' do at BFF's receptions lines (41.4%)
    t25 = X[(X.season == 2025) & (X.tg >= MKT['tg'][3])]
    best = None
    for kk in np.arange(.80, 1.21, .005):
        ov = float((t25.a_tg > np.floor(kk * t25.tg) + .5).mean())
        if best is None or abs(ov - .414) < abs(best[1] - .414): best = (round(float(kk), 3), ov)
    if 'tg' not in RULES: RULES['tg'] = {'k': best[0]}; R['lines']['tg'] = {'rule': RULES['tg'], 'note': "no real lines: books rarely post targets; set so 2025 overs hit like receptions' (41.4%)", 'over_2025': round(best[1], 3)}
    for k, rule in RULES.items():
        col, act, ps, mn = MKT[k]
        d = X[(X[col] >= mn) & (X[col].notna())]
        if ps: d = d[d.pos == ps]
        d = d.copy(); d['line'] = [fl(rule['k'] * x) if 'k' in rule else fl(rule['a'] * x + rule['b']) for x in d[col]]
        d = d[d[act].notna()]
        info = {}
        for ss in (2025, 2026):
            q = d[d.season == ss]
            info[str(ss)] = {'n': int(len(q)), 'over': round(float((q[act] > q.line).mean()), 3),
                             'by_bin': {str(b): {'n': int(len(g_)), 'over': round(float((g_[act] > g_.line).mean()), 3)} for b, g_ in q.groupby('bin', observed=True)}}
        R['lines'][k]['backtest'] = info
    # the spread of outcomes around the market projection (actual / projection at 5%, 10% ... 95%, 2025 and 2026 pooled):
    # the page uses it for the chance at a line other than BFF's (your book's), as it does for the yardage stats
    R['spread'] = {}
    for k, (col, act, ps, mn) in MKT.items():
        d = X[(X[col] >= mn) & X[col].notna() & X[act].notna()]
        if ps: d = d[d.pos == ps]
        R['spread'][k] = {'n': int(len(d)), 'q': [round(float(v), 3) for v in np.quantile(d[act] / d[col], np.arange(.05, .951, .05))]}
    R['rules'] = RULES; R['league'] = {k: round(v, 4) for k, v in LG.items()}
    print(json.dumps(R['lines'], indent=1))
    json.dump(R, open(os.path.join(BT, 'results_props_more.json'), 'w'), indent=1)
