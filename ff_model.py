"""BFF's projection model (version 5). Used by ff_produce.py; the backtests in research/ test exactly this recipe.

Training data: every player-game of the 13 completed seasons before this one (features from ff_feat.py, all known before
kickoff). For each position:
  - a total-points model: gradient-boosted trees (3 seeds averaged) on all features,
  - a stat-by-stat model: the same trees for each scoring stat (passing yards and touchdowns, interceptions, rushing yards
    and touchdowns, catches, receiving yards and touchdowns), added up with the scoring rules,
  - next-game projection = the average of the two,
  - (optional, research) a rest-of-season model on the average of his next six games; the site instead averages his
    remaining next-game projections, which tested better for trade values.
Out of sample 2021-2026 (each season predicted by models trained only on earlier seasons) the next-game model alone
ranked players 0.622 (2023-25; the FantasyPros experts 0.631) and 0.633 in 2026 (experts 0.633); see research/README.md.
"""
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor as HGBR

POS = ['QB', 'RB', 'WR', 'TE']
ES = dict(max_iter=1500, learning_rate=.03, max_leaf_nodes=15, min_samples_leaf=150, early_stopping=True, validation_fraction=.15, n_iter_no_change=40)
W = {'passing_yards': .04, 'passing_tds': 4, 'passing_interceptions': -2, 'rushing_yards': .1, 'rushing_tds': 6, 'receptions': 1, 'receiving_yards': .1, 'receiving_tds': 6}
COMP = {'QB': ['passing_yards', 'passing_tds', 'passing_interceptions', 'rushing_yards', 'rushing_tds'], 'RB': ['rushing_yards', 'rushing_tds', 'receptions', 'receiving_yards', 'receiving_tds'],
        'WR': ['receptions', 'receiving_yards', 'receiving_tds', 'rushing_yards'], 'TE': ['receptions', 'receiving_yards', 'receiving_tds']}
POISS = {'passing_tds', 'rushing_tds', 'receiving_tds', 'passing_interceptions', 'receptions'}
GAMEF = {'home', 'it', 'spread', 'total', 'dome', 'rest', 'div', 'dvp', 'q', 'prac', 'qp', 'gap', 'be_it', 'bxe_it', 'xs_it', 'xsm_it', 'x_tgt', 'x_car', 'x_att', 'bump', 'qbm', 'vac_all'}
DROP = {'player_id', 'season', 'week', 'pos', 'team', 'opp', 'y'} | set(COMP['QB'] + COMP['RB'] + COMP['WR'])
DER = ['b', 'bx', 'be', 'bxe', 'dsn', 'dts', 'dcs', 'pv', 'qp', 'be_it', 'bxe_it', 'xs_it', 'xsm_it', 'x_tgt', 'x_car', 'x_att', 'jump_snap', 'jump_xs']


def bk(x, y):
    """draft bucket for players without a full previous season"""
    if y == y and y >= 2: return None
    return 'u' if x != x else ('1' if x <= 32 else '2' if x <= 64 else '3' if x <= 100 else '4')


class Priors:
    """what a player with no history this season starts from: last season's points a game (3+ games), else what players
    from his draft range scored, else the position average (all learned from the training seasons)"""
    def __init__(self, tr):
        self.pavg = tr.groupby('pos').y.mean().to_dict()
        t_ = tr[tr.p_fp.isna() | (tr.p_g < 3)].copy(); t_['bk'] = [bk(x, y) for x, y in zip(t_.dpick, t_.yrs)]
        self.dpri = t_.dropna(subset=['bk']).groupby(['pos', 'bk']).y.mean().to_dict()


def prep(d, pr, K=3):
    """season-to-date and recent-form averages shrunk toward the prior (worth 3 games), and interactions"""
    d = d.copy()
    pv = d.p_fp.where(d.p_g >= 3)
    pv = pv.fillna(pd.Series([pr.dpri.get((p_, bk(x, y)), np.nan) for p_, x, y in zip(d.pos, d.dpick, d.yrs)], index=d.index)).fillna(d.pos.map(pr.pavg))
    d['pv'] = pv; g = d.g.values
    d['b'] = np.where(g > 0, (d.m_fp.fillna(0) * g + pv * K) / (g + K), pv); d['bx'] = np.where(g > 0, (d.m_xfp.fillna(0) * g + pv * K) / (g + K), pv)
    w = d.ew.fillna(0); d['be'] = (d.e_fp.fillna(0) * w + pv * K) / (w + K); d['bxe'] = (d.e_xfp.fillna(0) * w + pv * K) / (w + K)
    d['dsn'] = (d.e_snap - d.m_snap); d['dts'] = (d.e_ts - d.m_ts); d['dcs'] = (d.e_cs - d.m_cs)
    d['qp'] = d.q * (2 - d.prac.fillna(2))
    pace = ((d.plays_t + d.o_plays_t) / 2) / d.plays_t; itr = d.it / d.pts_t
    d['be_it'] = d.be * itr; d['bxe_it'] = d.bxe * itr; d['xs_it'] = d.e_xs * d.it; d['xsm_it'] = d.m_xs * d.it
    d['x_tgt'] = d.e_tgt * pace; d['x_car'] = d.e_car * pace; d['x_att'] = d.e_att * pace
    d['jump_snap'] = d.l1_snap - d.e_snap; d['jump_xs'] = d.l1_xs - d.e_xs
    return d


def feats(pos, cols):
    f = [c for c in cols if c not in DROP and not c.startswith('_')] + DER
    if pos != 'QB': f = [c for c in f if not any(c.endswith(s) for s in ('_att', '_pass', '_ptd', '_int', '_pepa', '_cpoe', '_sk'))]
    else: f = [c for c in f if not any(c.endswith(s) for s in ('_ays', '_rec', '_recy', '_rectd', '_repa', '_yac', '_aird', '_ts', 'p_ts', 'p_ays', '_tgt', 'x_tgt'))]
    if pos == 'QB': f = [c for c in f if c not in ('bump', 'vac_all')]
    return list(dict.fromkeys(f))


def ros_target(d):
    """the average of this game and his next five, weighted by how many games it covers"""
    d = d.sort_values(['player_id', 'season', 'week']).copy(); yr = []; nr = []
    for _, g_ in d.groupby(['player_id', 'season'], sort=False):
        y_ = g_.y.values; n_ = len(y_); yr += [float(np.mean(y_[k:k + 6])) for k in range(n_)]; nr += [min(6, n_ - k) for k in range(n_)]
    d['yr'] = yr; d['nr'] = nr; return d[d.nr >= 3]


class Model:
    def __init__(self, tr, cols, seeds=3, ros=True):
        """tr: training rows (features, y and the scoring stats); cols: the feature table's columns"""
        self.pr = Priors(tr); self.M = {}
        trr = ros_target(tr) if ros else None
        for pos in POS:
            a = prep(tr[tr.pos == pos], self.pr); FF = feats(pos, cols)
            tot = [HGBR(random_state=k, **ES).fit(a[FF], a.y) for k in range(seeds)]
            comp = {}
            for c in COMP[pos]:
                kw = dict(ES)
                if c in POISS: kw['loss'] = 'poisson'
                comp[c] = [HGBR(random_state=k, **kw).fit(a[FF], np.maximum(0, a[c]) if c in POISS else a[c]) for k in range(seeds)]
            res = float((a.y - sum(a[c] * W[c] for c in COMP[pos])).mean())
            RF = [f for f in FF if f not in GAMEF and not f.startswith('o_')]; rm = None
            if ros:
                b = prep(trr[trr.pos == pos], self.pr); rm = [HGBR(random_state=k, **ES).fit(b[RF], b.yr, sample_weight=b.nr) for k in range(seeds)]
            self.M[pos] = (FF, tot, comp, res, RF, rm)

    def next(self, pos, d):
        """next-game PPR points (average of the total and stat-by-stat models)"""
        FF, tot, comp, res, RF, rm = self.M[pos]; q = prep(d, self.pr)
        p1 = np.mean([m.predict(q[FF]) for m in tot], axis=0)
        p2 = res + sum(W[c] * np.maximum(0, np.mean([m.predict(q[FF]) for m in comp[c]], axis=0)) for c in comp)
        return np.maximum(0, (p1 + p2) / 2)

    def parts(self, pos, d):
        """the expected stat line behind the projection (passing yards, catches, touchdowns...)"""
        FF, tot, comp, res, RF, rm = self.M[pos]; q = prep(d, self.pr)
        return {c: np.maximum(0, np.mean([m.predict(q[FF]) for m in comp[c]], axis=0)) for c in comp}

    def ros(self, pos, d):
        """rest-of-season points per game (no game-specific features)"""
        FF, tot, comp, res, RF, rm = self.M[pos]; q = prep(d, self.pr)
        return np.maximum(0, np.mean([m.predict(q[RF]) for m in rm], axis=0))
