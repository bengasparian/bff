"""BFF research: how close BFF's predicted prop lines are to real posted lines, and the market calibration that fixed it.

Data (all in research/props/):
  real_lines_2026_w7.json        real week-7 2026 lines read from a public props page (passing, receiving, rushing yards)
  bff_lines_2026_w7_before.json  BFF's lines as published before this change
  espn_<season>.json.gz, sleeper_<season>.json.gz   ESPN's and Sleeper's public weekly projections, stat by stat
                                                    (fetched the same way the site's projection tracker reads them)
The new line for a stat = k x the average of ESPN's and Sleeper's projections (BFF's own stat projection only when neither
site projects the player); k sets the line where books set theirs (below the average for skewed stats). BFF's model stays
out of the line, so the picks test BFF's view against the market's.
Checks:
  1. week 7 2026: every rule is scored on players it never saw (leave one out) against the real lines;
  2. 2025: how often the overs hit at the calibrated lines (real books' prop overs hit a little under half the time);
  3. 2025: whether BFF's picks have an edge over lines like these (BFF's own model vs ESPN and Sleeper).
python research/bt_lines.py   (writes research/results_lines.json; a few seconds)"""
import os, sys, json, gzip, numpy as np, pandas as pd
BT = os.path.dirname(os.path.abspath(__file__)); RUN = os.path.dirname(BT); os.chdir(RUN); sys.path.insert(0, RUN)
PR = os.path.join(BT, 'props')
ids = pd.read_csv('db_playerids.csv', low_memory=False)
key = lambda v: str(int(v)) if isinstance(v, float) else str(v)
ME = {key(s): g for s, g in zip(ids.espn_id, ids.gsis_id) if s == s and isinstance(g, str)}
MS = {key(s): g for s, g in zip(ids.sleeper_id, ids.gsis_id) if s == s and isinstance(g, str)}
NAME = {g: n for g, n in zip(ids.gsis_id, ids.name) if isinstance(g, str)}
MK = ('py', 'ty', 'ry')


def site(season, src):
    D = json.load(gzip.open(os.path.join(PR, f'{src}_{season}.json.gz'), 'rt')); M = ME if src == 'espn' else MS
    return {int(w): {M[i]: v for i, v in d.items() if i in M} for w, d in D.items()}


def blend(e, s, m):
    """the market's view: the average of ESPN's and Sleeper's projections (either one alone if only one has him); BFF's own
    projection only when neither site projects him. BFF's model is kept out of the line so the picks can test it against
    the line (0 or missing = no forecast)."""
    xs = [v for v in (e, s) if v is not None and v > 0]
    if xs: return sum(xs) / len(xs)
    return m if m is not None and m > 0 else None


if __name__ == '__main__':
    R = {}
    # ---- 1. week 7 2026 against the real lines
    real = json.load(open(os.path.join(PR, 'real_lines_2026_w7.json'))); before = json.load(open(os.path.join(PR, 'bff_lines_2026_w7_before.json')))
    E26, S26 = site(2026, 'espn')[7], site(2026, 'sleeper')[7]
    BL = {(l['pid'], l['k']): l for l in before['lines']}
    byname = {}
    for g, n in NAME.items(): byname.setdefault(n, []).append(g)
    R['week7'] = {'source': real['source']}
    for k in MK:
        rows = []
        for n, v in real[k].items():
            g = next((x for x in byname.get(n, []) if x in E26 or x in S26 or (x, k) in BL), None)
            if not g: continue
            b = BL.get((g, k)); e = (E26.get(g) or {}).get(k); s = (S26.get(g) or {}).get(k)
            rows.append({'n': n, 'real': v, 'before': b['line'] if b else None, 'mm': b['mm'] if b else None, 'bl': blend(e, s, b['mm'] if b else None)})
        X = pd.DataFrame(rows)
        z = X[X.before.notna()]; old = float((z.real - z.before).abs().mean())
        y = X[X.bl.notna()]; err = []
        for i in y.index:
            k_ = float(np.median(y.real.drop(i) / y.bl.drop(i))); err.append(y.real[i] - (np.floor(k_ * y.bl[i]) + .5))
        kall = float(np.median(y.real / y.bl))
        same = y[y.index.isin(z.index)]
        R['week7'][k] = {'real_lines': len(X), 'before': {'n': len(z), 'avg_gap': round(old, 1), 'bias': round(float((z.real - z.before).mean()), 1)},
                         'after': {'n': len(y), 'avg_gap_leave_one_out': round(float(np.mean(np.abs(err))), 1), 'bias': round(float(np.mean(err)), 1)},
                         'after_same_players': round(float(np.mean([abs(e_) for e_, i in zip(err, y.index) if i in same.index])), 1), 'k': round(kall, 3)}
        print('week 7', k, R['week7'][k])
    # ---- 2. 2025: overs at the calibrated lines (ESPN + Sleeper only: BFF's 2025 stat projections are not stored)
    st = pd.read_parquet('stats_player_week_2025.parquet'); st = st[st.season_type == 'REG']
    A = {(r.player_id, int(r.week)): r for r in st.itertuples()}
    COL = {'py': 'passing_yards', 'ty': 'receiving_yards', 'ry': 'rushing_yards', 'rec': 'receptions'}
    THR = {'py': 150, 'ty': 15, 'ry': 7, 'rec': 1.5}
    K = {k: R['week7'][k]['k'] for k in MK}; K['rec'] = .95   # receptions: no real lines in the sample; .95 gives the same book-like over rate
    E25, S25 = site(2025, 'espn'), site(2025, 'sleeper')
    EP = {int(w): {ME[i]: v for i, v in d.items() if i in ME} for w, d in json.load(gzip.open(os.path.join(BT, 'hist', 'espn_2025.json.gz'), 'rt')).items()}
    SP = {int(w): {MS[i]: v for i, v in d.items() if i in MS} for w, d in json.load(gzip.open(os.path.join(BT, 'hist', 'sleeper_2025.json.gz'), 'rt')).items()}
    H = pd.read_parquet(os.path.join(BT, 'h_weekly_v5.parquet')); H = H[H.season == 2025].set_index(['player_id', 'week'])
    rows = []
    for w in range(2, 19):
        for k, col in COL.items():
            for g in set(E25.get(w, {})) | set(S25.get(w, {})):
                e = (E25[w].get(g) or {}).get(k); s = (S25[w].get(g) or {}).get(k)
                if not (e and s and e > 0 and s > 0) or (g, w) not in A: continue
                av = (e + s) / 2
                if av < THR[k]: continue
                fp = [x for x in ((EP.get(w) or {}).get(g), (SP.get(w) or {}).get(g)) if x and x > 0]
                mod = float(H.loc[(g, w)].model) if (g, w) in H.index else np.nan
                rows.append((w, k, av, float(getattr(A[(g, w)], col) or 0), mod, np.mean(fp) if len(fp) == 2 else np.nan))
    Z = pd.DataFrame(rows, columns=['w', 'k', 'avg', 'act', 'model', 'sitefp'])
    Z['line'] = np.floor(Z.k.map(K) * Z.avg) + .5
    R['overs_2025'] = {k: {'n': int((Z.k == k).sum()), 'over_pct': round(float((Z[Z.k == k].act > Z[Z.k == k].line).mean() * 100), 1)} for k in COL}
    R['k'] = K
    print('2025 overs at calibrated lines', R['overs_2025'])
    # ---- 3. picks against lines like these: BFF's model vs ESPN and Sleeper (fantasy points), 2025
    P = Z[Z.model.notna() & Z.sitefp.notna()].copy(); P['r'] = P.model / P.sitefp
    R['picks_2025'] = {}
    for t in (.1, .15):
        o = P[P.r > 1 + t]; u = P[P.r < 1 - t]; uy = u[u.k.isin(MK)]; ally = P[P.k.isin(MK)]
        R['picks_2025'][f'gap_{int(t*100)}'] = {'overs': {'n': len(o), 'hit_pct': round(float((o.act > o.line).mean() * 100), 1)},
                                               'unders_all': {'n': len(u), 'hit_pct': round(float((u.act < u.line).mean() * 100), 1)},
                                               'unders_yards': {'n': len(uy), 'hit_pct': round(float((uy.act < uy.line).mean() * 100), 1),
                                                                'by': {k: round(float((uy[uy.k == k].act < uy[uy.k == k].line).mean() * 100), 1) for k in MK}},
                                               'every_yards_under': round(float((ally.act < ally.line).mean() * 100), 1)}
    print('2025 picks', json.dumps(R['picks_2025']))
    json.dump(R, open(os.path.join(BT, 'results_lines.json'), 'w'), indent=1)
    # ---- 4. how often the over hit, by stat and by BFF's model vs ESPN and Sleeper (the 'chance' each line shows)
    P['rb'] = pd.cut(P.r, [0, .9, 1.1, 99], labels=['below', 'level', 'above'])
    R['over_rate_2025'] = {k: {str(b): {'n': int(len(g)), 'over': round(float((g.act > g.line).mean()), 3)} for b, g in P[P.k == k].groupby('rb', observed=True)} for k in COL}
    print('over rate by BFF vs sites', json.dumps(R['over_rate_2025']))
    json.dump(R, open(os.path.join(BT, 'results_lines.json'), 'w'), indent=1)
