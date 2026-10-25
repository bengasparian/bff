"""BFF research: kicker and team-defense (D/ST) projections.

Points come from ff_kdst.py's scoring (Yahoo's default settings) applied to nflverse's play-by-play and kicker stats.
Checks:
  1. the D/ST counts against nflverse's own team stats (2023-2025): sacks, interceptions, fumble recoveries, return
     touchdowns, safeties, blocked kicks;
  2. the projection models, fit on 2015-2022 regular seasons and scored on 2023-2025 (never seen): average miss (points),
     correlation with what happened, and how well each week's ranking matched (Spearman), against simpler rules (the
     league average, the season so far, Vegas alone);
  3. how much of a D/ST or kicker's week is predictable at all (the best any rule did), so the page can say so.
python research/bt_kdst.py   (writes research/results_kdst.json; about a minute)"""
import os, sys, json, numpy as np, pandas as pd
BT = os.path.dirname(os.path.abspath(__file__)); RUN = os.path.dirname(BT); os.chdir(RUN); sys.path.insert(0, RUN)
import ff_kdst as K
from scipy.stats import spearmanr

FIT = range(2015, 2023); TEST = range(2023, 2026)


def score(df, pred, y='pts'):
    e = df[pred] - df[y]
    sp = [spearmanr(x[pred], x[y]).correlation for _, x in df.groupby(['season', 'week']) if len(x) >= 8]
    return {'n': int(len(df)), 'mae': round(float(e.abs().mean()), 3), 'corr': round(float(np.corrcoef(df[pred], df[y])[0, 1]), 3), 'week_rank_corr': round(float(np.nanmean(sp)), 3)}


if __name__ == '__main__':
    R = {'scoring': 'Yahoo default (help.yahoo.com/kb/SLN6489 and SLN6442)'}
    G = K.games_table()
    DST = pd.concat([K.dst_games(y, G) for y in range(2015, 2026)], ignore_index=True)
    KG = pd.concat([K.k_games(y) for y in range(2015, 2026)], ignore_index=True)
    print('D/ST games', len(DST), 'kicker games', len(KG))
    # ---- 1. counts against nflverse team stats
    chk = {}
    for y in (2023, 2024, 2025):
        f = os.path.join(BT, 'hist', f'stats_team_week_{y}.parquet')
        if not os.path.exists(f): continue
        T = pd.read_parquet(f); T = T[T.season_type == 'REG'].copy(); T['team'] = T.team.map(K.fix)
        m = DST[DST.season == y].merge(T, on=['week', 'team'], how='inner', suffixes=('', '_t'))
        nv = {'sack': m.def_sacks, 'int': m.def_interceptions, 'fr': m.fumble_recovery_opp, 'sfty': m.def_safeties,
              'td': m.def_tds.fillna(0) + m.special_teams_tds.fillna(0) + m.fumble_recovery_tds.fillna(0),
              'blk': m.def_fg_blocks.fillna(0) + m.def_punt_blocks.fillna(0) + m.def_pat_blocks.fillna(0)}
        chk[str(y)] = {k: {'ours': int(m[k].sum()), 'nflverse': round(float(v.sum()), 1), 'games_differ': int((abs(m[k] - v) >= 1).sum()), 'games': int(len(m))} for k, v in nv.items()}
    R['counts_vs_nflverse'] = chk
    R['note_counts'] = ('sacks: play-by-play counts every sack, including team sacks no player is credited with, so it runs a '
                        'little above the player totals; touchdowns: nflverse also credits an offense that recovers its own fumble in the end zone')
    print(json.dumps(chk)[:600])
    # ---- 2. projections
    D, KK = K.features(DST, KG, G)
    D = D.dropna(subset=['oit', 'rate', 'give']); KK = KK.dropna(subset=['it', 'kavg'])
    fd, td = D[D.season.isin(FIT)], D[D.season.isin(TEST)]
    Xd = lambda z: np.c_[np.ones(len(z)), z.oit, z.rate, z.give, z.home]
    bd = np.linalg.lstsq(Xd(fd), fd.pts.values, rcond=None)[0]
    D['proj'] = Xd(D) @ bd
    D['avg'] = D.pts.groupby(D.season).transform('mean')   # league average (that season; a generous baseline)
    D['sofar'] = (D.pts_sum + 4 * D.season.map(D.groupby('season').pts.mean())) / (D.n_prev + 4)
    bv = np.polyfit(fd.oit, fd.pts, 1); D['vegas'] = np.polyval(bv, D.oit)
    td = D[D.season.isin(TEST)]
    R['dst'] = {'model': dict(zip(['a', 'opp_it', 'rate', 'give', 'home'], [round(float(x), 4) for x in bd])),
                'test_2023_25': {nm: score(td, nm) for nm in ('proj', 'vegas', 'sofar', 'avg')},
                'fit_2015_22': score(D[D.season.isin(FIT)], 'proj'), 'avg_pts': round(float(td.pts.mean()), 2), 'sd_pts': round(float(td.pts.std()), 2)}
    print('D/ST', json.dumps(R['dst']))
    fk = KK[KK.season.isin(FIT)]
    Xk = lambda z: np.c_[np.ones(len(z)), z.it, z.kavg, z.dome]
    bk = np.linalg.lstsq(Xk(fk), fk.pts.values, rcond=None)[0]
    KK['proj'] = Xk(KK) @ bk
    KK['avg'] = KK.pts.groupby(KK.season).transform('mean')
    KK['sofar'] = KK.kavg
    bv = np.polyfit(fk.it, fk.pts, 1); KK['vegas'] = np.polyval(bv, KK.it)
    tk = KK[KK.season.isin(TEST)]
    R['k'] = {'model': dict(zip(['a', 'it', 'kavg', 'dome'], [round(float(x), 4) for x in bk])),
              'test_2023_25': {nm: score(tk, nm) for nm in ('proj', 'vegas', 'sofar', 'avg')},
              'fit_2015_22': score(KK[KK.season.isin(FIT)], 'proj'), 'avg_pts': round(float(tk.pts.mean()), 2), 'sd_pts': round(float(tk.pts.std()), 2)}
    print('K', json.dumps(R['k']))
    R['shrink'] = K.SHRINK
    json.dump(R, open(os.path.join(BT, 'results_kdst.json'), 'w'), indent=1)
