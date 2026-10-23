"""BFF research: BFF's weekly projections vs other sites' public projections (ESPN, Sleeper) and the FantasyPros weekly
expert consensus, on the same player-games, 2020-2026; the stacked projection BFF now publishes; and how much room any
projection has left (what perfect hindsight would score).

Run from the repository folder after research/bt_weekly_v5.py was run with BT_FROM=2020 BT_SAVE=1 (it writes
research/h_weekly_v5.parquet: every graded player-game with BFF's model projection, made by models trained only on earlier
seasons, and the experts' weekly ranks). ESPN's and Sleeper's past projections are in research/hist/ (fetched from their
public APIs by research/hist_fetch.py; ESPN re-scored to full PPR from its projected stats). Writes research/results_sites.json.

The stack (ff_produce.py does the same every run): within each position and week, every source's projection becomes a z-score
(how many spreads above that group's average): BFF's model, the experts' rank (negated), Sleeper and ESPN. The stacked strength
is the weighted average of the z-scores a player has (weights re-normalised when a source does not project him). The k-th
strongest player then gets the k-th highest of the players' average points across BFF, Sleeper and ESPN, so the scale is the
sources' shared scale. The weights were chosen on 2020-22 only; 2023-25 and 2026 are a clean test.

python research/bt_sites.py [--ceiling]   (--ceiling adds the hindsight-usage bound, which rebuilds features: ~5 minutes)"""
import os, sys, json, gzip, itertools, warnings, numpy as np, pandas as pd
from scipy.stats import spearmanr
warnings.filterwarnings('ignore')
BT = os.path.dirname(os.path.abspath(__file__)); RUN = os.path.dirname(BT); os.chdir(RUN); sys.path.insert(0, RUN)
H = pd.read_parquet(os.path.join(BT, 'h_weekly_v5.parquet'))
ids = pd.read_csv('db_playerids.csv', low_memory=False)
key = lambda v: str(int(v)) if isinstance(v, float) else str(v)
MAP = {'sleeper': {key(s): g for s, g in zip(ids.sleeper_id, ids.gsis_id) if s == s and isinstance(g, str)},
       'espn': {key(s): g for s, g in zip(ids.espn_id, ids.gsis_id) if s == s and isinstance(g, str)}}
rows = []
for src, col in (('sleeper', 'sl'), ('espn', 'es')):
    for S in range(2019, 2027):
        f = os.path.join(BT, 'hist', f'{src}_{S}.json.gz')
        if not os.path.exists(f): continue
        for w, d in json.load(gzip.open(f, 'rt')).items():
            for k, v in d.items():
                g = MAP[src].get(k)
                if g: rows.append((g, S, int(w), col, float(v)))
X = pd.DataFrame(rows, columns=['player_id', 'season', 'week', 'col', 'v']).drop_duplicates(['player_id', 'season', 'week', 'col'])
X = X.pivot_table(index=['player_id', 'season', 'week'], columns='col', values='v').reset_index()
H = H.merge(X, on=['player_id', 'season', 'week'], how='left')
H.loc[~(H.sl > 0), 'sl'] = np.nan; H.loc[~(H.es > 0), 'es'] = np.nan   # 0 or missing = that site does not project him
G = ['season', 'week', 'pos']; TOPK = {'QB': 24, 'RB': 40, 'WR': 50, 'TE': 20}
SRC = ['model', 'e', 'sl', 'es']; H['e'] = -H.ecr
W_LIVE = (.3, .1, .3, .3)   # model, experts, Sleeper, ESPN: the grid's choice on 2020-22 (below), used by ff_produce.py


def score(h, col, mae=True):
    """rank: mean weekly Spearman by position (groups of 9+); pairs: of two top-K players (by expert rank), how often the
    higher-projected one really scored more; mae: average miss in PPR points."""
    sp = []; ab = []; ok = n = 0
    for (s_, w_, p_), x in h.groupby(G):
        if len(x) > 8: sp.append(spearmanr(x[col], x.y).correlation); ab.append(float(np.mean(np.abs(x[col] - x.y))))
        z = x[x.ecr <= TOPK[p_]]; v = z[col].values; y = z.y.values
        for i, j in itertools.combinations(range(len(z)), 2):
            if y[i] == y[j] or v[i] == v[j]: continue
            n += 1; ok += (v[i] > v[j]) == (y[i] > y[j])
    out = {'rank': round(float(np.nanmean(sp)), 4), 'pairs': round(ok / max(n, 1), 4), 'n': int(len(h))}
    if mae: out['mae'] = round(float(np.mean(ab)), 3)
    return out


def fast_rank(h, col): return float(np.nanmean([x[col].corr(x.y, method='spearman') for _, x in h.groupby(G) if len(x) > 8]))


def zs(h):
    g = h.groupby(G)
    return pd.DataFrame({c: (h[c] - g[c].transform('mean')) / g[c].transform('std') for c in SRC}, index=h.index)


def stack(h, w=W_LIVE):
    """the production rule (see the top of this file)"""
    h = h.copy(); Z = zs(h); num = 0; den = 0
    for c, wi in zip(SRC, w):
        ok = Z[c].notna(); num = num + wi * Z[c].fillna(0); den = den + wi * ok
    h['zst'] = num / den; h['pavg'] = h[['model', 'sl', 'es']].mean(1)
    h['bff'] = np.nan
    for _, x in h.groupby(G):
        h.loc[x.zst.sort_values(ascending=False, kind='stable').index, 'bff'] = np.sort(x.pavg.values)[::-1]
    return h


def pct(a, b, lower_better=False): return round(100 * ((b - a) / b if lower_better else (a - b) / b), 1)


if __name__ == '__main__':
    R = {'note': 'common = player-games every source projected (the fair head-to-head); all = every player-game the experts ranked'}
    C = H[H.sl.notna() & H.es.notna()].copy()
    print('common player-games', len(C), {int(s): int((C.season == s).sum()) for s in sorted(C.season.unique())})
    # 1) the weights: every split of 100% in steps of 10%, chosen on 2020-22 by ranking accuracy
    grid = [(a, b, c, round(1 - a - b - c, 1)) for a, b, c in itertools.product(np.round(np.arange(0, 1.01, .1), 1), repeat=3) if a + b + c <= 1.0001]
    tr = C[C.season.between(2020, 2022)]; Ztr = zs(tr).fillna(0); tr = tr.assign(**{'z_' + c: Ztr[c] for c in SRC})
    def zmix(h, w): return h.assign(s=sum(wi * h['z_' + c] for c, wi in zip(SRC, w)))
    fit = sorted(((fast_rank(zmix(tr, w), 's'), w) for w in grid), reverse=True)
    R['weights'] = {'chosen_on': '2020-22', 'best': [[round(a, 4), list(w)] for a, w in fit[:5]], 'used': list(W_LIVE)}
    print('weights chosen on 2020-22:', fit[:3])
    te = C[C.season.between(2023, 2025)]; Zte = zs(te).fillna(0); te = te.assign(**{'z_' + c: Zte[c] for c in SRC})
    orc = sorted(((fast_rank(zmix(te, w), 's'), w) for w in grid), reverse=True)[0]
    R['oracle_weights_2023_25'] = {'rank': round(orc[0], 4), 'w': list(orc[1]), 'note': 'weights picked on the test seasons themselves: the most any re-weighting of these sources could have reached'}
    # 2) head-to-head on common player-games
    R['common'] = {}
    for nm, (a, b) in {'2020-22': (2020, 2022), '2023-25': (2023, 2025), '2026': (2026, 2026)}.items():
        h = stack(C[C.season.between(a, b)]); R['common'][nm] = {}
        for k, c in (('experts', 'experts'), ('experts_pts', 'experts_pts'), ('espn', 'es'), ('sleeper', 'sl'), ('bff_model', 'model'), ('bff_old_mix', 'mix40'), ('bff', 'bff')):
            R['common'][nm][k] = score(h, c, mae=k != 'experts'); print(nm, k.ljust(12), R['common'][nm][k])
        o = R['common'][nm]   # best other site per measure (points: ESPN and Sleeper; the experts publish ranks only)
        best = {'rank': max(o[k]['rank'] for k in ('experts', 'espn', 'sleeper')), 'pairs': max(o[k]['pairs'] for k in ('experts', 'espn', 'sleeper')),
                'mae': min(o[k]['mae'] for k in ('espn', 'sleeper'))}
        o['bff_vs_best_other_pct'] = {m: pct(o['bff'][m], best[m], m == 'mae') for m in best}; print(nm, 'BFF vs best other site (%):', o['bff_vs_best_other_pct'])
    # 3) every player-game the experts ranked (some lack ESPN or Sleeper), by season: the Learn page table
    R['all'] = {}
    for nm, (a, b) in {'2023-25': (2023, 2025), '2026': (2026, 2026), **{str(s): (s, s) for s in range(2021, 2027)}}.items():
        h = stack(H[H.season.between(a, b)])
        h['avg'] = np.where(h.g > 0, (h.m_fp.fillna(0) * h.g + h.p_fp.fillna(h.m_fp.fillna(8)) * 3) / (h.g + 3), h.p_fp.fillna(8))   # season average shrunk toward last season
        R['all'][nm] = {k: score(h, c, mae=k != 'experts') for k, c in (('season_avg', 'avg'), ('experts', 'experts'), ('experts_pts', 'experts_pts'), ('bff_model', 'model'), ('bff_old_mix', 'mix40'), ('bff', 'bff'))}
        if nm == '2023-25':   # must-start calls: each week's top 10 at each position; a hit finishes as a starter (top 12 QB, 24 RB, 30 WR, 12 TE)
            TH = {'QB': 12, 'RB': 24, 'WR': 30, 'TE': 12}; R['must_start_2023_25'] = {}
            for k, c in (('bff', 'bff'), ('bff_old_mix', 'mix40'), ('experts', 'experts'), ('bff_model', 'model'), ('season_avg', 'avg')):
                hit = n = 0
                for (s_, w_, p_), x in h.groupby(G):
                    fin = x.y.rank(ascending=False, method='min') <= TH[p_]; top = x.sort_values(c, ascending=False).head(10); hit += int(fin[top.index].sum()); n += len(top)
                R['must_start_2023_25'][k] = round(100 * hit / n, 1)
            print('must starts 2023-25', R['must_start_2023_25'])
        if nm in ('2023-25', '2026'):   # ranking accuracy by position
            R['all'][nm]['by_pos'] = {q: {k: round(fast_rank(h[h.pos == q], c), 4) for k, c in (('experts', 'experts'), ('bff_model', 'model'), ('bff_old_mix', 'mix40'), ('bff', 'bff'))} for q in TOPK}
            hc = stack(C[C.season.between(a, b)])
            R['common'][nm]['by_pos'] = {q: {k: round(fast_rank(hc[hc.pos == q], c), 4) for k, c in (('experts', 'experts'), ('espn', 'es'), ('sleeper', 'sl'), ('bff', 'bff'))} for q in TOPK}
        print('all', nm, {k: v['rank'] for k, v in R['all'][nm].items() if k != 'by_pos'})
    # 4) how much room is left: hindsight bounds on 2023-25 common player-games
    h = C[C.season.between(2023, 2025)].copy(); s = h.groupby(['player_id', 'season']).y
    h['loo'] = (s.transform('sum') - h.y) / (s.transform('count') - 1); h = h[np.isfinite(h.loo)]
    R['hindsight'] = {'season_avg_other_games': score(h, 'loo'), 'espn_same_games': score(h, 'es'),
                      'note': "loo = the player's actual average in all his OTHER games that season, past and future (hindsight no site has)"}
    pairs = [('es', 'sl'), ('model', 'es'), ('model', 'sl'), ('e', 'es'), ('e', 'model')]
    R['agreement'] = {f'{a}~{b}': round(float(np.nanmean([spearmanr(x[a], x[b]).correlation for _, x in h.groupby(G) if len(x) > 8])), 3) for a, b in pairs}
    if '--ceiling' in sys.argv:
        import ff_feat as FX
        Cx = FX.Ctx([2023, 2024, 2025], [2012, 2013], rates=json.load(open('.cache/f5_2026_xfp.json')))
        st = Cx.st[['player_id', 'season', 'week', 'xfp']].drop_duplicates(['player_id', 'season', 'week'])
        u = C[C.season.between(2023, 2025)].merge(st, on=['player_id', 'season', 'week'], how='inner')
        R['hindsight']['same_game_usage_xfp'] = score(u, 'xfp'); R['hindsight']['espn_on_usage_rows'] = score(u, 'es')
        R['hindsight']['note_xfp'] = "xfp = expected points from the player's actual targets, carries and where they came, in that very game (perfect knowledge of usage)"
    for k, v in R['hindsight'].items(): print('hindsight', k, v)
    print('agreement', R['agreement'])
    json.dump(R, open(os.path.join(BT, 'results_sites.json'), 'w'), indent=1)
