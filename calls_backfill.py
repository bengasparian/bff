#!/usr/bin/env python3
"""Rebuild the weekly calls for past weeks of this season that were played before live tracking began.

Each past week is rebuilt the way it would have looked before its games: projections come from the same tested model,
fed only with games played before that week, that week's official injury report and roster status, and the Vegas
lines for that week. Rebuilt weeks are marked 'rebuilt' so the page keeps them apart from calls saved live.
Differences from live calls: no teammate-injury adjustment, and 'usual' scoring is the model's neutral projection
(no matchup or Vegas adjustment) instead of the rest-of-season average.

Run once (needs the same data files as ff_produce.py); weeks already tracked live are never touched.
  python calls_backfill.py
"""
import json, math
src = open('ff_produce.py').read().split('# ---- teammates expected to miss games')[0]   # note: the model reads globals L, F, FT; do not reuse those names below
exec(src)                                                     # model, features, data, pool (same as the data job)
import calls_update as CU

D = json.load(open('ff_data.json'))
try: H = json.load(open(CU.HIST))
except Exception: H = {}
if H.get('season') != SEASON: H = {'season': SEASON, 'weeks': {}}
H.update(fmt='PPR', cut=CU.CUT)
cw, nw = CU.call_week(D)
INJ = get(f'injuries/injuries_{SEASON}.parquet')
WROS = wr.set_index(['gsis_id', 'week'])
PL = {p['id']: p for p in D['players']}
LASTP = int(S26.week.max())

def team_week(pid, w, cur_team):
    try: return WROS.loc[(pid, w)].team if not isinstance(WROS.loc[(pid, w)], pd.DataFrame) else WROS.loc[(pid, w)].iloc[-1].team
    except KeyError: return cur_team
def status_week(pid, w):
    try:
        x = WROS.loc[(pid, w)]; return (x.iloc[-1] if isinstance(x, pd.DataFrame) else x).status
    except KeyError: return None

for w in range(2, min(LASTP, cw - 1) + 1):
    if H['weeks'].get(str(w), {}).get('src') == 'live': continue
    rep = INJ[INJ.week == w].drop_duplicates('gsis_id', keep='last').set_index('gsis_id').report_status.to_dict()
    G = SC26[SC26.week == w].set_index('team')
    rows_by_pos = {q: [] for q in POS}
    for pid, p in PL.items():
        tm = team_week(pid, w, p['t'])
        if tm not in G.index: continue                        # bye week or no game
        g = G.loc[tm]; rows = S26[(S26.player_id == pid) & (S26.week < w)].sort_values('week')
        base = feats(SEASON, 99, rows, None); pv = prev_pg.get((pid, SEASON), np.nan)
        if (pv is None or pv != pv) and pid in _pp2.index and _pp2.loc[pid, 'size'] >= 6: pv = 0.9 * float(_pp2.loc[pid, 'mean'])
        f = dict(base); f.update(pos=p['p'], prev=pv, dvp=dvp_factor(SEASON, w, g.opp, p['p']) if w > 2 else np.nan, it=g.it, home=g.home, bump=0.0, qbm=0, vac_all=0.0)
        rs = rep.get(pid); res_ = status_week(pid, w) == 'RES'
        rows_by_pos[p['p']].append(dict(pid=pid, tm=tm, opp=g.opp, home=int(g.home), f=f, out=(rs == 'Out' or res_), ir=res_, q=rs if rs in ('Questionable', 'Doubtful') else None,
                                        cs=float(rows.car_share.mean()) if len(rows) else 0.0, tpg=float(rows.targets.mean()) if len(rows) else 0.0))
    wk = {'src': 'rebuilt', 'start': [], 'sit': [], 'buy': [], 'sell': [], 'base': [], 'pool': []}
    for pos in POS:
        R = rows_by_pos[pos]
        if not R: continue
        FR = pd.DataFrame([x['f'] for x in R]); v = predict(pos, FR); u = predict(pos, FR.assign(dvp=np.nan, it=np.nan))
        for x, a, b_ in zip(R, v, u):
            x['v'] = 0.0 if x['out'] else float(a); x['u'] = float(b_)
            g_ = x['f']['g'] or 0; pv_ = x['f']['prev'] if x['f']['prev'] == x['f']['prev'] else 0.0
            x['b'] = ((x['f']['ppg'] if g_ else 0.0) * g_ + (pv_ or 0.0) * 3) / (g_ + 3)    # season average blended with last season
        cut = CU.CUT[pos]
        ranked = sorted([x for x in R if not x['out']], key=lambda x: -x['v']); wr_ = {x['pid']: i + 1 for i, x in enumerate(ranked)}
        rr = {x['pid']: i + 1 for i, x in enumerate(sorted([x for x in R if not x['ir']], key=lambda x: -x['u']))}
        must = [x for x in ranked if x['q'] != 'Doubtful'][:10]; ms = {x['pid'] for x in must}
        role = lambda x: pos != 'RB' or x['cs'] >= .15 or x['tpg'] >= 3
        regs = [x for x in ranked if x['u'] >= CU.MINU[pos] and role(x) and rr[x['pid']] <= round(cut * 1.5) + 6]   # usual starters
        cand = [x for x in regs if x['pid'] not in ms and (wr_[x['pid']] > cut or (x['q'] and wr_[x['pid']] > round(cut * .8)))]
        prio = lambda x: 2 if rr[x['pid']] <= cut and wr_[x['pid']] > cut else 1 if x['q'] else 0
        dont = sorted(cand, key=lambda x: (-prio(x), x['v'] - x['u']))[:10]
        ent = lambda x: {'id': x['pid'], 'n': PL[x['pid']]['n'], 'p': pos, 't': x['tm'], 'o': x['opp'], 'h': x['home'], 'k': CU.kickoff(D, x['tm'], w),
                         'v': CU.r1(x['v']), 'wr': wr_[x['pid']], 'u': CU.r1(x['u']), 'q': x['q']}
        wk['start'] += [ent(x) for x in must]; wk['sit'] += [ent(x) for x in dont]
        wk['pool'] += [{'id': x['pid'], 'p': pos, 't': x['tm'], 'k': CU.kickoff(D, x['tm'], w)} for x in regs]
        wk['base'] += [{'id': x['pid'], 'p': pos, 't': x['tm'], 'k': CU.kickoff(D, x['tm'], w)} for x in sorted([x for x in ranked if x['q'] != 'Doubtful'], key=lambda x: -x['b'])[:10]]
    if w >= 3:                                                # buy low / sell high need two games played
        sk = []
        for pid, p in PL.items():
            if p['p'] == 'QB': continue
            gl = [x for x in p.get('wk') or [] if x[0] < w]
            if len(gl) < 2 or rep.get(pid) == 'Out' or status_week(pid, w) == 'RES': continue
            fpg = sum(x[1] or 0 for x in gl) / len(gl); xfpg = sum(x[2] or 0 for x in gl) / len(gl)
            sk.append({'id': pid, 'n': p['n'], 'p': p['p'], 't': team_week(pid, w, p['t']), 'fpg': round(fpg, 1), 'xfpg': round(xfpg, 1), 'g': len(gl)})
        wk['buy'] = sorted([x for x in sk if x['xfpg'] >= 8 and x['xfpg'] - x['fpg'] >= 2.5], key=lambda x: -(x['xfpg'] - x['fpg']) * math.sqrt(x['xfpg']))[:10]
        wk['sell'] = sorted([x for x in sk if x['fpg'] >= 10 and x['fpg'] - x['xfpg'] >= 3], key=lambda x: -(x['fpg'] - x['xfpg']))[:10]
    kicks = [k for t in D['sched'] for k in [CU.kickoff(D, t, w)] if k]
    wk['lock'] = min(kicks) if kicks else None; wk['made'] = None; wk['upd'] = CU.STAMP
    H['weeks'][str(w)] = wk
    print(f'week {w}: rebuilt {len(wk["start"])} starts, {len(wk["sit"])} sits, {len(wk["buy"])} buys, {len(wk["sell"])} sells')
H['weeks'] = dict(sorted(H['weeks'].items(), key=lambda kv: int(kv[0])))
json.dump(H, open(CU.HIST, 'w'), separators=(',', ':'))
print('saved; now run calls_update.py to grade and add this week')
