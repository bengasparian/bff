#!/usr/bin/env python3
"""Predicted prop lines for BFF: what PrizePicks, Underdog and sportsbooks are expected to post this week.

Lines are built the way books build them, from OPPORTUNITY:
  expected volume (targets, carries or pass attempts; recent games count more, last season counts like 1-3 games,
  injury-shortened games are left out) x the player's efficiency (catch rate, yards per target / carry / attempt,
  touchdowns per attempt; shrunk toward the position average) x this game (Vegas implied team total, the defense).
Volume freed up by injured teammates is added for receiving yards. A player coming off an injury-shortened game is
marked down (in testing those players hit their overs only 25-33% of the time). Lines end in .5.

Settings were tuned on 2024 and tested on every 2025 game they had never seen: overs hit 44-50% for every stat, and
they stay balanced for players whose role rose or fell, rookies, players returning from partial games, and at every line
height (very high or low projections are pulled back toward typical, as books do).

Picks: our projection model against each line. In the 2025 test, picks shown at 55%+ won 59.6% (1,080 picks).
Receiving-yard picks did not beat their lines, so receiving yards get lines but never picks; quarterback rushing
lines were not part of the pick test, so they get no picks either.

Two ways to run:
  python ff_lines.py            data job: reads ff_data.json + last season's stats, writes bet_inputs.json, lines.json
                                and the lines into ff_data.json
  python ff_lines.py --refresh  score job (every 10 minutes): reads bet_inputs.json + live.json (current ESPN odds)
                                and rewrites lines.json only when a line or pick actually changed
Every line keeps its opening value and each move with its reason (Vegas total, teammate news, injury status).
"""
import json, math, os, re, sys, datetime

REFRESH = '--refresh' in sys.argv
PULLED = {}
NOW = datetime.datetime.fromisoformat(os.environ['BFF_NOW']) if os.environ.get('BFF_NOW') else datetime.datetime.now(datetime.timezone.utc)
STAMP = NOW.isoformat(timespec='minutes')

# ---- settings tuned on 2024, tested on 2025 (see the docstring)
# d: recency decay per game, Wv: last season's weight in games, pw: last season's weight in efficiency, k: shrinkage toward the
# position average, a: Vegas exponent, b: defense exponent, kb: injured-teammate volume, pp: after a partial game, nf: no last season,
# c: sets the line at the typical game (books' lines sit below the average for skewed stats), sh: pulls unusual projections back toward the
# typical player at the position (passing yards: the highest and lowest lines were too extreme without it)
PAR = {'rec': dict(d=.75, Wv=2, pw=.5, k=30, a=0, b=.25, kb=0, pp=.7, nf=1, c=.8989),
       'ty': dict(d=.9, Wv=2, pw=.5, k=10, a=.25, b=0, kb=.5, pp=.7, nf=1, c=0.8410, sh=.9),
       'ry': dict(d=.9, Wv=1, pw=.5, k=80, a=.5, b=.25, kb=0, pp=.7, nf=.9, c=.9178),
       'ryq': dict(d=.9, Wv=2, pw=.5, k=80, a=.5, b=.25, kb=0, pp=1, nf=1, c=.813),
       'py': dict(d=.6, Wv=3, pw=.5, k=30, a=.25, b=0, kb=0, pp=1, nf=1, c=0.9565, sh=.7),
       'ptd': dict(d=.5, Wv=2, pw=.5, k=30, a=.25, b=0, kb=0, pp=1, nf=1, c=1.0345)}
VOL = {'rec': 'tg', 'ty': 'tg', 'ry': 'car', 'ryq': 'car', 'py': 'att', 'ptd': 'att'}
EFF = {'rec': ('rec', 'tg'), 'ty': ('ty', 'tg'), 'ry': ('ry', 'car'), 'ryq': ('ry', 'car'), 'py': ('py', 'att'), 'ptd': ('ptd', 'att')}
GLI = {'att': 2, 'py': 3, 'ptd': 4, 'car': 6, 'ry': 7, 'rec': 9, 'tg': 10, 'ty': 11}       # columns of a game-log row
PICKS = {'rec', 'ry', 'py', 'ptd'}; PICK_MIN = .55
BT = {'season': 2025, 'tuned_on': 2024,
      'lines': {'rec': {'n': 2159, 'mae': 1.67, 'over': 46.8}, 'ty': {'n': 2159, 'mae': 21.9, 'over': 44.4}, 'ry': {'n': 658, 'mae': 26.4, 'over': 49.1},
                'ryq': {'n': 293, 'mae': 13.7, 'over': 50.2}, 'py': {'n': 487, 'mae': 64.5, 'over': 50.0}, 'ptd': {'n': 502, 'mae': 1.00, 'over': 47.2}},
      'picks': {'thr': .55, 'n': 1080, 'won': .596, 'by': {'ptd': .582, 'py': .597, 'rec': .603, 'ry': .538}, 'ty': .46}}
TEAMFIX = {'WSH': 'WAS', 'LAR': 'LA', 'JAC': 'JAX'}

def cdf(q, x):
    if x < q[0]: return max(0, .05 * (1 - (q[0] - x) / (max(q[1] - q[0], .05) * 3)))
    if x >= q[18]: return min(1, .95 + .05 * (x - q[18]) / (max(q[18] - q[17], .05) * 3))
    for i in range(18):
        if x < q[i + 1]: d = q[i + 1] - q[i]; return (i + 1 + ((x - q[i]) / d if d > 0 else 0)) / 20
    return .95
QK = lambda pos, k: {'py': 'pass_yds', 'ptd': 'pass_td', 'ry': 'rush_yds_qb' if pos == 'QB' else 'rush_yds', 'ryq': 'rush_yds_qb',
                     'ty': 'rec_yds_rb' if pos == 'RB' else 'rec_yds', 'rec': 'rec_rb' if pos == 'RB' else 'rec'}[k]

# ------------------------------------------------------------------ inputs
def build_inputs():
    """Data job: everything the lines need, in one compact file the 10-minute job can reuse."""
    import pandas as pd
    D = json.load(open('ff_data.json')); P = D['players']; NW = D['asof']['next_week']; SEASON = D['asof'].get('season') or NOW.year
    SCHED = D.get('sched', {})
    left = {tm for tm, L in SCHED.items() for x in L if x[0] == NW and x[4] is None}
    FW = NW + 1 if len(left) / 2 <= 2 and NW < 18 else NW
    pri, mu = {}, {}
    f = f'stats_player_week_{SEASON - 1}.parquet'
    if os.path.exists(f):
        s = pd.read_parquet(f); s = s[(s.season_type == 'REG') & s.position.isin(['QB', 'RB', 'WR', 'TE'])].copy()
        for c in ['attempts', 'passing_yards', 'passing_tds', 'carries', 'rushing_yards', 'receptions', 'targets', 'receiving_yards']: s[c] = s[c].fillna(0)
        s = s[(s.position != 'QB') | (s.attempts >= 15)]                                  # partial quarterback games left out
        g = s.groupby('player_id').agg(n=('week', 'size'), fp=('fantasy_points_ppr', 'mean'), tg=('targets', 'sum'), rec=('receptions', 'sum'), ty=('receiving_yards', 'sum'),
                                       car=('carries', 'sum'), ry=('rushing_yards', 'sum'), att=('attempts', 'sum'), py=('passing_yards', 'sum'), ptd=('passing_tds', 'sum'))
        g = g[g.n >= 3]
        pri = {pid: {k: round(float(v), 2) for k, v in r.items()} for pid, r in g.iterrows()}
        pos_of = s.drop_duplicates('player_id').set_index('player_id').position
        for q in ['QB', 'RB', 'WR', 'TE']:
            X = g[g.index.isin(pos_of[pos_of == q].index)]
            mu[q] = {k: round(float(v), 4) for k, v in {'rec': X.rec.sum() / max(1, X.tg.sum()), 'ty': X.ty.sum() / max(1, X.tg.sum()), 'ry': X.ry.sum() / max(1, X.car.sum()),
                     'py': X.py.sum() / max(1, X.att.sum()), 'ptd': X.ptd.sum() / max(1, X.att.sum())}.items()}
    else:
        print(f'{f} not found: lines use this season only')
    if not mu:   # league-typical efficiency if last season's file is missing
        mu = {'QB': {'rec': 1, 'ty': 1.6, 'ry': 4.6, 'py': 6.9, 'ptd': .045}, 'RB': {'rec': .78, 'ty': 5.6, 'ry': 4.3, 'py': 7, 'ptd': .04},
              'WR': {'rec': .64, 'ty': 8.1, 'ry': 6, 'py': 7, 'ptd': .04}, 'TE': {'rec': .72, 'ty': 7.4, 'ry': 4, 'py': 7, 'ptd': .04}}
    keep = ('id', 'n', 'p', 't', 'opp', 'nw', 'proj', 'inj', 'prac', 'fpg', 'g', 'gl', 'wk', 'role', 'bmp', 'home', 'sid')
    players = []
    for p in P:
        if p['p'] not in ('QB', 'RB', 'WR', 'TE'): continue
        q = {k: p.get(k) for k in keep}
        q['ros'] = [x for x in (p.get('ros') or []) if x[0] in (NW, FW)]
        q['pri'] = pri.get(p['id'])
        players.append(q)
    I = {'asof': D['asof'], 'fw': FW, 'nw': NW, 'sched': SCHED, 'dvp': D.get('dvp', {}), 'mu': mu, 'players': players}
    json.dump(I, open('bet_inputs.json', 'w'), separators=(',', ':'))
    return I, D

# ------------------------------------------------------------------ Vegas: ESPN's current odds when posted, else the schedule's
def espn_totals(I):
    """Implied team totals from ESPN's current odds (live.json, refreshed every 10 minutes): over/under and spread."""
    out = {}
    try: L = json.load(open('live.json'))
    except Exception: return out
    if int(L.get('week') or 0) != I['fw']: return out
    for g in L.get('games') or []:
        ou, det = g.get('ou'), g.get('odds') or ''
        if g.get('state') != 'pre' or not ou: continue
        try: ou = float(ou)
        except (TypeError, ValueError): continue
        m = re.match(r'\s*([A-Z]{2,4})\s*([-+]?\d+(?:\.\d+)?)', det)
        fav, sp = (TEAMFIX.get(m.group(1), m.group(1)), abs(float(m.group(2)))) if m else (None, 0.0)
        for tm in (g['home'], g['away']):
            out[tm] = round(ou / 2 + (sp / 2 if tm == fav else -sp / 2 if fav else 0), 2)
    return out

# ------------------------------------------------------------------ lines
def wkproj(p, FW):
    if p.get('inj') in ('Out', 'IR', 'Doubtful'): return 0.0
    if p['nw'] == FW: return float(p.get('proj') or 0)
    r = next((x for x in p.get('ros') or [] if x[0] == FW), None); return float(r[2]) if r else 0.0

def news_status(I):
    """Latest clear news status per player since his last game: 'out' (ruled out, expected to miss time, placed on IR...)
    pulls his lines, as books do; a later 'cleared' / 'will play' report restores them."""
    try: N = json.load(open('news.json')).get('items') or []
    except Exception: return {}
    last = {}
    for p in I['players']:
        G = [r[0] for r in (p.get('gl') or [])]
        k = next((x[5] for x in I['sched'].get(p['t'], []) if G and x[0] == max(G) and len(x) > 5 and x[5]), None)
        last[p['id']] = k
    st = {}
    for it in sorted(N, key=lambda x: x.get('d') or ''):
        if it.get('st') not in ('out', 'ok'): continue
        for pid in it.get('p') or []:
            since = last.get(pid) or (NOW - datetime.timedelta(days=6)).isoformat()
            if (it.get('d') or '') >= since: st[pid] = (it['st'], it['h'], it.get('s'))
    return {pid: v for pid, v in st.items() if v[0] == 'out'}

def build_lines(I):
    FW, SCHED, DVP, MU = I['fw'], I['sched'], I['dvp'], I['mu']
    QS = json.load(open('prop_qs.json')); ESPN = espn_totals(I); global PULLED; PULLED = news_status(I)
    sch = lambda tm: next((x for x in SCHED.get(tm, []) if x[0] == FW), None)
    rows = []
    for p in I['players']:
        pos = p['p']; e = sch(p['t']); wp = wkproj(p, FW)
        if not e or not e[1] or p['nw'] > FW or wp < (10 if pos == 'QB' else 4): continue   # Monday-night teams still get next week's lines
        if p['id'] in PULLED: continue                                                              # news says he will miss the game
        G = [r for r in (p.get('gl') or []) if r[0] < FW]
        snap = {w[0]: w[3] for w in (p.get('wk') or []) if w[3] is not None}
        med = sorted(snap.values())[len(snap) // 2] if snap else None
        def partial(r):
            if pos == 'QB': return r[2] < 15
            s_ = snap.get(r[0]); return bool(med and s_ is not None and s_ < .5 * med)
        F = [r for r in G if not partial(r)]; pr = p.get('pri')
        if not F and not pr: continue
        last_part = bool(G and partial(G[-1]))
        if pos == 'QB' and not (p.get('role') == 'QB1' or (G and not last_part)): continue          # books post QB lines for starters
        it_sched = e[3] if e[3] is not None else 22.5; it = ESPN.get(p['t'], it_sched); dv = ((DVP.get(e[1]) or {}).get(pos) or [None, None, 1.0])[2] or 1.0
        bmp = next((b for w, b in (p.get('bmp') or []) if w == FW), 0.0) or 0.0
        rows.append(dict(p=p, pos=pos, F=F, pr=pr, last_part=last_part, it=it, it_src='ESPN' if p['t'] in ESPN else 'schedule', dv=dv, bmp=bmp, opp=e[1],
                         kick=e[5] if len(e) > 5 else None, wp=wp))

    def volume(r, v, d, Wv):
        h = [x[GLI[v]] for x in r['F']]; n = len(h)
        ws = sum(x * d ** (n - 1 - i) for i, x in enumerate(h)); wn = sum(d ** (n - 1 - i) for i in range(n))
        pr = r['pr']; pv = pr[v] / pr['n'] if pr else None
        if pv is not None: return (ws + Wv * pv) / (wn + Wv)
        return ws / wn if wn else None
    def mean_for(r, k):
        P_ = PAR[k]; v = VOL[k]; num, den = EFF[k]; pos = r['pos']
        vol = volume(r, v, P_['d'], P_['Wv'])
        if vol is None: return None
        if P_['kb'] and r['bmp']: vol += P_['kb'] * r['bmp'] / (0.75 if v == 'car' else 1.4 if pos == 'RB' else 1.75) * (1 if (pos == 'RB') == (v == 'car') else .5)
        pr = r['pr'] or {}; cs_n = sum(x[GLI[num]] for x in r['F']); cs_d = sum(x[GLI[den]] for x in r['F'])
        eff = (cs_n + P_['pw'] * pr.get(num, 0) + P_['k'] * MU[pos][num]) / (cs_d + P_['pw'] * pr.get(den, 0) + P_['k'])
        ctx = max(.85, min(1.15, (r['it'] / 22.5) ** P_['a'] * r['dv'] ** P_['b']))
        m = vol * eff * ctx
        if r['last_part']: m *= P_['pp']
        if not r['pr']: m *= P_['nf']
        return m, vol, eff

    # our projection relative to a book-style fantasy baseline, centered by position (the pick signal)
    for r in rows:
        n = len(r['F']); fpg = r['p'].get('fpg'); prf = (r['pr'] or {}).get('fp')
        fpb = (fpg * n + prf * 3) / (n + 3) if (fpg is not None and n and prf is not None) else (fpg if (fpg is not None and n) else prf)
        r['s'] = r['wp'] / max(fpb, 4) if fpb else None
    S = {}
    for r in rows:
        if r['s']: S.setdefault(r['pos'], []).append(r['s'])
    MED = {q: sorted(v)[len(v) // 2] for q, v in S.items()}
    allm = {}
    for r in rows:
        for k in ('py', 'ty'):
            res = mean_for(r, k)
            if res: allm.setdefault((k, r['pos']), []).append(res[0])
    CEN = {key: sorted(v)[len(v) // 2] for key, v in allm.items() if len(v) >= 5}
    qb_done = set(); lines = []
    for r in sorted(rows, key=lambda r: -r['wp']):
        pos, p = r['pos'], r['p']
        if pos == 'QB':
            if p['t'] in qb_done: continue                                                       # one starting QB per team
            qb_done.add(p['t'])
        vtg = volume(r, 'tg', .75, 2) or 0; vcar = volume(r, 'car', .75, 2) or 0
        sn = max(.8, min(1.25, r['s'] / MED[pos])) if r['s'] and MED.get(pos) else 1.0
        stats = ['py', 'ptd', 'ryq'] if pos == 'QB' else (['ry'] if pos == 'RB' and vcar >= 8 else []) + (['rec', 'ty'] if vtg >= (2.5 if pos == 'RB' else 3.5) else [])
        for k in stats:
            res = mean_for(r, k)
            if not res: continue
            m, vol, eff = res
            if k == 'ryq':
                base_ry = (sum(x[7] for x in r['F']) + (r['pr'] or {}).get('ry', 0)) / max(1, len(r['F']) + (r['pr'] or {}).get('n', 0))
                if base_ry < 12: continue
            if PAR[k].get('sh') and CEN.get((k, pos)) is not None: m = CEN[(k, pos)] + PAR[k]['sh'] * (m - CEN[(k, pos)])
            raw = m * PAR[k]['c']
            line = (.5 if m < .70 else 1.5 if m < 2.55 else 2.5) if k == 'ptd' else math.floor(raw) + .5   # passing-TD cutoffs tuned on 2024
            if k == 'py' and line < 150.5: continue
            mm = m * (sn if k == 'ptd' else 1 + (sn - 1) * .7)
            if k == 'ptd': pm = 1 - sum(math.exp(-mm) * mm ** i / math.factorial(i) for i in range(int(line) + 1))
            else: pm = 1 - cdf(QS[QK(pos, k)], (line + 1e-4) / max(mm, .05))
            po = min(.62, max(.38, .5 * pm + .25))
            kk = 'ry' if k == 'ryq' else k
            lines.append({'pid': p['id'], 't': p['t'], 'opp': r['opp'], 'k': kk, 'line': line, 'mm': round(float(mm), 2), 'po': round(float(po), 3),
                          'pick': bool(k in PICKS and max(po, 1 - po) >= PICK_MIN), 'kick': r['kick'], 'q': bool(p.get('inj') == 'Questionable'),
                          'vol': round(float(vol), 1), 'eff': round(float(eff), 3), 'it': round(float(r['it']), 1), 'its': r['it_src'], 'bmp': round(float(r['bmp']), 1), 'pp': bool(r['last_part'])})
    return lines

# ------------------------------------------------------------------ history: opening line and every move, with the reason
def why(old, new):
    R = []
    if abs((old.get('it') or 0) - (new.get('it') or 0)) >= .5: R.append(f"Vegas team total {old.get('it')} → {new.get('it')}")
    if abs((old.get('bmp') or 0) - (new.get('bmp') or 0)) >= .3: R.append('teammate injury news' if (new.get('bmp') or 0) > (old.get('bmp') or 0) else 'teammate returning')
    if old.get('q') != new.get('q'): R.append('listed questionable' if new.get('q') else 'off the injury report')
    if abs((old.get('vol') or 0) - (new.get('vol') or 0)) >= .3 and not R: R.append('new game data')
    return '; '.join(R) or 'updated projections'

def merge_history(new_lines, fw):
    old = {}
    try:
        O = json.load(open('lines.json'))
        if O.get('wk') == fw: old = O
    except Exception: pass
    prev = {(l['pid'], l['k']): l for l in old.get('lines') or []}
    moves = list(old.get('moves') or [])
    for l in new_lines:
        o = prev.get((l['pid'], l['k']))
        if not o:
            l['open'] = l['line']; l['opened'] = STAMP; l['mv'] = []
            continue
        l['open'], l['opened'], l['mv'] = o.get('open', o['line']), o.get('opened', old.get('at', STAMP)), list(o.get('mv') or [])
        if l['line'] != o['line']:
            w = why(o, l); l['mv'].append([STAMP, o['line'], l['line'], w])
            moves.append({'pid': l['pid'], 'k': l['k'], 'from': o['line'], 'to': l['line'], 'at': STAMP, 'why': w})
    gone = [k for k in prev if k not in {(l['pid'], l['k']) for l in new_lines}]
    for pid, k in gone:
        n_ = PULLED.get(pid); w_ = f"pulled: {n_[1]} ({n_[2]})" if n_ else 'line pulled (injury report or role change)'
        moves.append({'pid': pid, 'k': k, 'from': prev[(pid, k)]['line'], 'to': None, 'at': STAMP, 'why': w_})
    sig = lambda L: sorted((l['pid'], l['k'], l['line'], round(l['po'], 2), l['q']) for l in L)
    changed = (not old) or sig(new_lines) != sig(old.get('lines') or [])
    out = {'wk': fw, 'at': STAMP if changed else old.get('at', STAMP), 'odds_from': None, 'bt': BT, 'lines': new_lines, 'moves': moves[-60:],
           'pulled': [{'pid': k, 'h': v[1], 's': v[2]} for k, v in PULLED.items()]}
    return out, changed

if __name__ == '__main__':
    if REFRESH:
        if not os.path.exists('bet_inputs.json'): print('bet_inputs.json not found yet (the data job makes it); skipping'); sys.exit(0)
        I = json.load(open('bet_inputs.json')); D = None
    else:
        I, D = build_inputs()
    try:
        L = build_lines(I)
    except Exception as ex:   # never break the job: keep the previous lines
        print('could not rebuild lines, keeping the previous ones:', ex); sys.exit(0)
    out, changed = merge_history(L, I['fw'])
    out['odds_from'] = 'ESPN (current odds)' if any(l['its'] == 'ESPN' for l in L) else 'nflverse schedule (opening odds)'
    if changed or not os.path.exists('lines.json'):
        json.dump(out, open('lines.json', 'w'), separators=(',', ':'))
    if D is not None:
        D['lines'] = out; json.dump(D, open('ff_data.json', 'w'), separators=(',', ':'))
    mv = sum(1 for m in out['moves'] if m['at'] == STAMP)
    print(f"lines: {len(L)} for week {I['fw']} ({sum(l['pick'] for l in L)} picks at {int(PICK_MIN*100)}%+), {mv} moved this run, odds from {out['odds_from']}"
          + ('' if changed else ' (no change)'))
