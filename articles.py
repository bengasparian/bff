"""BFF Originals: data-driven fantasy football articles, written and updated automatically, like a weekly newsletter.

Runs every 10 minutes with the live job (standard library only). Each run decides what should exist right now (Eastern time):
  * Thursday outlook    - Thursday 8 AM, the Thursday game(s): matchup, fantasy breakdown, start/sit, best bets, our pick.
  * Thursday recap      - Friday 7 AM (once the game is final): how it happened, every fantasy-relevant line, stock up and
                          down, waiver adds, what is next.
  * Injury report       - Friday 5 PM: who is out, game-time decisions, quarterback situations and who benefits.
  * Sunday outlook      - Saturday 8 AM: the whole Sunday slate, game by game, start/sit, sleepers and best bets.
  * Sunday recap        - once the afternoon games are final (before the night game): scores, top performances, game by
                          game, stock up and down, injuries to watch and an early waiver look.
  * Sunday night recap  - once the night game is final.
  * Monday outlook      - Monday 8 AM; Monday recap once the game is final.
  * Other game days     - Friday, Saturday, Christmas or international games: an outlook that morning, a recap the next.
  * Fantasy landscape   - Tuesday 10 AM, after the week: MVPs, risers, fallers, injury fallout, waiver priorities, buy
                          low and sell high, next week's byes and best matchups, and our weekly calls scorecard.
  * Breaking news       - a relevant player ruled out, placed on injured reserve, traded or released (at most 3 a run, 12 a day).
Outlooks and the injury report are rewritten when their facts change (until kickoff), with a dated update note.

Writers: BFF's own writer (always on, free) writes from the data. If the repository has an ANTHROPIC_API_KEY secret,
Claude rewrites each article from the same fact sheet (model: BFF_AI_MODEL, default claude-sonnet-5-5; at most
BFF_AI_MAX_DAY calls a day, default 30); any number Claude uses must appear in the facts, or BFF's own version is kept.

Inputs: index.html (the page's data), live.json (scores, box scores, scoring plays), news.json (headlines), lines.json,
proj_history.json, articles.json.   Output: articles.json.   Testing: BFF_NOW=2026-10-18T12:00:00Z python articles.py
"""
import json, os, re, sys, hashlib, datetime, urllib.request
try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo('America/New_York')
except Exception:
    ET = datetime.timezone(datetime.timedelta(hours=-4))
UTC = datetime.timezone.utc
NOW = datetime.datetime.fromisoformat(os.environ['BFF_NOW'].replace('Z', '+00:00')) if os.environ.get('BFF_NOW') else datetime.datetime.now(UTC)
OUT = 'articles.json'; KEEP_DAYS = 21; MAX_BRK_RUN = 3; MAX_BRK_DAY = 12
DOW = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


# ---------------------------------------------------------------- small helpers
def iso(d): return d.astimezone(UTC).isoformat(timespec='seconds')
def pdt(s):
    try:
        d = datetime.datetime.fromisoformat(str(s).replace('Z', '+00:00')); return (d if d.tzinfo else d.replace(tzinfo=UTC)).astimezone(UTC)
    except Exception: return None
def load(path, default):
    try: return json.load(open(path))
    except Exception: return default
def page_data():
    """the data embedded in index.html (ff_data.json is not kept in the repository)"""
    if os.path.exists('ff_data.json') and os.environ.get('BFF_USE_FF_DATA'): return json.load(open('ff_data.json'))
    h = open('index.html', encoding='utf-8').read(); i = h.index('const D=') + 8; j = h.index(';\n', i)
    return json.loads(h[i:j].replace('<\\/', '</'))
def f1(x): return f'{x:.1f}'
def fnum(x): return str(int(x)) if float(x) == int(x) else f1(x)
def seed(*a): return int(hashlib.md5('|'.join(map(str, a)).encode()).hexdigest()[:8], 16)
def pick(opts, *k): return opts[seed(*k) % len(opts)]
def normn(s): return re.sub(r'\b(jr|sr|ii|iii|iv|v)\b', '', re.sub(r"[.'’`-]", '', str(s or '').lower())).strip()
def last(n): return re.sub(r'\s+(Jr\.?|Sr\.?|II|III|IV|V)$', '', n).split()[-1]
def poss(n): return n + ("'" if n.endswith('s') else "'s")
def plural(n, w, pl=None): return f"{fnum(n)} {w if n == 1 else (pl or w + 's')}"
def andj(L):
    L = [x for x in L if x]
    return '' if not L else L[0] if len(L) == 1 else ', '.join(L[:-1]) + ' and ' + L[-1]
def ordn(n): return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"
WORDS = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten']
def numw(n): return WORDS[n] if 0 <= n < len(WORDS) else str(n)
def cap(s): return s[:1].upper() + s[1:]
TEAMS = {'ARI': 'Cardinals', 'ATL': 'Falcons', 'BAL': 'Ravens', 'BUF': 'Bills', 'CAR': 'Panthers', 'CHI': 'Bears', 'CIN': 'Bengals', 'CLE': 'Browns', 'DAL': 'Cowboys', 'DEN': 'Broncos',
         'DET': 'Lions', 'GB': 'Packers', 'HOU': 'Texans', 'IND': 'Colts', 'JAX': 'Jaguars', 'KC': 'Chiefs', 'LA': 'Rams', 'LAC': 'Chargers', 'LV': 'Raiders', 'MIA': 'Dolphins',
         'MIN': 'Vikings', 'NE': 'Patriots', 'NO': 'Saints', 'NYG': 'Giants', 'NYJ': 'Jets', 'PHI': 'Eagles', 'PIT': 'Steelers', 'SEA': 'Seahawks', 'SF': '49ers', 'TB': 'Buccaneers',
         'TEN': 'Titans', 'WAS': 'Commanders'}
def tm_name(t): return TEAMS.get(t, t)
def a_an(w): return ('an ' if str(w)[:1].upper() in 'AEIOU' else 'a ') + str(w)
def the(t): return 'the ' + tm_name(t)
def The(t): return 'The ' + tm_name(t)
def et(d): return d.astimezone(ET)
def at_et(day, h, m=0): return datetime.datetime.combine(day, datetime.time(h, m), ET).astimezone(UTC)


# ---------------------------------------------------------------- the data
D = page_data(); P = D['players']; PI = {p['id']: p for p in P}; SEASON = D['asof']['season']
LIVE = load('live.json', {}); NEWS = load('news.json', {}); LINES = load('lines.json', None) or D.get('lines') or {}
PH = (load('proj_history.json', {}) or {}).get(str(SEASON), {})
OLD = load(OUT, {}); OLD = OLD if isinstance(OLD, dict) else {}
ARTS = {a['id']: a for a in OLD.get('items') or [] if isinstance(a, dict) and a.get('id')}
if OLD.get('season') not in (None, SEASON): ARTS = {}
SEEN = dict(OLD.get('seen') or {}) if isinstance(OLD.get('seen'), dict) else {}
# Claude calls in the last 24 hours: a hard daily cap keeps the optional AI writer's cost bounded
AI_LOG = [t for t in OLD.get('ai_log') or [] if pdt(t) and NOW - pdt(t) < datetime.timedelta(hours=24)]
try: AI_MAX = max(0, int(os.environ.get('BFF_AI_MAX_DAY') or 30))
except ValueError: AI_MAX = 30
NAMEIX = {}
for p in P: NAMEIX.setdefault((p['t'], normn(p['n'])), p)
OWN = lambda p: p.get('own')


def proj_wk(p, w):
    if p.get('nw') == w: return 0.0 if p.get('inj') in ('Out', 'IR', 'Doubtful') else float(p.get('proj') or 0)
    for r in p.get('ros') or []:
        if r[0] == w: return float(r[2] or 0)
    return 0.0
def proj_then(p, w):
    """what BFF projected for week w: the projection locked at kickoff when saved, else today's"""
    h = (PH.get(str(w)) or {}).get(p['id'])
    if h: return float(h[0])
    v = proj_wk(p, w); return v if v > 0 else None
def ppr(r): return (r.get('py') or 0) * .04 + (r.get('ptd') or 0) * 4 - (r.get('int') or 0) * 2 + (r.get('ry') or 0) * .1 + (r.get('rtd') or 0) * 6 + (r.get('ty') or 0) * .1 + (r.get('rectd') or 0) * 6 + (r.get('rec') or 0) - (r.get('fl') or 0) * 2
def tds(r): return int((r.get('rtd') or 0) + (r.get('rectd') or 0))
def yd(n): return plural(int(n), 'yard')


# ---------------------------------------------------------------- games
def games():
    """every game from the schedule (home team's row), with Vegas numbers and kickoff; live scores, quarters and ESPN ids override"""
    G = {}
    for t, rows in (D.get('sched') or {}).items():
        for r in rows:
            if len(r) < 6 or not r[2] or not r[5]: continue
            opp_row = next((x for x in D['sched'].get(r[1], []) if x[0] == r[0]), None)
            G[(r[0], t)] = dict(wk=r[0], home=t, away=r[1], kick=pdt(r[5]), sp=r[6] if len(r) > 6 else None, ou=r[7] if len(r) > 7 else None, ih=r[3], ia=opp_row[3] if opp_row else None,
                                hs=r[4], as_=opp_row[4] if opp_row else None, ls=None, gid=None)
    for x in LIVE.get('games') or []:
        for g in G.values():
            if g['home'] == x.get('home') and g['away'] == x.get('away') and abs((g['kick'] - (pdt(x.get('kick')) or g['kick'])).total_seconds()) < 86400 * 3:
                g.update(state=x.get('state'), gid=str(x.get('id')), ls=x.get('ls'), hs=x.get('hs') if x.get('hs') is not None else g['hs'], as_=x.get('as') if x.get('as') is not None else g['as'])
    for g in G.values():
        if 'state' not in g or g['state'] is None: g['state'] = 'post' if g['hs'] is not None else 'pre'
    return sorted(G.values(), key=lambda g: g['kick'])
GAMES = games()
def gday(g): return et(g['kick']).date()
def ghour(g): return et(g['kick']).hour
def gtime(g): t = et(g['kick']); return t.strftime('%-I:%M %p ET') if t.minute else t.strftime('%-I %p ET')
def gdaytime(g): return f"{DOW[gday(g).weekday()]} at {gtime(g)}"
def fav_of(g):
    """(favorite, points) from the home spread (negative = home favored)"""
    if g['sp'] is None or g['sp'] == 0: return None, 0
    return (g['home'], -g['sp']) if g['sp'] < 0 else (g['away'], g['sp'])
def win_prob(g, tm):
    if g['sp'] is None: return None
    z = -g['sp'] / 13.45; import math; ph = .5 * (1 + math.erf(z / math.sqrt(2)))
    return ph if tm == g['home'] else 1 - ph
def vegas(g):
    if g['sp'] is None or g['ou'] is None: return ''
    fav, sp = fav_of(g)
    return f"{the(fav)} favored by {fnum(sp)} and a total of {fnum(g['ou'])}" if fav else f"a pick'em with a total of {fnum(g['ou'])}"
def record(tm, through_wk):
    W = L = T = 0
    for x in (D.get('sched') or {}).get(tm, []):
        if x[0] > through_wk or not x[1] or x[4] is None: continue
        o = next((y for y in D['sched'].get(x[1], []) if y[0] == x[0]), None)
        if not o or o[4] is None: continue
        W, L, T = W + (x[4] > o[4]), L + (x[4] < o[4]), T + (x[4] == o[4])
    for g in GAMES:   # live finals not yet in the schedule data
        if g['wk'] <= through_wk and g['state'] == 'post' and tm in (g['home'], g['away']):
            row = next((x for x in D['sched'].get(tm, []) if x[0] == g['wk']), None)
            if row and row[4] is None and g['hs'] is not None and g['as_'] is not None:
                mine, theirs = (g['hs'], g['as_']) if tm == g['home'] else (g['as_'], g['hs'])
                W, L, T = W + (mine > theirs), L + (mine < theirs), T + (mine == theirs)
    return f"{W}-{L}" + (f"-{T}" if T else '')
def last_result(tm, before_wk):
    """(week, opponent, our score, their score) of the team's most recent finished game before week before_wk"""
    for x in sorted((D.get('sched') or {}).get(tm, []), reverse=True):
        if x[0] >= before_wk or not x[1] or x[4] is None: continue
        o = next((y for y in D['sched'].get(x[1], []) if y[0] == x[0]), None)
        if o and o[4] is not None: return x[0], x[1], x[4], o[4]
    return None
def result_words(tm, before_wk):
    r = last_result(tm, before_wk)
    if not r: return ''
    w_, opp, a, b = r
    return (f"beat the {tm_name(opp)} {a}-{b}" if a > b else f"lost to the {tm_name(opp)} {b}-{a}" if a < b else f"tied the {tm_name(opp)} {a}-{b}") + f" in week {w_}"
def hot_hand(teams, before_wk):
    best = None
    for p in P:
        if p['t'] not in teams or p.get('inj') in ('Out', 'Doubtful', 'IR'): continue   # a player ruled out can't come in hot
        L = [x for x in p.get('wk') or [] if x[0] < before_wk]
        if L and L[-1][1] is not None and L[-1][1] >= 20 and (best is None or L[-1][1] > best[1]): best = (p, L[-1][1], L[-1][0])
    return best
def next_game(tm, after_wk):
    return next(((x[0], x[1], x[2]) for x in sorted((D.get('sched') or {}).get(tm, [])) if x[0] > after_wk and x[1]), None)
def team_players(t, w, n=3, pos=None):
    L = [p for p in P if p['t'] == t and (pos is None or p['p'] in pos) and proj_wk(p, w) > 0]
    return sorted(L, key=lambda p: -proj_wk(p, w))[:n]
DVP = D.get('dvp') or {}
def dvp_rank(opp, pos):
    v = (DVP.get(opp) or {}).get(pos)   # [points allowed a game, games, factor, rank (1 = allows the fewest)]
    return v[3] if isinstance(v, list) and len(v) > 3 else None
def vs(mw):
    """'against a soft defense' / ', though he faces a tough one'"""
    return '' if not mw else (f", though he faces {mw}" if 'fewest' in mw else f" against {mw}")
def dot(s): return s if s.endswith('.') else s + '.'
def matchup_words(opp, pos):
    r = dvp_rank(opp, pos)
    if r is None: return ''
    if r >= 26: k = 33 - r; return f"{a_an(tm_name(opp))} defense that has allowed the {'' if k == 1 else ordn(k) + '-'}most fantasy points to {pos}s"
    if r <= 6: return f"{a_an(tm_name(opp))} defense that has allowed the {'' if r == 1 else ordn(r) + '-'}fewest fantasy points to {pos}s"
    return ''
def wk_rank(p, w):
    L = sorted([q for q in P if q['p'] == p['p'] and proj_wk(q, w) > 0], key=lambda q: -proj_wk(q, w))
    return L.index(p) + 1 if p in L else None
def usual_rank(p):
    L = sorted([q for q in P if q['p'] == p['p'] and (q.get('rl') or q.get('fpg'))], key=lambda q: -(q.get('rl') or q.get('fpg') or 0))
    return L.index(p) + 1 if p in L else None
def picks_for(teams, w):
    lw = LINES.get('wk')
    L = [x for x in (LINES.get('lines') or []) if x.get('pick') and PI.get(x.get('pid')) and x.get('t') in teams and (x.get('wk') or lw) == w]
    return sorted(L, key=lambda x: -max(x.get('po', .5), 1 - x.get('po', .5)))
SNAME = {'py': 'passing yards', 'ptd': 'passing TDs', 'ry': 'rushing yards', 'ty': 'receiving yards', 'rec': 'receptions', 'td': 'anytime TD'}
def low_snap(p, w):
    """his snap share in week w when it was far below his usual (a starter who barely played usually got hurt in the
    game or was eased back in), else None"""
    L = [x for x in (p.get('wk') or []) if x[3] is not None and x[0] <= w]
    if not L or L[-1][0] != w or L[-1][3] >= .4 or len(L) < 2: return None
    before = [x[3] for x in L[:-1]]
    return L[-1][3] if (sum(before) / len(before) >= .6 or max(before) >= .75) else None
def inj_word(p):
    """how to name a player's status in a sentence: an official or ESPN listing by its name; BFF's own between-reports
    estimate (no injury report for the game yet) as what really happened, so it never reads like an official listing"""
    s = p.get('inj') or ''
    if s == 'IR': return 'injured reserve'
    if p.get('injs') == 'expected':
        m = re.search(r'week (\d+)', p.get('injn') or '')
        return ('expected out' if s == 'Out' else f"missed week {m.group(1)}, status not set yet" if m else 'status not set yet')
    if p.get('injs') == 'news' and s == 'Questionable': return 'questionable (back from the exempt list)' if 'exempt' in (p.get('injn') or '') else 'questionable'
    return s.lower()
def injured(teams, w, statuses=('Out', 'Doubtful', 'Questionable', 'IR')):
    out = [p for p in P if p['t'] in teams and p.get('inj') in statuses and ((p.get('rl') or 0) >= 7 or (p.get('ecr') or 999) <= 160 or (p.get('pj0') or 0) >= 6)]
    return sorted(out, key=lambda p: -((p.get('rl') or 0) + (p.get('pj0') or 0)))
def qb_of(tm): return next((q for q in P if q['t'] == tm and q['p'] == 'QB' and q.get('qbs')), None) or next((q for q in P if q['t'] == tm and q['p'] == 'QB' and q.get('role') == 'QB1'), None)
def pace(tm):
    q = next((p for p in P if p['t'] == tm and p.get('tpl')), None)
    return (q.get('tpl'), q.get('tpr')) if q else (None, None)
def season_games(p, before_wk): return [x for x in (p.get('wk') or []) if x[0] < before_wk]


# ---------------------------------------------------------------- article pieces
def P_(text): return ['p', text]
def H_(text): return ['h', text]
def UL(items): return ['ul', [x for x in items if x]]
def PL(p, note): return ['pl', p['id'], note]
def gref(g): return g.get('gid') or f"w{g['wk']}{g['home']}"   # ESPN id, else the schedule id the page also understands
def GH(g): return ['game', g['away'], g['home'], gref(g)]
def SCORE(g): return ['score', g['away'], g['home'], g['as_'], g['hs'], (g.get('ls') or [None, None])[0], (g.get('ls') or [None, None])[1], gref(g)]
def SCORES(gs): return ['scores', [[g['away'], g['home'], g['as_'], g['hs'], gref(g)] for g in gs]]
def PULL(text): return ['pull', text]
def facts_digest(players, gs):
    return {'p': {p['id']: [p.get('inj'), round(proj_wk(p, p.get('nw') or 0), 1)] for p in players}, 'g': {f"{g['away']}@{g['home']}": [g['sp'], g['ou']] for g in gs}}
def change_notes(old, new):
    """what changed since the last version (injury statuses, projections, lines)"""
    notes = []
    for pid, (st, pj) in new.get('p', {}).items():
        o = (old or {}).get('p', {}).get(pid)
        if not o or pid not in PI: continue
        n = PI[pid]['n']
        if o[0] != st: notes.append(f"{n} is now {st.lower() if st else 'off the injury report'}" if st not in ('Out', 'IR') else f"{n} has been ruled out")
        elif abs((o[1] or 0) - (pj or 0)) >= 1.5: notes.append(f"{poss(n)} projection moved from {f1(o[1])} to {f1(pj)}")
    for k, (sp, ou) in new.get('g', {}).items():
        o = (old or {}).get('g', {}).get(k)
        if o and o[1] is not None and ou is not None and abs(o[1] - ou) >= 1.5: notes.append(f"the {k.replace('@', ' at ')} total moved from {fnum(o[1])} to {fnum(ou)}")
    return notes[:4]
def uniq(L):
    seen = []; [seen.append(p['id'] if isinstance(p, dict) else p) for p in L if (p['id'] if isinstance(p, dict) else p) not in seen]; return seen
SRC_PRE = [{'s': 'BFF projections', 'u': ''}, {'s': 'Vegas lines and schedule (nflverse)', 'u': 'https://github.com/nflverse/nfldata'}, {'s': 'Official injury reports (nflverse) and ESPN', 'u': 'https://github.com/nflverse/nflverse-data'}]
SRC_POST = [{'s': 'ESPN box scores and scoring plays', 'u': 'https://www.espn.com/nfl/scoreboard'}, {'s': 'Official stats (nflverse)', 'u': 'https://github.com/nflverse/nflverse-data'}, {'s': 'BFF projections', 'u': ''}]


# ---------------------------------------------------------------- what happened in a game
def box_rows(g):
    """[(player, stat row, team)] for a game: the live box score, else the official weekly stats in the page data"""
    B = (LIVE.get('box') or {}).get(str(g.get('gid'))) if g.get('gid') else None
    rows = []
    BL = B.get('players') if isinstance(B, dict) else B if isinstance(B, list) else None
    if BL:
        for r in BL:
            p = NAMEIX.get((r.get('t'), normn(r.get('n'))))
            if p: rows.append((p, r, r.get('t')))
    if not rows:
        for p in P:
            wkr = next((x for x in p.get('wk') or [] if x[0] == g['wk']), None)
            gl = next((x for x in p.get('gl') or [] if x[0] == g['wk']), None)
            if not gl or not wkr: continue
            opp = wkr[6]
            if opp not in (g['home'], g['away']): continue
            tm = g['away'] if opp == g['home'] else g['home']
            rows.append((p, dict(pc=gl[1], pa=gl[2], py=gl[3], ptd=gl[4], int=gl[5], ra=gl[6], ry=gl[7], rtd=gl[8], rec=gl[9], tg=gl[10], ty=gl[11], rectd=gl[12], fl=gl[13], snap=wkr[3]), tm))
    return rows
def scoring_plays(g):
    B = (LIVE.get('box') or {}).get(str(g.get('gid'))) if g.get('gid') else None
    return [x for x in (B or {}).get('sp') or [] if isinstance(x, list) and len(x) >= 7] if isinstance(B, dict) else []
class Game:
    """a finished game, read for the story"""
    def __init__(s, g):
        s.g = g; s.w = g['wk']; s.rows = box_rows(g); hs, as_ = g['hs'] or 0, g['as_'] or 0
        s.win, s.lose = (g['home'], g['away']) if hs > as_ else (g['away'], g['home']); s.tie = hs == as_
        s.ws, s.ls = max(hs, as_), min(hs, as_); s.margin = s.ws - s.ls; s.total = hs + as_
        fav, sp = fav_of(g); s.fav, s.sp = fav, sp
        s.upset = bool(fav and fav == s.lose and sp >= 3); s.covered = bool(fav and fav == s.win and s.margin > sp)
        s.ot = bool(g.get('ls') and max(len(g['ls'][0] or []), len(g['ls'][1] or [])) > 4)
        s.half = None
        if g.get('ls') and len(g['ls'][0] or []) >= 2 and len(g['ls'][1] or []) >= 2:
            a2, h2 = sum(g['ls'][0][:2]), sum(g['ls'][1][:2]); s.half = (a2, h2)
        s.comeback = None
        if s.half:
            lead_h = s.half[1] - s.half[0] if s.win == g['home'] else s.half[0] - s.half[1]
            if lead_h <= -7: s.comeback = -lead_h
        s.plays = scoring_plays(g)
        s.pts = sorted([(p, r, t, ppr(r)) for p, r, t in s.rows], key=lambda x: -x[3])
    def team_rows(s, tm): return [x for x in s.pts if x[2] == tm]
    def top(s): return s.pts[0] if s.pts else None


def lede_recap(G, key):
    g = G.g; W, L = tm_name(G.win), tm_name(G.lose); sc = f"{G.ws}-{G.ls}"; rw, rl = record(G.win, g['wk']), record(G.lose, g['wk'])
    if G.tie: return f"{tm_name(g['away'])} and {tm_name(g['home'])} played to a {sc} tie" + (" in overtime" if G.ot else '') + '.'
    ot = ' in overtime' if G.ot else ''
    if G.comeback: s = pick([f"The {W} erased a {G.comeback}-point halftime deficit and beat the {L} {sc}{ot}.", f"Down {G.comeback} at the half, the {W} came all the way back to beat the {L} {sc}{ot}."], key, 'cb')
    elif G.upset: s = pick([f"The {W} won outright as {fnum(G.sp)}-point underdogs, beating the {L} {sc}{ot}.", f"Underdogs by {fnum(G.sp)}, the {W} took down the {L} {sc}{ot}."], key, 'up')
    elif G.margin >= 17: s = pick([f"The {W} rolled past the {L}, {sc}.", f"It was never close: the {W} beat the {L} {sc}.", f"The {W} handled the {L} {sc}."], key, 'bl')
    elif G.margin <= 3: s = pick([f"The {W} survived the {L}, {sc}{ot}.", f"The {W} edged the {L} {sc}{ot} in a game that came down to the end.", f"The {W} held on to beat the {L} {sc}{ot}."], key, 'cl')
    else: s = pick([f"The {W} beat the {L} {sc}{ot}.", f"The {W} took care of the {L}, {sc}{ot}.", f"The {W} pulled away from the {L} for a {sc} win{ot}."], key, 'md')
    s += f" The {W} are {rw}; the {L} fall to {rl}."
    if g['ou']:
        diff = G.total - g['ou']
        if diff >= 10: s += f" The {G.total} combined points blew past the {fnum(g['ou'])}-point total, the kind of game fantasy managers dream about."
        elif diff <= -10: s += f" The {G.total} combined points came in well under the {fnum(g['ou'])}-point total, and fantasy scoring suffered for it."
    return s
def flow_paragraph(G, key):
    """how it unfolded, from ESPN's scoring plays (touchdowns, and the score that decided it)"""
    g = G.g; pl = G.plays
    if not pl:
        if G.half: return f"{The(g['away'])} led {G.half[0]}-{G.half[1]} at halftime." if G.half[0] > G.half[1] else (f"{The(g['home'])} led {G.half[1]}-{G.half[0]} at halftime." if G.half[1] > G.half[0] else f"It was tied {G.half[0]}-{G.half[1]} at halftime.")
        return ''
    out = []; first = pl[0]
    out.append(f"{The(first[2])} struck first in the {ordn(int(first[0] or 1))} quarter: {first[4].rstrip('.')}.")
    lead = None; changes = 0; decisive = None
    for x in pl:
        a, h = x[5] or 0, x[6] or 0; now = g['home'] if h > a else g['away'] if a > h else None
        if now and now != lead:
            if lead is not None: changes += 1
            lead = now; decisive = x
    tdl = [x for x in pl if (x[3] or '').upper() == 'TD' or 'touchdown' in (x[4] or '').lower()]
    if changes >= 2: out.append(f"The lead changed hands {numw(changes) if changes <= 10 else changes} times.")
    if decisive and decisive is not first:
        q = int(decisive[0] or 4)
        when = f"with {decisive[1]} left in the {ordn(q)} quarter" if decisive[1] and q <= 4 else ('in overtime' if q > 4 else '')
        out.append(f"The go-ahead score for good came {when}: {decisive[4].rstrip('.')}.")
    if len(tdl) >= 4 and changes < 2: out.append(f"In all there were {len(tdl)} touchdowns.")
    return ' '.join(out)


def player_note(p, r, pts, w, key):
    """one player's game in a sentence, with what BFF expected"""
    n = p['n']; pj = proj_then(p, w); prev = [x[1] for x in season_games(p, w)]
    if p['p'] == 'QB' and r.get('pa'):
        s = f"{n} completed {r.get('pc', 0)} of {r['pa']} passes for {yd(r.get('py', 0))}"
        bits = []
        if r.get('ptd'): bits.append(plural(r['ptd'], 'touchdown'))
        if r.get('int'): bits.append(plural(r['int'], 'interception'))
        s += (' with ' + andj(bits) if bits else '')
        run_ = ([f"{yd(r['ry'])} on the ground"] if (r.get('ry') or 0) >= 20 else []) + ([plural(r['rtd'], 'rushing score')] if r.get('rtd') else [])
        if run_: s += ', adding ' + andj(run_)
    elif p['p'] == 'RB' or (r.get('ra') or 0) >= 6:
        s = f"{n} ran {plural(r.get('ra', 0), 'time')} for {yd(r.get('ry', 0))}" + (f" and {plural(r['rtd'], 'touchdown')}" if r.get('rtd') else '')
        if r.get('rec'): s += f", plus {plural(r.get('rec', 0), 'catch', 'catches')} for {yd(r.get('ty', 0))}" + (" and a receiving score" if r.get('rectd') else '')
    else:
        s = f"{n} caught {r.get('rec', 0)} of {plural(r.get('tg', 0), 'target')} for {yd(r.get('ty', 0))}" + (f" and {plural(r['rectd'], 'touchdown')}" if r.get('rectd') else '')
    s += f" ({f1(pts)} PPR points"
    if pj:
        d = pts - pj
        s += (f", {f1(d)} above our {f1(pj)} projection" if d >= 2.5 else f", {f1(-d)} below our {f1(pj)} projection" if d <= -2.5 else f", right around our {f1(pj)} projection") + ')'
    else: s += ')'
    if len(prev) >= 2 and pts > max(prev) + .5 and pts >= 12: s += pick([', his best game of the season', ', a season high', ', easily his top game of the year'], key, n)
    return s + '.'


def team_breakdown(G, tm, key):
    """the fantasy story of one team in a game: quarterback, backfield, pass catchers"""
    R = G.team_rows(tm)
    if not R: return []
    out = []; w = G.w
    tg_tot = sum((r.get('tg') or 0) for _, r, _, _ in R) or 0; rb_car = sum((r.get('ra') or 0) for p, r, _, _ in R if p['p'] == 'RB') or 0
    qb = next((x for x in R if x[0]['p'] == 'QB' and (x[1].get('pa') or 0) >= 10), None)
    if qb: out.append(player_note(qb[0], qb[1], qb[3], w, key))
    rbs = sorted([x for x in R if x[0]['p'] == 'RB' and (x[1].get('ra') or 0) + (x[1].get('tg') or 0) >= 4], key=lambda x: -((x[1].get('ra') or 0) + (x[1].get('tg') or 0)))
    if rbs:
        p, r, _, pts = rbs[0]; s = player_note(p, r, pts, w, key)
        if rb_car >= 8 and r.get('ra'):
            sh = r['ra'] / rb_car
            s += ' ' + (pick([f"That was {round(sh * 100)}% of the backfield carries, a true workhorse share.", f"He handled {round(sh * 100)}% of the running back carries; that kind of volume holds up."], key, 'wh') if sh >= .7
                        else f"He split the work, taking {round(sh * 100)}% of the running back carries." if sh <= .55 else f"He took {round(sh * 100)}% of the running back carries.")
        out.append(s)
        if len(rbs) > 1 and (rbs[1][1].get('ra') or 0) + (rbs[1][1].get('tg') or 0) >= 7: out.append(player_note(rbs[1][0], rbs[1][1], rbs[1][3], w, key))
    rec = sorted([x for x in R if x[0]['p'] in ('WR', 'TE', 'RB') and (x[1].get('tg') or 0) >= 4 and x not in rbs[:2]], key=lambda x: -((x[1].get('tg') or 0) * 2 + x[3]))
    for i, (p, r, _, pts) in enumerate(rec[:3]):
        s = player_note(p, r, pts, w, key)
        if i == 0 and tg_tot >= 15 and r.get('tg'):
            sh = r['tg'] / tg_tot
            if sh >= .28: s += f" He drew {round(sh * 100)}% of the team's targets, the volume of a true number one."
        out.append(s)
    return out


def stock_lists(G_list, key):
    """stock up / down / waiver, from what happened and how it happened (volume says more than a touchdown)"""
    up, down, wav = [], [], []
    for G in G_list:
        for p, r, t, pts in G.pts:
            pj = proj_then(p, G.w) or 0; vol = (r.get('tg') or 0) + (r.get('ra') or 0); td = tds(r)
            td_heavy = td >= 1 and (pts - 6 * td) < pts * .5
            if pts - pj >= 7 and pts >= 14 and NOW > G.g['kick']:
                why = (f"{plural(r.get('tg', 0), 'target')} is real volume" if (r.get('tg') or 0) >= 8 else f"{r.get('ra', 0)} carries is a featured role" if (r.get('ra') or 0) >= 16
                       else 'a big arm day' if p['p'] == 'QB' and (r.get('py') or 0) >= 300 else 'the touchdowns did the heavy lifting, so temper expectations' if td_heavy else 'the role is growing')
                up.append((pts - pj, p, f"{p['n']} ({p['p']}, {t}): {f1(pts)} points" + (f" vs a {f1(pj)} projection" if pj >= 1 else " out of nowhere") + f"; {why}."))
            elif pj >= 9 and pj - pts >= 6:
                why = ((f"{plural(r.get('tg', 0), 'target')} but only {r.get('rec', 0)} for {yd(r.get('ty', 0))}" if (r.get('tg') or 0) >= 7 else f"only {plural(r.get('tg', 0), 'target')}") if p['p'] in ('WR', 'TE')
                       else (f"{r.get('ra', 0)} carries went for just {yd(r.get('ry', 0))}" if (r.get('ra') or 0) >= 14 else f"only {plural(r.get('ra', 0), 'carry', 'carries')}") if p['p'] == 'RB' else 'a rough day through the air')
                sn = low_snap(p, G.w)
                if p.get('inj') == 'IR' or 'for the season' in (p.get('injn') or ''): why += f"; he has since been {'placed on injured reserve' if p.get('inj') == 'IR' else 'ruled out for the season'}"
                elif sn is not None: why += f"; he played just {round(sn * 100)}% of the snaps, which often points to an injury, so watch this week's injury report"
                down.append((pj - pts, p, f"{p['n']} ({p['p']}, {t}): {f1(pts)} points on a {f1(pj)} projection, {why}."))
            if OWN(p) is not None and OWN(p) < 50 and (pts >= 12 or (r.get('tg') or 0) >= 7 or (r.get('ra') or 0) >= 13) and p['p'] != 'QB':
                wav.append((pts + vol, p, f"{p['n']} ({p['p']}, {t}, rostered in {OWN(p)}% of leagues): {f1(pts)} points on {andj([plural(r['tg'], 'target') if r.get('tg') else '', plural(r['ra'], 'carry', 'carries') if r.get('ra') else ''])}." + (" The volume is worth chasing." if vol >= 10 else " One week is not a role, so check his snaps first.")))
    srt = lambda L: [x[2] for x in sorted(L, key=lambda x: -x[0])[:4]]
    return srt(up), srt(down), srt(wav), [x[1] for x in up + down + wav]


def looking_ahead(G_list, key):
    out = []
    for G in G_list:
        for tm in (G.win, G.lose):
            nx = next_game(tm, G.w)
            if not nx: continue
            w2, opp, home = nx; top = team_players(tm, w2, 1)
            if top:
                p = top[0]; mw = matchup_words(opp, p['p'])
                out.append(f"{The(tm)} {'host' if home else 'visit'} the {tm_name(opp)} in week {w2}; {p['n']} projects for {f1(proj_wk(p, w2))} points" + vs(mw) + '.')
    return out[:4]


def recap_title(G_list, label, key):
    if len(G_list) == 1:
        G = G_list[0]; W, L = tm_name(G.win), tm_name(G.lose); top = G.top(); sc = f"{G.ws}-{G.ls}"
        verb = 'rally past' if G.comeback else 'stun' if G.upset else 'roll past' if G.margin >= 17 else 'hold off' if G.margin <= 3 else 'beat'
        hook = f"{top[0]['n']} leads the fantasy winners" if top else 'the fantasy fallout'
        return pick([f"{W} {verb} {L} {sc}: {hook}", f"{label} recap: {W} {verb} {L}, and what it means for fantasy", f"{W} {G.ws}, {L} {G.ls}: winners, losers and waiver adds"], key, 't')
    tops = sorted([G.top() for G in G_list if G.top()], key=lambda x: -x[3])
    return pick([f"{label} recap: {tops[0][0]['n']} leads the way" if tops else f"{label} recap", f"{label} recap: winners, surprises and waiver adds", f"Everything that mattered from {label.lower() if not label.startswith('Week') else label}"], key, 't')


def write_recap(gs, key, label):
    """an in-depth recap of one game, or a few (Thursday, Sunday night, Monday, other days)"""
    G_list = [Game(g) for g in gs]; G_list = [G for G in G_list if G.rows]
    if not G_list: return None, None
    body = []; ment = []
    multi = len(G_list) > 1
    if multi: body.append(SCORES([G.g for G in G_list]))
    for G in G_list:
        if multi: body.append(H_(f"{tm_name(G.win)} {G.ws}, {tm_name(G.lose)} {G.ls}" if not G.tie else f"{tm_name(G.g['away'])} {G.g['as_']}, {tm_name(G.g['home'])} {G.g['hs']}"))
        else: body.append(SCORE(G.g))
        body.append(P_(lede_recap(G, key)))
        fl = flow_paragraph(G, key)
        if fl and not multi: body.append(H_('How it happened'))
        if fl: body.append(P_(fl))
        top = G.top()
        if top and not multi: body.append(PULL(f"{top[0]['n']}: {f1(top[3])} PPR points"))
        for tm in (G.win, G.lose):
            notes = team_breakdown(G, tm, key)
            if notes: body.append(H_(f"Fantasy breakdown: {tm_name(tm)}")); body.append(P_(' '.join(notes)))
            ment += [x[0] for x in G.team_rows(tm)[:5]]
    up, down, wav, sm = stock_lists(G_list, key)
    if up: body.append(H_('Stock up')); body.append(UL(up))
    if down: body.append(H_('Stock down')); body.append(UL(down))
    if wav: body.append(H_('Waiver wire')); body.append(UL(wav))
    la = looking_ahead(G_list, key)
    if la: body.append(H_('Looking ahead')); body.append(P_(' '.join(la)))
    ment += sm
    tops = sorted([G.top() for G in G_list if G.top()], key=lambda x: -x[3])
    dek = (f"{tops[0][0]['n']} put up {f1(tops[0][3])} PPR points. " if tops else '') + "How it happened, every fantasy-relevant line, who's rising, who's falling and who to grab off waivers."
    one = G_list[0]
    img = {'k': 'game', 'away': one.g['away'], 'home': one.g['home'], 'gid': one.g.get('gid')} if not multi else ({'k': 'player', 'pid': tops[0][0]['id']} if tops else None)
    return dict(kind='recap', src=SRC_POST, title=recap_title(G_list, label, key), dek=dek, body=body, players=uniq(ment), teams=sorted({t for G in G_list for t in (G.g['home'], G.g['away'])}), wk=one.w, img=img), None


def write_window_recap(gs, key, label, still):
    """a slate of games (Sunday afternoon): scores, top performances, game by game, stock, injuries, waivers, what is left"""
    G_list = [Game(g) for g in gs]; G_list = [G for G in G_list if G.rows]
    if not G_list: return None, None
    w = G_list[0].w; body = [SCORES([G.g for G in G_list])]; ment = []
    allp = sorted([x + (G,) for G in G_list for x in G.pts], key=lambda x: -x[3])
    ups = [G for G in G_list if G.upset]; hi = max(G_list, key=lambda G: G.total); cb = [G for G in G_list if G.comeback]
    intro = f"{cap(numw(len(G_list)) if len(G_list) <= 10 else str(len(G_list)))} games are in the books."
    if ups: intro += f" The biggest surprise: the {tm_name(ups[0].win)} beat the {tm_name(ups[0].lose)} as {fnum(ups[0].sp)}-point underdogs."
    if cb: intro += f" The {tm_name(cb[0].win)} came back from {cb[0].comeback} down at the half."
    intro += f" The {tm_name(hi.g['away'])}-{tm_name(hi.g['home'])} game was the highest-scoring at {hi.total} points."
    if allp: intro += f" {allp[0][0]['n']} led every fantasy scorer with {f1(allp[0][3])} PPR points."
    body.append(P_(intro))
    body.append(H_('The top performances'))
    body.append(UL([player_note(p, r, pts, w, key) for p, r, t, pts, G in allp[:6]]))
    ment += [x[0] for x in allp[:6]]
    body.append(H_('Game by game'))
    for G in sorted(G_list, key=lambda G: G.g['kick']):
        tps = G.pts[:2]
        cap_ = lede_recap(G, key) + ' ' + ' '.join(f"{p['n']} posted {f1(pts)} points" + (f" on {plural(r['tg'], 'target')}" if (r.get('tg') or 0) >= 6 else f" on {plural(r['ra'], 'carry', 'carries')}" if (r.get('ra') or 0) >= 12 else '') + '.' for p, r, t, pts in tps)
        body.append(GH(G.g)); body.append(P_(cap_)); ment += [x[0] for x in tps]
    up, down, wav, sm = stock_lists(G_list, key); ment += sm
    if up: body.append(H_('Stock up')); body.append(UL(up))
    if down: body.append(H_('Stock down')); body.append(UL(down))
    teams = {t for G in G_list for t in (G.g['home'], G.g['away'])}; start = min(G.g['kick'] for G in G_list)
    inj = []
    for h in NEWS.get('items') or []:
        d = pdt(h.get('d'))
        if not d or d < start or h.get('c') != 'inj': continue
        ps = [PI[i] for i in h.get('p') or [] if i in PI and PI[i]['t'] in teams]
        if ps: inj.append(f"{h.get('h')} ({h.get('s') or 'news'})"); ment += ps
    if inj: body.append(H_('Injuries to watch')); body.append(UL(inj[:5]))
    if wav: body.append(H_('Early waiver look')); body.append(UL(wav))
    if still: body.append(H_('Still to come')); body.append(P_(' '.join(f"{tm_name(g['away'])} at {tm_name(g['home'])}, {gdaytime(g)}" + (f" ({vegas(g)})" if vegas(g) else '') + '.' for g in still)))
    title = pick([f"{label} recap: {allp[0][0]['n']} leads a {len(G_list)}-game afternoon" if allp else f"{label} recap",
                  f"{label} recap: the performances, surprises and waiver adds that matter", f"{label}: what we learned from {numw(len(G_list)) if len(G_list) <= 10 else len(G_list)} games"], key, 't')
    dek = "Every score, the best fantasy days, who's rising and falling, injuries to watch and the first waiver targets of the week."
    return dict(kind='recap', src=SRC_POST, title=title, dek=dek, body=body, players=uniq(ment), teams=sorted(teams), wk=w, img={'k': 'player', 'pid': allp[0][0]['id']} if allp else None), None


# ---------------------------------------------------------------- outlooks
def start_sit(gs, w):
    teams = {t for g in gs for t in (g['home'], g['away'])}; starts = []; sits = []
    for p in P:
        if p['t'] not in teams or proj_wk(p, w) <= 0: continue
        wr, ur = wk_rank(p, w), usual_rank(p)
        if not wr or not ur: continue
        cut = {'QB': 12, 'RB': 24, 'WR': 30, 'TE': 12}[p['p']]
        if wr <= cut and ur > cut + 4: starts.append((ur - wr, p, wr, ur))
        if ur <= cut and wr > cut + 4 and p.get('inj') not in ('Out', 'IR'): sits.append((wr - ur, p, wr, ur))
    starts.sort(key=lambda x: -x[0]); sits.sort(key=lambda x: -x[0])
    return starts[:3], sits[:3]
def team_outlook(g, tm, key, deep=True):
    """one offense's fantasy outlook for a game"""
    w = g['wk']; opp = g['away'] if tm == g['home'] else g['home']; it = g['ih'] if tm == g['home'] else g['ia']; out = []
    qb = qb_of(tm)
    if qb and proj_wk(qb, w) > 0:
        r = wk_rank(qb, w); mw = matchup_words(opp, 'QB')
        out.append(f"{qb['n']} projects for {f1(proj_wk(qb, w))} points" + (f", QB{r} this week" if r else '') + vs(mw) + '.')
    elif qb is None or proj_wk(qb, w) <= 0:
        q2 = next((q for q in P if q['t'] == tm and q['p'] == 'QB' and q.get('qbs')), None)
        if q2: out.append(f"{q2['n']} is expected to start at quarterback.")
    rbs = team_players(tm, w, 2, ('RB',))
    if rbs:
        p = rbs[0]; cs = p.get('cs'); mw = matchup_words(opp, 'RB')
        s = f"{p['n']} leads the backfield" + (f" with {round(cs * 100)}% of the carries this season" if cs else '') + f" and projects for {f1(proj_wk(p, w))}" + vs(mw) + '.'
        if len(rbs) > 1 and proj_wk(rbs[1], w) >= 7: s += f" {rbs[1]['n']} ({f1(proj_wk(rbs[1], w))}) is involved enough to flex in deeper leagues."
        out.append(s)
    rec = team_players(tm, w, 3, ('WR', 'TE'))
    if rec:
        p = rec[0]; ts = p.get('ts'); mw = matchup_words(opp, p['p'])
        s = f"{p['n']} is the top target" + (f", drawing {round(ts * 100)}% of the targets" if ts else '') + f"; he projects for {f1(proj_wk(p, w))}" + vs(mw) + '.'
        if len(rec) > 1: s += ' ' + andj([f"{q['n']} ({f1(proj_wk(q, w))})" for q in rec[1:]]) + ' round out the passing game.'
        out.append(s)
    if deep and it:
        tpl, tpr = pace(tm)
        if tpl and tpr: out.append(f"The {tm_name(tm)} run {f1(tpl)} plays a game and pass {round(tpr * 100)}% of the time; Vegas expects {f1(it)} points from them.")
    return ' '.join(out)
def injury_line(gs, w):
    L = injured({t for g in gs for t in (g['home'], g['away'])}, w)
    if not L: return ''
    return 'Injury report: ' + '; '.join(f"{p['n']} ({p['t']}, {inj_word(p)}{', ' + p['injd'].lower() if p.get('injd') else ''})" for p in L[:6]) + '.'
def prediction(g):
    if g['ih'] is None or g['ia'] is None: return ''
    h, a = round(g['ih']), round(g['ia'])
    if h == a: h += 1 if (g['sp'] or 0) <= 0 else 0; a += 1 if (g['sp'] or 0) > 0 else 0
    wp = win_prob(g, g['home'] if h > a else g['away'])
    wn = g['home'] if h > a else g['away']
    return f"{tm_name(wn)} {max(h, a)}, {tm_name(g['away'] if wn == g['home'] else g['home'])} {min(h, a)}" + (f" (a {round(wp * 100)}% win chance from the spread)" if wp else '')
def bets_lines(gs, w, n=3):
    out = []
    for x in picks_for({t for g in gs for t in (g['home'], g['away'])}, w)[:n]:
        p = PI[x['pid']]; pr = max(x['po'], 1 - x['po'])
        out.append(f"{p['n']} {'over' if x['po'] >= .5 else 'under'} {x['line']} {SNAME.get(x['k'], x['k'])}: BFF gives it {round(pr * 100)}% (we project {fnum(round(x['mm'], 1))}).")
    return out


def write_outlook(gs, key, label):
    """Thursday, Monday or any other day's game(s), in depth"""
    w = gs[0]['wk']; body = []; ment = []
    g0 = gs[0]
    for g in gs:
        body.append(GH(g))
        ra, rh = record(g['away'], w - 1), record(g['home'], w - 1)
        lede = pick([f"The {tm_name(g['away'])} ({ra}) visit the {tm_name(g['home'])} ({rh}) {gdaytime(g)}.", f"{tm_name(g['away'])} ({ra}) at {tm_name(g['home'])} ({rh}) kicks off {gdaytime(g)}."], key, g['home'])
        if vegas(g): lede += f" Vegas has {vegas(g)}, which implies about {fnum(round(g['ia'] or 0))} points for {the(g['away'])} and {fnum(round(g['ih'] or 0))} for {the(g['home'])}." if g['ia'] and g['ih'] else f" Vegas has {vegas(g)}."
        ra_, rh_ = result_words(g['away'], w), result_words(g['home'], w)
        if ra_ and rh_: lede += f" The {tm_name(g['home'])} {rh_}; the {tm_name(g['away'])} {ra_}."
        hh = hot_hand({g['home'], g['away']}, w)
        if hh: lede += f" {hh[0]['n']} comes in hot after a {f1(hh[1])}-point game."
        if g['ou'] and g['ou'] >= 50: lede += ' That total is one of the week\'s highest, so this is a game to target.'
        elif g['ou'] and g['ou'] <= 40: lede += ' That low total caps the ceiling for everyone involved.'
        body.append(P_(lede))
        body.append(H_(f"{tm_name(g['away'])} outlook")); body.append(P_(team_outlook(g, g['away'], key)))
        body.append(H_(f"{tm_name(g['home'])} outlook")); body.append(P_(team_outlook(g, g['home'], key)))
        il = injury_line([g], w)
        if il: body.append(P_(il))
        ment += team_players(g['away'], w, 5) + team_players(g['home'], w, 5)
    st, sit = start_sit(gs, w)
    if st or sit:
        body.append(H_("Start 'em, sit 'em"))
        body.append(UL([f"Start {p['n']} ({p['p']}, {p['t']}): ranks {p['p']}{wr} this week, well above his usual {p['p']}{ur}." for _, p, wr, ur in st]
                       + [f"Sit {p['n']} ({p['p']}, {p['t']}): only {p['p']}{wr} this week after ranking {p['p']}{ur} most weeks." for _, p, wr, ur in sit]))
        ment += [x[1] for x in st + sit]
    bl = bets_lines(gs, w)
    if bl: body.append(H_('Best bets')); body.append(UL(bl + ['For entertainment, 21+ where legal.']))
    preds = [prediction(g) for g in gs if prediction(g)]
    if preds: body.append(H_("BFF's pick")); body.append(P_(' '.join(f"{x}." for x in preds) + " The score comes from Vegas' implied points; the fantasy calls above are ours, and this outlook updates until kickoff."))
    night = ghour(g0) >= 19 and len(gs) == 1
    day = DOW[gday(g0).weekday()]
    show = {'Thursday': 'Thursday Night Football', 'Monday': 'Monday Night Football', 'Sunday': 'Sunday Night Football'}.get(day) if night else None
    if len(gs) == 1:
        title = pick([f"{show or label + ' outlook'}: {tm_name(g0['away'])} at {tm_name(g0['home'])}, the fantasy breakdown", f"{tm_name(g0['away'])} at {tm_name(g0['home'])}: {label} outlook, start/sit and best bets",
                      f"{label} outlook: what to expect from {tm_name(g0['away'])} at {tm_name(g0['home'])}"], key, 't')
    else: title = f"{label} outlook: all {numw(len(gs))} games, start/sit and best bets"
    dek = f"The matchup, both offenses' fantasy outlook, injuries, start/sit calls, best bets and our pick for {'the game' if len(gs) == 1 else 'every game'}. Updates until kickoff."
    return dict(kind='outlook', src=SRC_PRE, title=title, dek=dek, body=body, players=uniq(ment), teams=sorted({t for g in gs for t in (g['home'], g['away'])}), wk=w,
                img={'k': 'game', 'away': g0['away'], 'home': g0['home'], 'gid': g0.get('gid')}), facts_digest([PI[i] for i in uniq(ment)], gs)


def capsule(g, key):
    """a few sentences on one game: the line, the best play, one more angle, who is out"""
    w = g['wk']; s = f"Kickoff is {gtime(g)}" + (f", and Vegas has {vegas(g)}" if vegas(g) else '') + '.'
    tops = sorted(team_players(g['away'], w, 4) + team_players(g['home'], w, 4), key=lambda p: -proj_wk(p, w))
    if tops:
        p = tops[0]; opp = g['home'] if p['t'] == g['away'] else g['away']; mw = matchup_words(opp, p['p'])
        s += ' ' + pick([f"{p['n']} is the top play here at {f1(proj_wk(p, w))} projected points", f"The headliner is {p['n']}, projected for {f1(proj_wk(p, w))}"], key, g['home']) + vs(mw) + '.'
    angle = None
    for p in tops[1:]:
        wr, ur = wk_rank(p, w), usual_rank(p)
        if wr and ur and wr + 8 <= ur: angle = f"{p['n']} ({p['p']}{wr} this week, usually {p['p']}{ur}) is a sneaky start."; break
    if not angle:
        x = (picks_for({g['home'], g['away']}, w) or [None])[0]
        if x: angle = f"Our favorite prop: {PI[x['pid']]['n']} {'over' if x['po'] >= .5 else 'under'} {x['line']} {SNAME.get(x['k'], x['k'])} ({round(max(x['po'], 1 - x['po']) * 100)}%)."
    if angle: s += ' ' + angle
    outs = injured({g['home'], g['away']}, w, ('Out', 'Doubtful'))
    if outs: s += ' ' + dot(f"Out: {andj([p['n'] for p in outs[:3]])}")
    q = injured({g['home'], g['away']}, w, ('Questionable',))
    if q: s += ' ' + dot(f"Questionable: {andj([p['n'] for p in q[:3]])}")
    return s, tops[:3]


def write_sunday_outlook(gs, key):
    """the Saturday-morning look at every Sunday game"""
    w = gs[0]['wk']; body = []; ment = []
    wl = [g for g in gs if g['ou'] is not None]
    hi = max(wl, key=lambda g: g['ou']) if wl else None; lo = min(wl, key=lambda g: g['ou']) if wl else None
    its = sorted([(g['ih'], g['home'], g) for g in gs if g['ih']] + [(g['ia'], g['away'], g) for g in gs if g['ia']], key=lambda x: -x[0])
    byes = sorted({t for t in (D.get('sched') or {}) if not any(x[0] == w and x[1] for x in D['sched'][t])})
    outs = injured({t for g in gs for t in (g['home'], g['away'])}, w, ('Out', 'IR', 'Doubtful'))
    intro = pick([f"Sunday brings {plural(len(gs), 'game')}, from the early window through the night game.", f"Week {w}'s Sunday slate has {plural(len(gs), 'game')}, and plenty of lineup decisions."], key, 'i')
    if hi: intro += f" {tm_name(hi['away'])} at {tm_name(hi['home'])} carries the highest total ({fnum(hi['ou'])})"
    if its: intro += f", and {the(its[0][1])} have the biggest implied team total at {f1(its[0][0])} points." if hi else f" {The(its[0][1])} have the biggest implied team total at {f1(its[0][0])} points."
    elif hi: intro += '.'
    if byes: intro += f" On bye: {andj([tm_name(t) for t in byes])}."
    body.append(P_(intro))
    things = []
    if outs: things.append(f"Key absences: {andj([p['n'] + ' (' + p['t'] + ')' for p in outs[:5]])}. Every projection below already accounts for them.")
    if lo and hi and lo is not hi: things.append(f"Lowest total: {tm_name(lo['away'])} at {tm_name(lo['home'])} ({fnum(lo['ou'])}). Lower your expectations for everyone in that one.")
    if its and len(its) > 1: things.append(f"Best offensive environments: {andj([f'{tm_name(t)} ({f1(v)})' for v, t, _ in its[:3]])}.")
    st, sit = start_sit(gs, w)
    if things: body.append(H_('Things to know')); body.append(UL(things))
    if st or sit:
        body.append(H_("Start 'em, sit 'em"))
        body.append(UL([f"Start {p['n']} ({p['p']}, {p['t']}): {p['p']}{wr} this week, well above his usual {p['p']}{ur}." for _, p, wr, ur in st]
                       + [f"Sit {p['n']} ({p['p']}, {p['t']}{', ' + inj_word(p) if p.get('inj') else ''}): only {p['p']}{wr} this week after ranking {p['p']}{ur} most weeks." for _, p, wr, ur in sit]))
        ment += [x[1] for x in st + sit]
    body.append(H_('Game by game'))
    for g in gs:
        body.append(GH(g)); s, tp = capsule(g, key); body.append(P_(s)); ment += tp
    bl = bets_lines(gs, w, 4)
    if bl: body.append(H_('Best bets of the day')); body.append(UL(bl + ['For entertainment, 21+ where legal.']))
    title = pick([f"Week {w} Sunday outlook: {hi['away']}-{hi['home']} headlines a {len(gs)}-game slate" if hi else f"Week {w} Sunday outlook",
                  f"Week {w} Sunday outlook: every game's fantasy angle", f"Sunday, week {w}: who to start, who to sit, what Vegas expects"], key, 't')
    dek = f"Things to know, start/sit calls, every game's fantasy outlook and the best bets for all {len(gs)} Sunday games. Updates until kickoff."
    return dict(kind='slate', src=SRC_PRE, title=title, dek=dek, body=body, players=uniq(ment), teams=sorted({t for g in gs for t in (g['home'], g['away'])}), wk=w,
                img={'k': 'game', 'away': hi['away'], 'home': hi['home'], 'gid': hi.get('gid')} if hi else None), facts_digest([PI[i] for i in uniq(ment)], gs)


# ---------------------------------------------------------------- the week: Friday injury report, Tuesday landscape
def benefactors(p, n=2):
    L = [q for q in P if q['t'] == p['t'] and q['id'] != p['id'] and q['p'] == p['p'] and proj_wk(q, p.get('nw') or 0) > 0]
    return sorted(L, key=lambda q: -proj_wk(q, p.get('nw') or 0))[:n]
def write_injury_report(w, gs, key):
    teams = {t for g in gs for t in (g['home'], g['away'])}
    outs = injured(teams, w, ('Out', 'Doubtful')); irs = [p for p in injured(teams, w, ('IR',)) if (p.get('rl') or 0) >= 10]
    qs = injured(teams, w, ('Questionable',))
    if not outs and not qs and not irs: return None, None
    body = []; ment = []
    late = [g for g in gs if ghour(g) >= 16 or DOW[gday(g).weekday()] != 'Sunday']
    body.append(P_(f"Friday's reports are in for week {w}: {plural(len(outs), 'notable player')} {'is' if len(outs) == 1 else 'are'} out or doubtful and {len(qs)} more {'is' if len(qs) == 1 else 'are'} questionable."
                   + " Here is who is affected, who benefits, and how to plan around the game-time decisions."))
    if outs:
        body.append(H_('Ruled out or doubtful'))
        L = []
        for p in outs[:10]:
            b = benefactors(p); ment += [p] + b
            L.append(f"{p['n']} ({p['p']}, {p['t']}, {inj_word(p)}{', ' + p['injd'].lower() if p.get('injd') else ''})" + (f": {andj([f'{q[chr(110)]} ({f1(proj_wk(q, w))} projected)' if i == 0 else q['n'] for i, q in enumerate(b)])} {'move' if len(b) > 1 else 'moves'} up" if b else '') + '.')
        body.append(UL(L))
    if irs: body.append(P_(dot(f"Still on injured reserve: {andj([p['n'] + ' (' + p['t'] + ')' for p in irs[:8]])}")))
    if qs:
        body.append(H_('Questionable: the game-time decisions'))
        L = []
        for p in qs[:10]:
            g = next((g for g in gs if p['t'] in (g['home'], g['away'])), None); ment.append(p)
            L.append(f"{p['n']} ({p['p']}, {p['t']}{', ' + p['injd'].lower() if p.get('injd') else ''})" + (f", {gdaytime(g)}" if g else '') + (f". {p['injn']}" if p.get('injn') else '') + '.')
        body.append(UL(L))
        body.append(P_("Questionable players played 61% of the time in 2021-2025. For the 4 PM and night games you cannot wait for the news and still pick a replacement from the early games, so keep a pivot from the same window or later on your bench, and check the inactive list 90 minutes before kickoff."
                       if late else "Questionable players played 61% of the time in 2021-2025. Check the inactive list 90 minutes before kickoff."))
    qbx = [(t, qb_of(t)) for t in sorted(teams)]
    qbx = [(t, q) for t, q in qbx if q and q.get('role') not in (None, 'QB1')]
    if qbx:
        body.append(H_('Quarterback situations'))
        body.append(UL([f"{tm_name(t)}: {q['n']} is expected to start ({f1(proj_wk(q, w))} projected)." for t, q in qbx])); ment += [q for _, q in qbx]
    top = (outs or qs or irs)[0]
    title = pick([f"Week {w} injury report: {top['n']} {'out' if top in outs else 'questionable'}, and everything else that matters", f"Week {w} injury report: who's out, who's a game-time decision"], key, 't')
    dek = "Every fantasy-relevant player ruled out, doubtful or questionable this week, who benefits, and the quarterback situations. Updates until Sunday."
    return dict(kind='injuries', src=SRC_PRE, title=title, dek=dek, body=body, players=uniq(ment), teams=sorted(teams), wk=w, img={'k': 'player', 'pid': top['id']}), facts_digest(ment, gs)


def usage_change(p, w):
    """expected points (usage) in his last 2 games vs his season before them"""
    L = [x for x in season_games(p, w + 1) if x[2] is not None]
    if len(L) < 4: return None
    last2 = sum(x[2] for x in L[-2:]) / 2; before = sum(x[2] for x in L[:-2]) / len(L[:-2])
    return last2 - before, last2, before
def write_landscape(w, key):
    """Tuesday: the fantasy landscape after the week"""
    rows = [(p, x) for p in P for x in (p.get('wk') or []) if x[0] == w and x[1] is not None]
    if len(rows) < 40: return None, None
    body = []; ment = []
    byp = {q: sorted([(p, x) for p, x in rows if p['p'] == q], key=lambda y: -y[1][1]) for q in ('QB', 'RB', 'WR', 'TE')}
    top_all = sorted(rows, key=lambda y: -y[1][1])
    intro = pick([f"Week {w} is in the books.", f"Another week down: here is where the fantasy landscape stands after week {w}."], key, 'i')
    if top_all: intro += f" {top_all[0][0]['n']} led everyone with {f1(top_all[0][1][1])} PPR points."
    body.append(P_(intro))
    body.append(H_(f"Week {w} MVPs"))
    body.append(UL([f"{q}: {byp[q][0][0]['n']} ({byp[q][0][0]['t']}), {f1(byp[q][0][1][1])} points" + (f" on {byp[q][0][1][4]} targets" if q in ('WR', 'TE') and byp[q][0][1][4] else f" on {byp[q][0][1][5]} carries" if q == 'RB' and byp[q][0][1][5] else '') + '.' for q in ('QB', 'RB', 'WR', 'TE') if byp[q]]))
    ment += [byp[q][0][0] for q in byp if byp[q]]
    ch = [(usage_change(p, w), p) for p in P if p['p'] != 'QB']
    ch = [(c, p) for c, p in ch if c]
    ris = sorted([x for x in ch if x[0][0] >= 3 and x[0][1] >= 8], key=lambda x: -x[0][0])[:5]
    # fallers are role changes: a player who just missed time hurt (or is out) is injury news, not a usage drop
    fal = sorted([x for x in ch if x[0][0] <= -3 and x[0][2] >= 8 and x[1].get('inj') not in ('IR', 'Out', 'Doubtful') and x[1].get('injs') != 'expected'], key=lambda x: x[0][0])[:5]
    if ris:
        body.append(H_('Risers'))
        body.append(UL([f"{p['n']} ({p['p']}, {p['t']}): " + pick([f"his usage was worth {f1(c[1])} expected points a game over the last two weeks, up from {f1(c[2])} before.",
                                                                       f"{f1(c[1])} expected points a game of usage the last two weeks, more than his {f1(c[2])} before that.",
                                                                       f"the opportunity jumped to {f1(c[1])} expected points a game, from {f1(c[2])}."], key, p['id'])
                        + ' ' + pick(['Usage like that tends to stick.', 'Volume is the stickiest stat in fantasy.', 'That is a role change, not a fluke.', 'Act before the rest of your league does.'], key, p['id'], 'b') for c, p in ris]))
        ment += [p for _, p in ris]
    if fal:
        body.append(H_('Fallers'))
        def fal_note(p):
            if p.get('inj') and p.get('injs') in ('ESPN', 'report'): return f" He is listed {p['inj'].lower()}."
            if 'for the season' in (p.get('injn') or ''): return ' He has since been ruled out for the season.'
            sn = low_snap(p, w)   # a starter who barely played his last game usually got hurt in it: say so, don't call it a role change
            if sn is not None:
                return f" He played just {round(sn * 100)}% of the snaps in week {w}, which often points to an injury, so check Wednesday's injury report before reading it as a role change."
            return ' Watch his snap share this week.'
        body.append(UL([f"{p['n']} ({p['p']}, {p['t']}): down to {f1(c[1])} expected points a game over the last two weeks from {f1(c[2])}." + fal_note(p) for c, p in fal]))
        ment += [p for _, p in fal]
    inj = [p for p in P if p.get('inj') in ('Out', 'IR', 'Doubtful') and ((p.get('rl') or 0) >= 10 or (p.get('ecr') or 999) <= 100)]
    if inj:
        body.append(H_('Injury fallout'))
        body.append(UL([f"{p['n']} ({p['p']}, {p['t']}, {inj_word(p)}{', ' + p['injd'].lower() if p.get('injd') else ''})" + (f": {andj([q['n'] for q in benefactors(p)])} {'stands' if len(benefactors(p)) == 1 else 'stand'} to gain." if benefactors(p) else '.') for p in sorted(inj, key=lambda p: -(p.get('rl') or 0))[:6]]))
        ment += inj[:6]
    nw = w + 1
    pjn = lambda p: proj_wk(p, nw) or (float(p.get('rl') or 0) if not any(r[0] == nw for r in p.get('ros') or []) and p.get('nw') != nw else 0.0)
    wav = [p for p in P if OWN(p) is not None and OWN(p) < 45 and p['p'] != 'QB' and pjn(p) >= 7 and p.get('inj') not in ('Out', 'IR')]
    wav = sorted(wav, key=lambda p: -(pjn(p) + 2 * ((usage_change(p, w) or (0,))[0])))[:6]
    if wav:
        body.append(H_('Waiver wire priorities'))
        body.append(UL([f"{p['n']} ({p['p']}, {p['t']}, rostered in {OWN(p)}% of leagues): projects for {f1(pjn(p))} a game going forward" + (", and his usage is climbing" if (usage_change(p, w) or (0,))[0] >= 2 else '') + '.' for p in wav]))
        ment += wav
    bl = [p for p in P if p['p'] != 'QB' and (p.get('g') or 0) >= 3 and p.get('xfpg') and p.get('fpg') is not None and p['xfpg'] >= 9 and p['xfpg'] - p['fpg'] >= 2.5 and p.get('inj') not in ('Out', 'IR')]
    sh = [p for p in P if p['p'] != 'QB' and (p.get('g') or 0) >= 3 and p.get('xfpg') and p.get('fpg') is not None and p['fpg'] >= 11 and p['fpg'] - p['xfpg'] >= 3]
    if bl or sh:
        body.append(H_('Buy low, sell high'))
        body.append(UL([f"Buy low: {p['n']} ({p['t']}) is scoring {f1(p['fpg'])} a game on usage worth {f1(p['xfpg'])}." for p in sorted(bl, key=lambda p: -(p['xfpg'] - p['fpg']))[:3]]
                       + [f"Sell high: {p['n']} ({p['t']}) is scoring {f1(p['fpg'])} a game on usage worth only {f1(p['xfpg'])}." for p in sorted(sh, key=lambda p: -(p['fpg'] - p['xfpg']))[:3]]))
        ment += bl[:3] + sh[:3]
    nx = [g for g in GAMES if g['wk'] == nw]
    if nx:
        byes = sorted({t for t in (D.get('sched') or {}) if not any(x[0] == nw and x[1] for x in D['sched'][t])})
        its = sorted([(g['ih'], g['home']) for g in nx if g['ih']] + [(g['ia'], g['away']) for g in nx if g['ia']], key=lambda x: -x[0])
        s = f"Week {nw} has {plural(len(nx), 'game')}."
        if byes: s += f" On bye: {andj([tm_name(t) for t in byes])}, so plan around those players now."
        if its: s += f" The best offensive environments by Vegas: {andj([f'{tm_name(t)} ({f1(v)})' for v, t in its[:3]])}."
        body.append(H_(f"Looking ahead to week {nw}")); body.append(P_(s))
    C = ((D.get('calls') or {}).get('weeks') or {}).get(str(w)) or {}
    gr = lambda k: [e for e in C.get(k) or [] if e.get('res') in ('hit', 'miss')]
    if gr('start') or gr('sit'):
        a, b = gr('start'), gr('sit')
        body.append(H_("BFF's calls scorecard"))
        body.append(P_(f"Our week {w} must starts finished as starters {sum(e['res'] == 'hit' for e in a)} of {len(a)} times" + (f", and our must sits finished outside the starter spots {sum(e['res'] == 'hit' for e in b)} of {len(b)} times." if b else '.')
                       + " Every call is graded with official stats in Fantasy Help, Weekly calls."))
    lead = (ris[0][1] if ris else top_all[0][0] if top_all else None)
    title = pick([f"Week {w} fantasy landscape: {poss(lead['n'])} rise, waiver priorities and what changed" if lead else f"Week {w} fantasy landscape",
                  f"After week {w}: risers, fallers and the waiver wire", f"The fantasy landscape after week {w}: who's up, who's down, who to add"], key, 't')
    dek = f"Week {w}'s MVPs, the risers and fallers by usage, injury fallout, waiver priorities, buy-low and sell-high targets and a look at week {nw}."
    return dict(kind='landscape', src=[{'s': 'Official stats and usage (nflverse)', 'u': 'https://github.com/nflverse/nflverse-data'}, {'s': 'BFF projections and weekly calls', 'u': ''}],
                title=title, dek=dek, body=body, players=uniq(ment), teams=[], wk=w, img={'k': 'player', 'pid': lead['id']} if lead else None), None


# ---------------------------------------------------------------- breaking news
BV = 2   # version of the breaking-news keys (2: injury news keyed by week, activations apart from placements)
def teammates(p, n=3):
    L = [q for q in P if q['t'] == p['t'] and q['id'] != p['id'] and q['p'] == p['p'] and (q.get('rl') or 0) > 0]
    return sorted(L, key=lambda q: -(q.get('rl') or 0))[:n]
def write_breaking(p, ev, key):
    w = p.get('nw') or D['asof']['next_week']; kind = ev['kind']; n = p['n']; ln = last(n)
    if kind == 'out' and 'for the season' in (p.get('injn') or ''): kind = 'season'   # BFF already has him out for the season
    what = {'season': f"{n} is out for the rest of the season", 'ir': f"{n} has been placed on injured reserve", 'out': f"{n} has been ruled out for week {w}", 'doubtful': f"{n} is doubtful for week {w}",
            'traded': f"{n} has been traded", 'released': f"{n} has been released", 'activated': f"{n} has been activated from injured reserve"}[kind]
    title = pick({'season': [f"{n} out for the season: the fantasy fallout", f"Season over for {n}: who steps up", f"Fantasy fallout: {n} is done for the season"],
                  'ir': [f"{n} to injured reserve: what it means for fantasy", f"{n} lands on IR. Here is the fantasy fallout", f"Fantasy fallout: {n} heads to injured reserve"],
                  'out': [f"{n} ruled out for week {w}: who to start instead", f"Fantasy fallout: {n} is out this week", f"{n} out for week {w}. Here is what to do"],
                  'doubtful': [f"{n} doubtful for week {w}: pivot now", f"{n} is doubtful. Here is your backup plan"],
                  'traded': [f"{n} traded: what it means for fantasy", f"Fantasy fallout from the {n} trade"],
                  'released': [f"{n} released: the fantasy fallout", f"{n} cut: who benefits"],
                  'activated': [f"{n} back from injured reserve: the fantasy outlook", f"{n} activated off IR: start him or wait?"]}[kind], key)
    body = [P_(f"{what}{(' (' + ev['why'] + ')') if ev.get('why') else ''}." + (f" It was first reported by {ev['src']}." if ev.get('src') else ''))]
    ur = usual_rank(p); g_ = p.get('g') or 0
    s = f"{ln} has averaged {f1(p.get('fpg') or 0)} PPR points over {plural(g_, 'game')} this season" if g_ else f"{ln} has not played this season"
    if ur and ur <= 60: s += f" and ranks as a {p['p']}{ur} in BFF's per-game rest-of-season projection when healthy"
    s += '.'
    if kind == 'ir' and p.get('ret'):
        rep = f"; he was {p['injn'][0].lower() + p['injn'][1:]}" if p.get('injs') == 'news' and p.get('injn') else ''
        s += (f" Players on injured reserve must miss at least four games{rep}. BFF expects him back around week {p['ret']} at the earliest, and those returns often slip."
              if p['ret'] <= 18 else f" Players on injured reserve must miss at least four games{rep}, and BFF doesn't expect him back this season.")
    body.append(P_(s))
    tm = teammates(p)
    if kind == 'activated':
        pw_ = proj_wk(p, w)
        body.append(H_('His outlook'))
        body.append(P_(f"BFF projects {ln} for {f1(pw_)} PPR points in week {w}" + (f", which makes him a {p['p']}{wk_rank(p, w)} for the week" if pw_ > 0 and wk_rank(p, w) else '') + ". First games back from injured reserve can come with a snap count, so the projection leans conservative." if pw_ > 0 else f"BFF does not project {ln} to play in week {w} yet; his projection returns once he is expected to suit up."))
        if tm:
            body.append(H_('Whose role shrinks'))
            body.append(UL([f"{q['n']} ({q.get('role') or q['p'] + ' depth'}) projects for {f1(proj_wk(q, w))} in week {w}." for q in tm if proj_wk(q, w) > 0] or [f"No {tm_name(p['t'])} {p['p']} projects for meaningful points behind {ln}."]))
        body.append(H_('What to do'))
        body.append(UL([f"Move {ln} out of your IR slot and back into your lineup plans" + (f"; at {f1(pw_)} projected points he is worth starting over most bench options." if pw_ >= 10 else "; give him a week to show his workload if you have a steadier option."),
                        "BFF's projections, rankings and trade values already reflect this, or will after the next data update (every 3 hours)."]))
        dek = f"{what}. His outlook for week {w}, whose role shrinks on the {tm_name(p['t'])}, and what to do with your lineup."
        return dict(kind='breaking', title=title, dek=dek, body=body, players=uniq([p] + tm), teams=[p['t']], wk=w, img={'k': 'player', 'pid': p['id']}, src=[{'s': 'BFF projections and depth charts (nflverse)', 'u': ''}]), None
    if p['p'] == 'QB': tm = [q for q in tm if proj_wk(q, w) > 0 or q.get('qbs')][:1] or tm[:1]
    body.append(H_('Who benefits'))
    if tm:
        L = []
        for q in tm:
            cl = ([f"projects for {f1(proj_wk(q, w))} in week {w}"] if proj_wk(q, w) > 0 else []) + ([f"is rostered in {q['own']}% of leagues"] if q.get('own') is not None else [])
            L.append(f"{q['n']} ({q.get('role') or q['p'] + ' depth'})" + (' ' + andj(cl) if cl else '') + '.')
        if p['p'] == 'QB' and tm: L[0] = L[0].rstrip('.') + '; he is the expected starter.'
        body.append(UL(L))
        free = [q for q in tm if q.get('own') is not None and q['own'] < 50]
        body.append(P_(f"Waiver priority: {free[0]['n']} is the add if he is on your wire." if free else f"The {tm_name(p['t'])} depth behind {ln} is mostly rostered, so look for help elsewhere on waivers."))
    else:
        body.append(P_(f"The {tm_name(p['t'])} have no clear replacement at {p['p']} in BFF's data, so expect a committee."))
    if p['p'] in ('WR', 'TE'):
        qb = qb_of(p['t'])
        if qb: body.append(P_(f"For {qb['n']}, losing a top target lowers the ceiling; BFF's projections already shift those targets to the receivers still active."))
    body.append(H_('What to do'))
    body.append(UL([{'season': f"In redraft leagues {ln} can go to an IR slot if your league has one, or be dropped for a player who can help this year; in dynasty leagues, hold him for next season.",
                     'ir': f"Move {ln} to an IR slot if your league has one; do not drop him unless you need the roster spot for a starter.",
                     'out': f"Start someone else in week {w}; {ln} keeps his rest-of-season value.", 'doubtful': f"Plan to start someone else in week {w} and check the inactive list 90 minutes before kickoff.",
                     'traded': "Wait for his new role before moving him; trade values update after the next data run.", 'released': "He is droppable in most leagues until he signs somewhere."}[kind],
                    "BFF's projections, rankings and trade values already reflect this, or will after the next data update (every 3 hours)."]))
    dek = f"{what}. Who benefits on the {tm_name(p['t'])}, waiver moves and what to do with your lineup."
    src = ([{'s': ev['src'], 'u': ev['url']}] if ev.get('url') else []) + [{'s': 'BFF projections and depth charts (nflverse)', 'u': ''}]
    return dict(kind='breaking', title=title, dek=dek, body=body, players=uniq([p] + tm), teams=[p['t']], wk=w, img={'k': 'player', 'pid': p['id']}, src=src), None


SEASON_RE = re.compile(r"\b(out for (the )?((rest|remainder) of (the )?)?(season|year)|season[- ]ending|(miss|misses|missing|sit out) (the )?((rest|remainder) of (the )?)?(season|year)(?!\s*(opener|finale|debut))|done for the (season|year))\b", re.I)
DIAG_RE = re.compile(r"\b(with|after|due to|suffers|suffered|has) (an? )?((torn|broken|fractured|ruptured|dislocated|separated|sprained|high[- ]ankle|lisfranc|acl|mcl|achilles)[^,.;:!?]{0,40})", re.I)
def breaking_events():
    """fresh, fantasy-relevant news: official injury report and transactions (data run), and headlines (every 10 minutes)"""
    E = []
    # fantasy-relevant: a consensus top-150 player, or a real role; a backup quarterback is news only as the starter
    rel = lambda p: p and ((p.get('ecr') or 999) <= 150 or (p['p'] == 'QB' and (p.get('role') == 'QB1' or p.get('qbs')))
                           or (p['p'] != 'QB' and ((p.get('rl') or 0) >= 9 or p.get('role') in ('RB1', 'WR1', 'WR2', 'TE1'))))
    def kicked(p):   # his next game has started: "ruled out" for it is no longer news
        x = next((y for y in (D.get('sched') or {}).get(p['t']) or [] if y[0] == p.get('nw') and len(y) > 5 and y[5]), None)
        return bool(x and pdt(x[5]) and pdt(x[5]) <= NOW)
    built = min(NOW, pdt(D['asof'].get('built') + 'T12:00:00+00:00')) if D['asof'].get('built') else NOW
    nw = D['asof'].get('next_week')
    for d in D.get('news') or []:
        p = PI.get(d.get('id'))
        if not rel(p): continue
        x = d.get('x') or ''; m_ = re.search(r'week (\d+)', f"{d.get('d') or ''} {x}")
        # an injury report is about one game: only the report for the player's next game is news (a week 6 "Out" is
        # history once his week 6 game is over); roster moves count from the current week on
        if d['k'] == 'inj' and (not m_ or int(m_.group(1)) != p.get('nw') or kicked(p)): continue
        if m_ and int(m_.group(1)) not in (nw, p.get('nw')): continue   # last week's report is not news
        if d['k'] == 'ir': E.append(dict(p=p, kind='activated' if re.search(r'activat', x, re.I) else 'ir', why=None, src='official roster data (nflverse)', at=pdt(d.get('d')) or built))
        elif d['k'] == 'inj' and d.get('st') in ('Out', 'Doubtful'):
            m = re.search(r'\(([^)]+)\)', x); E.append(dict(p=p, kind=d['st'].lower(), why=m.group(1) if m else None, src='the official injury report', at=pdt(d.get('d')) or built))
        elif d['k'] == 'move' and re.search(r'\btrade', x, re.I): E.append(dict(p=p, kind='traded', why=None, src='official roster data (nflverse)', at=pdt(d.get('d')) or built))
        elif d['k'] == 'move' and re.search(r'releas|waiv|cut', x, re.I): E.append(dict(p=p, kind='released', why=None, src='official roster data (nflverse)', at=pdt(d.get('d')) or built))
    INGAME = re.compile(r"\b(remainder|rest of (the )?(game|day|contest|half)|won't return|will not return|(questionable|doubtful|unlikely) to return|ruled out (of|for) (the |today's |sunday's |monday's |thursday's )?game)", re.I)
    for h in NEWS.get('items') or []:
        if h.get('st') != 'out': continue
        if INGAME.search(h.get('h', '')) and not re.search(r'season', h.get('h', ''), re.I): continue   # hurt during a game: not a status for the next one
        for pid in h.get('p') or []:
            p = PI.get(pid)
            if rel(p) and not kicked(p):
                k = 'season' if SEASON_RE.search(h.get('h', '')) else 'ir' if re.search(r'\b(ir|injured reserve)\b', h.get('h', ''), re.I) else 'out'
                dx = DIAG_RE.search(h.get('h', ''))
                E.append(dict(p=p, kind=k, why=dx.group(3).strip() if dx else None, src=h.get('s') or 'news reports', url=h.get('u') or '', at=pdt(h.get('d')) or NOW))
    E = [e for e in E if e['at'] and NOW - e['at'] < datetime.timedelta(hours=48)]
    rank = {'season': -1, 'ir': 0, 'traded': 1, 'released': 2, 'out': 3, 'doubtful': 4, 'activated': 5}; best = {}
    for e in E:
        pid = e['p']['id']
        if pid not in best or rank[e['kind']] < rank[best[pid]['kind']]: best[pid] = e
    return sorted(best.values(), key=lambda e: -(e['p'].get('rl') or 0))


# ---------------------------------------------------------------- the optional Claude writer
KEEP_BLOCKS = ('game', 'score', 'scores', 'pl')
def claude_rewrite(art, facts):
    key = os.environ.get('ANTHROPIC_API_KEY')
    if not key: return None
    if len(AI_LOG) >= AI_MAX: print(f'Claude writer: daily limit of {AI_MAX} calls reached, using BFF text'); return None
    AI_LOG.append(iso(NOW))
    model = os.environ.get('BFF_AI_MODEL') or 'claude-sonnet-5-5'
    sysmsg = ("You are the lead writer of BFF (Ben's Fantasy Football), a fantasy football newsletter. Rewrite the draft you are given into a polished, "
              "engaging newsletter article: a strong lede, natural transitions, analysis of what the numbers mean for fantasy managers, in a confident "
              "professional sports-media voice. Use ONLY the facts in the draft and fact sheet: never invent statistics, quotes, injuries, people or events, "
              "and keep every number exactly as given. Keep the section headings' order and keep every structured block (lists starting with \"game\", "
              "\"score\", \"scores\" or \"pl\") exactly as given, in the same place. Return ONLY JSON: "
              '{"title": str, "dek": str, "body": [["h", text] | ["p", text] | ["ul", [text, ...]] | ["pull", text] | the structured blocks unchanged]}.')
    msg = json.dumps({'draft': {k: art[k] for k in ('title', 'dek', 'body')}, 'facts': facts}, separators=(',', ':'))
    req = urllib.request.Request(os.environ.get('BFF_AI_URL') or 'https://api.anthropic.com/v1/messages', method='POST', data=json.dumps(
        {'model': model, 'max_tokens': 4000 if art['kind'] in ('slate', 'landscape', 'recap') else 2500, 'system': sysmsg, 'messages': [{'role': 'user', 'content': msg}]}).encode(),
        headers={'x-api-key': key, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=120) as r: R = json.loads(r.read())
        txt = ''.join(b.get('text', '') for b in R.get('content', []) if b.get('type') == 'text')
        o = json.loads(txt[txt.index('{'):txt.rindex('}') + 1])
        allowed = set(re.findall(r'\d+(?:\.\d+)?', msg)) | {str(i) for i in range(0, 21)}
        bad = [n for n in re.findall(r'\d+(?:\.\d+)?', json.dumps(o)) if n not in allowed]
        if bad or not isinstance(o.get('body'), list) or not o.get('title'):
            print('Claude version not used (numbers not in the facts: %s)' % bad[:5]); return None
        orig = [b for b in art['body'] if b[0] in KEEP_BLOCKS]; it_ = iter(orig); body = []
        for b in o['body']:
            if not isinstance(b, list) or not b: continue
            if b[0] in KEEP_BLOCKS:
                nb = next(it_, None)
                if nb is None or nb[0] != b[0]: print('Claude version not used (structured blocks changed)'); return None
                body.append(nb)
            elif len(b) == 2 and b[0] in ('h', 'p', 'pull') and isinstance(b[1], str): body.append(b)
            elif len(b) == 2 and b[0] == 'ul' and isinstance(b[1], list): body.append(['ul', [str(x) for x in b[1]]])
        if next(it_, None) is not None: print('Claude version not used (structured blocks missing)'); return None
        if len(body) < 3: return None
        return dict(title=str(o['title'])[:140], dek=str(o.get('dek') or art['dek'])[:300], body=body)
    except Exception as e:
        print('Claude writer unavailable, using BFF text:', str(e)[:120]); return None


# ---------------------------------------------------------------- deciding what to publish
# writer version: raise it when a fix to a writer should correct the article still in its window (Tuesday landscape).
# 2: injury statuses are named by their source; a player who just missed time is injury news, not a usage faller;
#    a starter who barely played his last game is flagged as a possible injury (landscape fallers, recap stock down)
#    5: season-ending news is its own kind of breaking story (not "ruled out for week N"), with the diagnosis; recaps
#       note a player since ruled out for the season or placed on injured reserve
WV = 6
def publish(aid, key, made, once=False):
    art, digest = made
    if not art: return False
    old = ARTS.get(aid); now = iso(NOW)
    sig = hashlib.md5(json.dumps([art['title'], art['body']], sort_keys=True).encode()).hexdigest()
    if old and old.get('sig') == sig: return False
    if old and (once or old.get('kind') in ('recap', 'breaking', 'landscape')) and old.get('wv', 1) >= WV: return False   # written once (a writer fix rewrites it in its window)
    notes = list((old or {}).get('notes') or [])
    if old and digest:
        ch = change_notes(old.get('digest'), digest)
        if ch: notes = [[now, 'Updated: ' + '; '.join(ch) + '.']] + notes[:4]
    ai = claude_rewrite(art, {'week': art['wk'], 'players': {i: {k: PI[i].get(k) for k in ('n', 'p', 't', 'proj', 'rl', 'fpg', 'inj', 'own', 'role')} for i in art['players'][:25] if i in PI}})
    if ai: art.update(ai)
    ARTS[aid] = dict(art, id=aid, key=key, sig=sig, digest=digest, notes=notes, pub=(old or {}).get('pub') or now, upd=now, by='BFF AI Desk (Claude)' if ai else 'BFF Data Desk', ai=bool(ai), season=SEASON, wv=WV)
    print(('updated' if old else 'published'), aid, '|', ARTS[aid]['title']); return True


def boxed(gs):
    """every game has a box score (live, or the official stats the morning after)"""
    return all(box_rows(g) for g in gs)
def run():
    made = 0
    # games around now, grouped by day (Eastern)
    near = [g for g in GAMES if -datetime.timedelta(days=4) < g['kick'] - NOW < datetime.timedelta(days=8)]
    by_day = {}
    for g in near: by_day.setdefault(gday(g), []).append(g)
    for day, gs in sorted(by_day.items()):
        w = gs[0]['wk']; wd = day.weekday(); dname = DOW[wd].lower()[:3]; first = min(g['kick'] for g in gs); pre = [g for g in gs if g['state'] == 'pre']
        if wd == 6:   # Sunday: Saturday-morning outlook; afternoon recap before the night game; night recap
            opens = at_et(day - datetime.timedelta(days=1), 8)
            if opens <= NOW < first and pre: aid = f"{SEASON}-w{w}-sun-outlook"; made += publish(aid, aid, write_sunday_outlook(gs, aid))
            aft = [g for g in gs if ghour(g) < 19]; night = [g for g in gs if ghour(g) >= 19]
            if aft and all(g['state'] == 'post' for g in aft) and NOW > max(g['kick'] for g in aft) + datetime.timedelta(hours=3):
                aid = f"{SEASON}-w{w}-sun-recap"; late_ok = NOW >= at_et(day + datetime.timedelta(days=1), 10)
                if aid not in ARTS and (boxed(aft) or late_ok) and NOW - max(g['kick'] for g in aft) < datetime.timedelta(days=3):
                    made += publish(aid, aid, write_window_recap(aft, aid, f"Week {w} Sunday", [g for g in night if g['state'] != 'post' or g['kick'] > NOW]), once=True)
            if night and all(g['state'] == 'post' for g in night) and NOW > max(g['kick'] for g in night) + datetime.timedelta(hours=3):
                aid = f"{SEASON}-w{w}-snf-recap"
                if aid not in ARTS and (boxed(night) or NOW >= at_et(day + datetime.timedelta(days=1), 10)) and NOW - max(g['kick'] for g in night) < datetime.timedelta(days=3):
                    made += publish(aid, aid, write_recap(night, aid, 'Sunday night'), once=True)
            continue
        # Thursday, Monday and other days: an outlook that morning (8 AM, or 10 hours before an early kickoff)
        opens = min(at_et(day, 8), first - datetime.timedelta(hours=10))
        label = {'thu': 'Thursday', 'mon': 'Monday', 'fri': 'Friday', 'sat': 'Saturday', 'tue': 'Tuesday', 'wed': 'Wednesday'}[dname]
        if day.month == 12 and day.day == 25: label = 'Christmas'
        if opens <= NOW < first and pre: aid = f"{SEASON}-w{w}-{dname}-outlook"; made += publish(aid, aid, write_outlook(gs, aid, label))
        # recap: right after the final for Monday (and the night it ends), the next morning at 7 for Thursday and other days
        if all(g['state'] == 'post' for g in gs) and datetime.timedelta(hours=3) < NOW - max(g['kick'] for g in gs) < datetime.timedelta(days=3):
            aid = f"{SEASON}-w{w}-{dname}-recap"; ready = NOW >= at_et(day + datetime.timedelta(days=1), 7) if wd != 0 else True
            if (aid not in ARTS or ARTS[aid].get('wv', 1) < WV) and ready and (boxed(gs) or NOW >= at_et(day + datetime.timedelta(days=1), 10)):
                made += publish(aid, aid, write_recap(gs, aid, label), once=True)
    # Friday 5 PM injury report for the coming Sunday (updated until Sunday's first kickoff)
    for day, gs in sorted(by_day.items()):
        if day.weekday() != 6: continue
        w = gs[0]['wk']; opens = at_et(day - datetime.timedelta(days=2), 17); first = min(g['kick'] for g in gs)
        if opens <= NOW < first: aid = f"{SEASON}-w{w}-injuries"; made += publish(aid, aid, write_injury_report(w, [g for g in near if g['wk'] == w and g['state'] == 'pre'], aid))
    # Tuesday 10 AM landscape once every game of the week is final (written once)
    for w in sorted({g['wk'] for g in near}):
        wg = [g for g in GAMES if g['wk'] == w]
        if not wg or not all(g['state'] == 'post' for g in wg) or NOW < max(g['kick'] for g in wg): continue
        endday = max(gday(g) for g in wg); tue = endday + datetime.timedelta(days=(1 - endday.weekday()) % 7 or 7)
        if at_et(tue, 10) <= NOW < at_et(tue, 10) + datetime.timedelta(days=2):
            aid = f"{SEASON}-w{w}-landscape"
            if aid not in ARTS or ARTS[aid].get('wv', 1) < WV: made += publish(aid, aid, write_landscape(w, aid), once=True)
    # breaking news
    today = [a for a in ARTS.values() if a.get('kind') == 'breaking' and pdt(a.get('pub')) and NOW - pdt(a['pub']) < datetime.timedelta(hours=24)]
    room = min(MAX_BRK_RUN, MAX_BRK_DAY - len(today)); done = set(); cur = set()
    first_run = 'seen' not in OLD or OLD.get('bv') != BV   # a new file, or news keys from an older version: learn what is known, publish nothing
    for e in breaking_events():
        k = f"brk-{e['p']['id']}-{e['kind']}" + (f"-w{e['p'].get('nw')}" if e['kind'] in ('out', 'doubtful') else ''); cur.add(k)   # ruled out again next week is new news
        if k not in SEEN: SEEN[k] = iso(NOW - datetime.timedelta(days=1) if first_run else NOW)   # learned on a first run = already known
        # only news first seen in the last 6 hours becomes an article (the first run just learns what is already known)
        if first_run or room <= 0 or NOW - pdt(SEEN[k]) > datetime.timedelta(hours=6): continue
        recent = [a for a in ARTS.values() if a.get('key') == k and pdt(a.get('pub')) and NOW - pdt(a['pub']) < datetime.timedelta(days=6)]
        if recent or k in done: continue
        done.add(k); aid = f"{SEASON}-{k}-{NOW.strftime('%m%d')}"
        if e['kind'] == 'season':
            prior = [a for a in ARTS.values() if a.get('kind') == 'breaking' and str(a.get('key', '')).startswith(f"brk-{e['p']['id']}-out") and pdt(a.get('pub')) and NOW - pdt(a['pub']) < datetime.timedelta(days=6)]
            if prior: aid = prior[0]['id']; ARTS[aid]['wv'] = 0; ARTS[aid]['key'] = k   # replace it in place (same link, corrected story)
        if publish(aid, k, write_breaking(e['p'], e, aid)): room -= 1; made += 1
    # keep three weeks
    keep = {i: a for i, a in ARTS.items() if pdt(a.get('upd')) and NOW - pdt(a['upd']) < datetime.timedelta(days=KEEP_DAYS)}
    items = sorted(keep.values(), key=lambda a: a['upd'], reverse=True)
    seen = {k: v for k, v in SEEN.items() if k in cur or (pdt(v) and NOW - pdt(v) < datetime.timedelta(days=14))}
    new = {'season': SEASON, 'at': iso(NOW) if made else OLD.get('at', iso(NOW)), 'bv': BV, 'items': items, 'seen': seen, **({'ai_log': AI_LOG} if AI_LOG else {})}
    if made or len(items) != len(OLD.get('items') or []) or seen != OLD.get('seen') or AI_LOG != (OLD.get('ai_log') or []) or OLD.get('bv') != BV or not os.path.exists(OUT):
        json.dump(new, open(OUT, 'w'), separators=(',', ':')); print(f'articles: {made} new or updated, {len(items)} kept')
    else: print('articles: nothing new')


if __name__ == '__main__':
    try: run()
    except Exception:   # never break the live job
        import traceback; traceback.print_exc(); print('articles: skipped this run'); sys.exit(0)
