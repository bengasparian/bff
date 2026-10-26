#!/usr/bin/env python3
"""Parlay tracker for BFF, built from this week's predicted lines (ff_lines.py).

Each run:
  1. Reads this week's lines and picks (lines.json) and player game logs (ff_data.json in the data job,
     bet_inputs.json in the 10-minute job).
  2. Builds the best 2-, 3- and 5-pick parlays from tested picks only (55%+ chance: receiving-yard unders
     where BFF's model is 10%+ below ESPN and Sleeper), one leg per game and per player, at most
     2 of one stat, no questionable players.
     They follow the lines until the week's first kickoff, then lock.
  3. Grades every locked parlay from official box scores: a leg is a hit, a miss, or void if the player did not play.
     A parlay is won when no leg misses and at least one leg hits (voided legs drop out, as at sportsbooks).
  4. Writes parlay_history.json (the permanent record) and parlays.json (what the page shows).
For entertainment only (21+ where legal).
"""
import json, math, os, sys, datetime

REFRESH = '--refresh' in sys.argv
NOW = datetime.datetime.fromisoformat(os.environ['BFF_NOW']) if os.environ.get('BFF_NOW') else datetime.datetime.now(datetime.timezone.utc)
SRC = 'bet_inputs.json' if REFRESH else 'ff_data.json'
if not os.path.exists(SRC) or not os.path.exists('lines.json'):
    print(f'{SRC} or lines.json not found yet; skipping'); sys.exit(0)
D = json.load(open(SRC)); P = D['players']; PI = {p['id']: p for p in P}; SCHED = D.get('sched', {})
LN = json.load(open('lines.json')); FW = LN['wk']
HIST_FILE = 'parlay_history.json'
H = json.load(open(HIST_FILE)) if os.path.exists(HIST_FILE) else {}
# one season per file: when a new season starts, last season's record is kept as parlay_history_<season>.json
SEASON = int(D['asof'].get('season') or NOW.year)
if H.get('_season') not in (None, SEASON):
    json.dump(H, open(f"parlay_history_{H['_season']}.json", 'w'), indent=1); print('new season: archived', H['_season']); H = {}
H['_season'] = SEASON
WKS = lambda: [k for k in H if not k.startswith('_')]

def suggest():
    legs = []
    for x in LN.get('lines') or []:
        if x.get('wk', LN.get('wk')) != LN.get('wk'): continue   # parlays are for the coming week only
        p = PI.get(x['pid'])
        if not p or not x.get('pick') or x.get('q') or p.get('inj') in ('Out', 'IR', 'Doubtful'): continue
        if x.get('kick') and datetime.datetime.fromisoformat(x['kick']) <= NOW: continue
        lean = 'Over' if x['po'] >= .5 else 'Under'
        legs.append({**x, 'lean': lean, 'pr': round(max(x['po'], 1 - x['po']), 4)})
    legs.sort(key=lambda l: -l['pr'])
    def pick(n):
        o, games, people = [], set(), set()
        for l in legs:
            g = ''.join(sorted([l['t'], l['opp']]))
            if g in games or l['pid'] in people or sum(1 for y in o if y['k'] == l['k']) >= 2: continue
            games.add(g); people.add(l['pid']); o.append(l)
            if len(o) == n: return o
        return None
    res = []
    for typ, n in (('safe', 2), ('bal', 3), ('long', 5)):
        sel = pick(n)
        if sel: res.append({'type': typ, 'prob': round(math.prod(l['pr'] for l in sel), 4),
                            'legs': [{**{k: l.get(k) for k in ('pid', 't', 'opp', 'k', 'line', 'lean', 'pr')}, 'book': 'bff', 'n': PI[l['pid']]['n'], 'pos': PI[l['pid']]['p']} for l in sel]})
    return res

kicks = [datetime.datetime.fromisoformat(x[5]) for L in SCHED.values() for x in L if x[0] == FW and len(x) > 5 and x[5]]
first = min(kicks) if kicks else None; key = str(FW)
if first and NOW < first:
    sug = suggest()
    if key not in H or sug != H[key].get('parlays'):
        H[key] = {'wk': FW, 'made': NOW.isoformat(timespec='minutes'), 'locks': first.isoformat(), 'lines_at': LN.get('at'), 'src': 'BFF predicted lines', 'parlays': sug}
    print(f'week {FW}: {len(sug)} parlay(s) from tested picks; they lock at {first.isoformat()}' if sug else f'week {FW}: no picks strong enough this week')
elif key in H: print(f'week {FW}: locked since {H[key]["locks"]}')
else: print(f'week {FW}: first kickoff passed before any parlay was recorded')

STAT = {'py': lambda r: r[3], 'ptd': lambda r: r[4], 'ry': lambda r: r[7], 'ty': lambda r: r[11], 'rec': lambda r: r[9], 'td': lambda r: r[8] + r[12]}
def final(team, w):
    e = next((x for x in SCHED.get(team, []) if x[0] == w), None); return bool(e and e[4] is not None)
for wk in WKS():
    W = H[wk]; w = int(wk)
    for par in W['parlays']:
        for lg in par['legs']:
            if lg.get('res') in ('hit', 'miss', 'void'): continue                       # graded once, never changed
            if not final(lg['t'], w): lg['res'] = 'pending'; continue
            p = PI.get(lg['pid']); row = next((r for r in (p or {}).get('gl') or [] if r[0] == w), None)
            played = row is not None or any(x[0] == w and (x[3] or 0) > 0 for x in (p or {}).get('wk') or [])
            if not played: lg['res'] = 'void'; lg['act'] = None; continue
            a = STAT[lg['k']](row) if row else 0; lg['act'] = a
            lg['res'] = 'hit' if (a > lg['line'] if lg['lean'] == 'Over' else a < lg['line']) else 'miss'
        R = [l['res'] for l in par['legs']]
        par['status'] = 'lost' if 'miss' in R else 'pending' if 'pending' in R else 'won' if 'hit' in R else 'void'
new_h = json.dumps(H, indent=1)
if not os.path.exists(HIST_FILE) or open(HIST_FILE).read() != new_h: open(HIST_FILE, 'w').write(new_h)
page = {'fw': FW, 'season': SEASON, 'start': min((int(k) for k in WKS()), default=FW), 'weeks': [H[k] for k in sorted(WKS(), key=int, reverse=True)]}
new_p = json.dumps(page, separators=(',', ':'))
if not os.path.exists('parlays.json') or open('parlays.json').read() != new_p: open('parlays.json', 'w').write(new_p)
if not REFRESH:
    D['parl'] = page; json.dump(D, open('ff_data.json', 'w'), separators=(',', ':'))
done = [p for k in WKS() for p in H[k]['parlays'] if p['status'] in ('won', 'lost')]
print(f'parlay tracker: {len(WKS())} week(s) recorded, {sum(p["status"] == "won" for p in done)} won of {len(done)} graded')
