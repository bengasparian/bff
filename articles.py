"""BFF Originals: data-driven fantasy football articles, written and updated automatically.

Runs every 10 minutes with the live job (standard library only). Each run decides what should exist right now:
  * Breaking news  - a star or starter is ruled out, placed on injured reserve, traded or released: what it means for
                     fantasy, who benefits, and waiver moves. At most 3 a run and 12 a day.
  * Sunday preview - every Saturday from 8 AM ET: every Sunday game's fantasy angles, start/sit calls and Vegas lines.
  * Game previews  - Thursday, Monday and any other day with games (Saturday, Christmas, Black Friday...): published
                     10 hours before the first kickoff of that day.
  * Recaps         - once every game of a day is final: fantasy winners, surprises and waiver adds.
Previews are rewritten on every run until kickoff, so injuries and line moves show up, with a dated update note.

Writers: BFF's own writer (always on, free) builds the text from the data. If the repository has an ANTHROPIC_API_KEY
secret, Claude rewrites each article from the same fact sheet (model: BFF_AI_MODEL, default claude-sonnet-5-5); any
number Claude uses must appear in the facts, or BFF's own version is kept.

Inputs: index.html (the page's data), live.json (scores, box scores), news.json (headlines), lines.json, articles.json.
Output: articles.json.     Testing: BFF_NOW=2026-10-18T12:00:00Z python articles.py
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


def iso(d): return d.astimezone(UTC).isoformat(timespec='seconds')
def pdt(s):
    try: return datetime.datetime.fromisoformat(str(s).replace('Z', '+00:00')).astimezone(UTC)
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
def seed(*a): return int(hashlib.md5('|'.join(map(str, a)).encode()).hexdigest()[:8], 16)
def pick(opts, *k): return opts[seed(*k) % len(opts)]
def normn(s): return re.sub(r'\b(jr|sr|ii|iii|iv|v)\b', '', re.sub(r"[.'’`-]", '', str(s or '').lower())).strip()
def last(n): return re.sub(r'\s+(Jr\.?|Sr\.?|II|III|IV|V)$', '', n).split()[-1]
def plural(n, w): return f'{n} {w}' + ('' if n == 1 else 's')
def andj(L): L = list(L); return L[0] if len(L) == 1 else ', '.join(L[:-1]) + ' and ' + L[-1] if L else ''
def tm_name(t): return TEAMS.get(t, t)
TEAMS = {'ARI': 'Cardinals', 'ATL': 'Falcons', 'BAL': 'Ravens', 'BUF': 'Bills', 'CAR': 'Panthers', 'CHI': 'Bears', 'CIN': 'Bengals', 'CLE': 'Browns', 'DAL': 'Cowboys', 'DEN': 'Broncos',
         'DET': 'Lions', 'GB': 'Packers', 'HOU': 'Texans', 'IND': 'Colts', 'JAX': 'Jaguars', 'KC': 'Chiefs', 'LA': 'Rams', 'LAC': 'Chargers', 'LV': 'Raiders', 'MIA': 'Dolphins',
         'MIN': 'Vikings', 'NE': 'Patriots', 'NO': 'Saints', 'NYG': 'Giants', 'NYJ': 'Jets', 'PHI': 'Eagles', 'PIT': 'Steelers', 'SEA': 'Seahawks', 'SF': '49ers', 'TB': 'Buccaneers',
         'TEN': 'Titans', 'WAS': 'Commanders'}


# ---------------------------------------------------------------- the data
D = page_data(); P = D['players']; PI = {p['id']: p for p in P}; SEASON = D['asof']['season']
LIVE = load('live.json', {}); NEWS = load('news.json', {}); LINES = load('lines.json', None) or D.get('lines') or {}
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


def proj_wk(p, w):
    if p.get('nw') == w: return 0.0 if p.get('inj') in ('Out', 'IR') else float(p.get('proj') or 0)
    for r in p.get('ros') or []:
        if r[0] == w: return float(r[2] or 0)
    return 0.0
def proj_then(p, w):
    """what BFF projected for week w (locked projection for a finished game when available)"""
    ph = (D.get('ph') or {}).get(p['id'])
    if ph and D['asof'].get('next_week') == w: return float(ph[0])
    v = proj_wk(p, w); return v if v > 0 else None
def ppr(r): return (r.get('py') or 0) * .04 + (r.get('ptd') or 0) * 4 - (r.get('int') or 0) * 2 + (r.get('ry') or 0) * .1 + (r.get('rtd') or 0) * 6 + (r.get('ty') or 0) * .1 + (r.get('rectd') or 0) * 6 + (r.get('rec') or 0) - (r.get('fl') or 0) * 2
def statline(r):
    s = []
    if r.get('pa'): s.append(f"{r.get('pc', 0)}/{r['pa']}, {r.get('py', 0)} yds" + (f", {r['ptd']} TD" if r.get('ptd') else '') + (f", {r['int']} INT" if r.get('int') else ''))
    if r.get('ra'): s.append(f"{plural(r['ra'], 'carry').replace('carrys', 'carries')}, {r.get('ry', 0)} yds" + (f", {r['rtd']} TD" if r.get('rtd') else ''))
    if r.get('rec') or r.get('tg'): s.append(f"{plural(r.get('rec', 0), 'catch').replace('catchs', 'catches')}" + (f" on {plural(r['tg'], 'target')}" if r.get('tg') else '') + f", {r.get('ty', 0)} yds" + (f", {r['rectd']} TD" if r.get('rectd') else ''))
    return '; '.join(s)


def games():
    """every game from the schedule (from the home team's row), with Vegas numbers and kickoff"""
    G = {}
    for t, rows in (D.get('sched') or {}).items():
        for r in rows:
            if len(r) < 6 or not r[2] or not r[5]: continue
            k = pdt(r[5]); sp = r[6] if len(r) > 6 else None; ou = r[7] if len(r) > 7 else None
            opp_row = next((x for x in D['sched'].get(r[1], []) if x[0] == r[0]), None)
            G[(r[0], t)] = dict(wk=r[0], home=t, away=r[1], kick=k, sp=sp, ou=ou, ih=r[3], ia=opp_row[3] if opp_row else None,
                                hs=r[4], as_=opp_row[4] if opp_row else None)
    for x in LIVE.get('games') or []:   # live scores and states override
        for g in G.values():
            if g['home'] == x.get('home') and g['away'] == x.get('away') and abs((g['kick'] - (pdt(x.get('kick')) or g['kick'])).total_seconds()) < 86400 * 3:
                g.update(state=x.get('state'), gid=str(x.get('id')), hs=x.get('hs') if x.get('hs') is not None else g['hs'], as_=x.get('as') if x.get('as') is not None else g['as'])
    for g in G.values():
        if 'state' not in g: g['state'] = 'post' if g['hs'] is not None else 'pre'
    return sorted(G.values(), key=lambda g: g['kick'])
GAMES = games()
def gday(g): return g['kick'].astimezone(ET).date()
def gtime(g): t = g['kick'].astimezone(ET); return t.strftime('%-I:%M %p ET') if t.minute else t.strftime('%-I %p ET')
def vegas(g):
    if g['sp'] is None or g['ou'] is None: return ''
    fav, sp = (g['home'], -g['sp']) if g['sp'] <= 0 else (g['away'], g['sp'])
    return f"{tm_name(fav)} by {f1(abs(sp)).rstrip('0').rstrip('.')}, total {g['ou']}" if sp else f"a pick'em, total {g['ou']}"
def team_players(t, w, n=3, pos=None):
    L = [p for p in P if p['t'] == t and (pos is None or p['p'] in pos) and proj_wk(p, w) > 0]
    return sorted(L, key=lambda p: -proj_wk(p, w))[:n]
DVP = D.get('dvp') or {}
def dvp_rank(opp, pos):
    v = (DVP.get(opp) or {}).get(pos)   # [points allowed a game, games, factor, rank (1 = allows the fewest)]
    return v[3] if isinstance(v, list) and len(v) > 3 else None
def matchup_words(opp, pos):
    r = dvp_rank(opp, pos)
    if r is None: return ''
    a = 'an' if tm_name(opp)[0] in 'AEIOU' else 'a'
    if r >= 26: return f"{a} {tm_name(opp)} defense that has allowed the {ordn(33 - r)}-most fantasy points to {pos}s"
    if r <= 6: return f"{a} {tm_name(opp)} defense that has allowed the {ordn(r)}-fewest fantasy points to {pos}s"
    return ''
def ordn(n): return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"
def wk_rank(p, w):
    L = sorted([q for q in P if q['p'] == p['p'] and proj_wk(q, w) > 0], key=lambda q: -proj_wk(q, w))
    return L.index(p) + 1 if p in L else None
def usual_rank(p):
    L = sorted([q for q in P if q['p'] == p['p'] and (q.get('rl') or q.get('fpg'))], key=lambda q: -(q.get('rl') or q.get('fpg') or 0))
    return L.index(p) + 1 if p in L else None
def picks_for(teams, w):
    L = [x for x in (LINES.get('lines') or []) if x.get('pick') and PI.get(x.get('pid')) and PI[x['pid']]['t'] in teams and LINES.get('wk') == w]
    return sorted(L, key=lambda x: -max(x.get('po', .5), 1 - x.get('po', .5)))
SNAME = {'py': 'passing yards', 'ptd': 'passing TDs', 'ry': 'rushing yards', 'ty': 'receiving yards', 'rec': 'receptions', 'td': 'anytime TD'}
def injured(teams, w):
    out = []
    for p in P:
        if p['t'] in teams and p.get('inj') in ('Out', 'Doubtful', 'Questionable', 'IR') and ((p.get('rl') or 0) >= 8 or (p.get('ecr') or 999) <= 150):
            out.append(p)
    return sorted(out, key=lambda p: -(p.get('rl') or 0))


# ---------------------------------------------------------------- article pieces
def P_(text): return ['p', text]
def H_(text): return ['h', text]
def UL(items): return ['ul', [x for x in items if x]]
def PL(p, note): return ['pl', p['id'], note]
def GH(g): return ['game', g['away'], g['home'], g.get('gid')]
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
        elif abs((o[1] or 0) - (pj or 0)) >= 1.5: notes.append(f"{n}'s projection moved from {f1(o[1])} to {f1(pj)}")
    for k, (sp, ou) in new.get('g', {}).items():
        o = (old or {}).get('g', {}).get(k)
        if o and o[1] is not None and ou is not None and abs(o[1] - ou) >= 1.5: notes.append(f"the {k.replace('@', ' at ')} total moved from {o[1]} to {ou}")
    return notes[:4]


def game_block(g, depth):
    """paragraphs about one game: line, top projections, matchups, injuries and the best prop pick"""
    w = g['wk']; out = [GH(g)]; tms = [g['away'], g['home']]
    ih = g['ih']; ia = g['ia']
    lead = f"{tm_name(g['away'])} at {tm_name(g['home'])}, {gtime(g)}."
    if vegas(g): lead += f" Vegas has the {vegas(g)}" + (f", which implies {f1(ia)} points for {g['away']} and {f1(ih)} for {g['home']}." if ih and ia else '.')
    out.append(P_(lead))
    tops = sorted(team_players(g['away'], w, 3) + team_players(g['home'], w, 3), key=lambda p: -proj_wk(p, w))[:depth]
    lines = []
    for p in tops:
        opp = g['home'] if p['t'] == g['away'] else g['away']; mw = matchup_words(opp, p['p']); rk = wk_rank(p, w)
        s = f"{p['n']} ({p['p']}, {p['t']}) projects for {f1(proj_wk(p, w))} points" + (f", {p['p']}{rk} this week" if rk and rk <= 36 else '')
        if mw: s += f" against {mw}"
        lines.append(s + '.')
    if lines: out.append(UL(lines))
    inj = injured(tms, w)[:4]
    if inj: out.append(P_('Injury report: ' + '; '.join(f"{p['n']} ({p['inj'].lower() if p['inj'] != 'IR' else 'injured reserve'})" for p in inj) + '.'))
    pk = picks_for(tms, w)[:1]
    if pk:
        x = pk[0]; p = PI[x['pid']]; pr = max(x['po'], 1 - x['po'])
        out.append(P_(f"Best prop lean: {p['n']} {'over' if x['po'] >= .5 else 'under'} {x['line']} {SNAME.get(x['k'], x['k'].replace('_', ' '))} (BFF gives it {round(pr * 100)}%)."))
    return out, tops


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


def write_slate(gs, key):
    """the Saturday article for the Sunday slate"""
    w = gs[0]['wk']; body = []; mentioned = []
    with_lines = [g for g in gs if g['ou'] is not None]
    hi = max(with_lines, key=lambda g: g['ou']) if with_lines else None
    fav = max(with_lines, key=lambda g: abs(g['sp'] or 0)) if with_lines else None
    best_it = max([(g['ih'], g['home'], g) for g in gs if g['ih']] + [(g['ia'], g['away'], g) for g in gs if g['ia']], default=None, key=lambda x: x[0])
    outs = [p for p in injured({t for g in gs for t in (g['home'], g['away'])}, w) if p.get('inj') in ('Out', 'IR', 'Doubtful')]
    intro = pick([f"Sunday brings {plural(len(gs), 'game')} and plenty of lineup decisions.", f"{len(gs)} games, {len(gs) * 2} teams and a week {w} that will decide a lot of matchups.",
                  f"The week {w} Sunday slate is set: {plural(len(gs), 'game')} from the early window through Sunday night."], key)
    if hi: intro += f" The highest total belongs to {tm_name(hi['away'])} at {tm_name(hi['home'])} ({hi['ou']}),"
    if best_it: intro += f" and the {tm_name(best_it[1])} carry the biggest implied team total at {f1(best_it[0])} points."
    elif hi: intro = intro.rstrip(',') + '.'
    body.append(P_(intro))
    if outs: body.append(P_(f"Key absences so far: {andj([p['n'] + ' (' + p['t'] + ')' for p in outs[:5]])}. Everything below already accounts for them, and this preview updates itself until kickoff."))
    st, sit = start_sit(gs, w)
    if st or sit:
        body.append(H_('Start and sit'))
        L = [f"Start {p['n']} ({p['p']}, {p['t']}): ranks {p['p']}{wr} this week, well above his usual {p['p']}{ur}." for _, p, wr, ur in st]
        L += [f"Sit {p['n']} ({p['p']}, {p['t']}{', ' + p['inj'].lower() if p.get('inj') else ''}): only {p['p']}{wr} this week after ranking {p['p']}{ur} most weeks." for _, p, wr, ur in sit]
        body.append(UL(L)); mentioned += [x[1] for x in st + sit]
    body.append(H_('Game by game'))
    for g in gs:
        blk, tops = game_block(g, 3); body += blk; mentioned += tops
    if fav and fav['sp']:
        f_ = g_fav(fav); body.append(P_(f"Biggest favorite: the {tm_name(f_[0])}, laying {f1(abs(fav['sp'])).rstrip('0').rstrip('.')} points. Big favorites lean on the run late, which helps their running backs more than their receivers."))
    title = pick([f"Week {w} Sunday preview: {hi['away']}-{hi['home']} headlines a {len(gs)}-game slate" if hi else f"Week {w} Sunday preview",
                  f"Week {w} Sunday preview: every game's fantasy angle", f"Sunday, week {w}: who to start, who to sit, what Vegas expects"], key, 't')
    dek = f"Start/sit calls, matchups, injuries and Vegas angles for all {len(gs)} Sunday games, from BFF's projections. Updates until kickoff."
    SRC_PRE = [{'s': 'BFF projections', 'u': ''}, {'s': 'Vegas lines and schedule (nflverse)', 'u': 'https://github.com/nflverse/nfldata'}, {'s': 'Official injury reports (nflverse)', 'u': 'https://github.com/nflverse/nflverse-data'}]
    return dict(kind='slate', src=SRC_PRE, title=title, dek=dek, body=body, players=uniq(mentioned), teams=sorted({t for g in gs for t in (g['home'], g['away'])}), wk=w,
                img={'k': 'game', 'away': hi['away'], 'home': hi['home'], 'gid': hi.get('gid')} if hi else None), facts_digest([PI[i] for i in uniq(mentioned)], gs)
def g_fav(g): return (g['home'], -g['sp']) if g['sp'] <= 0 else (g['away'], g['sp'])
def uniq(L):
    seen = []; [seen.append(p['id'] if isinstance(p, dict) else p) for p in L if (p['id'] if isinstance(p, dict) else p) not in seen]; return seen


def write_game_day(gs, key):
    """Thursday, Monday or any other non-Sunday day of games"""
    w = gs[0]['wk']; day = DOW[gday(gs[0]).weekday()]; body = []; mentioned = []
    night = gs[0]['kick'].astimezone(ET).hour >= 19
    label = {'Thursday': 'Thursday Night Football', 'Monday': 'Monday Night Football'}.get(day) if night and len(gs) == 1 else None
    g0 = gs[0]
    if len(gs) == 1:
        title = pick([f"{label or day} preview: {g0['away']} at {g0['home']}, the fantasy plays", f"{g0['away']} at {g0['home']}: {label or day} fantasy preview and best bets",
                      f"{label or day}: what to expect from {tm_name(g0['away'])} at {tm_name(g0['home'])}"], key)
    else:
        title = f"{day}'s {len(gs)} games: the week {w} fantasy preview"
    intro = pick([f"{label or day} kicks off {gtime(g0)}.", f"Week {w} {'continues' if day != 'Thursday' else 'starts'} {day.lower()}{' night' if night else ''}.",
                  f"Lineups lock early for {plural(len(gs), 'game')} on {day}."], key, 'i')
    body.append(P_(intro + " Here is what BFF's projections, the Vegas line and the injury report say."))
    for g in gs:
        blk, tops = game_block(g, 5); body += blk; mentioned += tops
    st, sit = start_sit(gs, w)
    if st or sit:
        body.append(H_('Start and sit'))
        body.append(UL([f"Start {p['n']}: {p['p']}{wr} this week, above his usual {p['p']}{ur}." for _, p, wr, ur in st] + [f"Sit {p['n']}: {p['p']}{wr} this week, below his usual {p['p']}{ur}." for _, p, wr, ur in sit]))
        mentioned += [x[1] for x in st + sit]
    dek = f"Projections, matchups, injuries and prop leans for {'the game' if len(gs) == 1 else 'every game'} on {day}, from BFF's data. Updates until kickoff."
    SRC_PRE = [{'s': 'BFF projections', 'u': ''}, {'s': 'Vegas lines and schedule (nflverse)', 'u': 'https://github.com/nflverse/nfldata'}, {'s': 'Official injury reports (nflverse)', 'u': 'https://github.com/nflverse/nflverse-data'}]
    return dict(kind='preview', src=SRC_PRE, title=title, dek=dek, body=body, players=uniq(mentioned), teams=sorted({t for g in gs for t in (g['home'], g['away'])}), wk=w,
                img={'k': 'game', 'away': g0['away'], 'home': g0['home'], 'gid': g0.get('gid')}), facts_digest([PI[i] for i in uniq(mentioned)], gs)


def box_rows(g):
    """fantasy lines for a finished game: the live box score, else the weekly stats in the page data"""
    B = (LIVE.get('box') or {}).get(str(g.get('gid'))) if g.get('gid') else None
    rows = []
    BL = B.get('players') if isinstance(B, dict) else B if isinstance(B, list) else None
    if BL:
        for r in BL:
            p = NAMEIX.get((r.get('t'), normn(r.get('n'))))
            if p: rows.append((p, r))
    if not rows:
        for p in P:
            if p['t'] not in (g['home'], g['away']): continue
            gl = next((x for x in p.get('gl') or [] if x[0] == g['wk']), None)
            if gl: rows.append((p, dict(pc=gl[1], pa=gl[2], py=gl[3], ptd=gl[4], int=gl[5], ra=gl[6], ry=gl[7], rtd=gl[8], rec=gl[9], tg=gl[10], ty=gl[11], rectd=gl[12], fl=gl[13])))
    return rows


def write_recap(gs, key):
    w = gs[0]['wk']; day = DOW[gday(gs[0]).weekday()]; body = []; rows = []
    for g in gs: rows += [(p, r, ppr(r), proj_then(p, w), g) for p, r in box_rows(g)]
    if not rows: return None, None
    rows.sort(key=lambda x: -x[2]); top = rows[0]
    scores = [(f"{tm_name(g['home'])} {g['hs']}, {tm_name(g['away'])} {g['as_']}" if g['hs'] >= g['as_'] else f"{tm_name(g['away'])} {g['as_']}, {tm_name(g['home'])} {g['hs']}") for g in gs if g['hs'] is not None and g['as_'] is not None]
    title = pick([f"{day} recap: {top[0]['n']} leads the fantasy winners with {f1(top[2])}", f"{day} takeaways: {top[0]['n']} posts {f1(top[2])} points",
                  f"Week {w} {day} recap: winners, surprises and waiver adds"], key)
    body.append(P_(('Final' + ('s' if len(scores) > 1 else '') + ': ' + '; '.join(scores) + '.') if scores else f"Every {day} game is final."))
    body.append(H_('Top fantasy performers (PPR)'))
    body.append(UL([f"{p['n']} ({p['p']}, {p['t']}): {f1(pts)} points on {statline(r) or 'limited stats'}" + (f", against a projection of {f1(pj)}" if pj else '') + '.' for p, r, pts, pj, g in rows[:6]]))
    beats = sorted([x for x in rows if x[3] and x[2] - x[3] >= 8], key=lambda x: -(x[2] - x[3]))[:3]
    miss = sorted([x for x in rows if x[3] and x[3] >= 11 and x[3] - x[2] >= 7], key=lambda x: -(x[3] - x[2]))[:3]
    if beats or miss:
        body.append(H_('Surprises'))
        body.append(UL([f"{p['n']} beat his {f1(pj)}-point projection by {f1(pts - pj)}." for p, r, pts, pj, g in beats] + [f"{p['n']} fell {f1(pj - pts)} short of his {f1(pj)}-point projection with {f1(pts)}." for p, r, pts, pj, g in miss]))
    use = []
    for p, r, pts, pj, g in rows:
        if p['p'] in ('WR', 'TE', 'RB') and (r.get('tg') or 0) >= 9: use.append(f"{p['n']} drew {plural(r['tg'], 'target')}, the kind of volume that holds up even in quieter weeks.")
        elif p['p'] == 'RB' and (r.get('ra') or 0) >= 18: use.append(f"{p['n']} handled {plural(r['ra'], 'carry').replace('carrys', 'carries')}, a workhorse share.")
    if use: body.append(H_('Usage to remember')); body.append(UL(use[:4]))
    nxt = [(p, pts) for p, r, pts, pj, g in rows[:4] if p.get('nw') and p['nw'] != w and proj_wk(p, p['nw']) > 0]
    if nxt: body.append(P_('Next up: ' + '; '.join(f"{p['n']} projects for {f1(proj_wk(p, p['nw']))} in week {p['nw']} against the {tm_name(p.get('opp') or '')}" for p, _ in nxt[:3]) + '.'))
    wa = [x for x in rows if (x[0].get('own') is not None and x[0]['own'] < 50) and x[2] >= 12][:3]
    if wa:
        body.append(H_('Waiver watch'))
        body.append(UL([f"{p['n']} ({p['p']}, {p['t']}, rostered in {p['own']}% of leagues) scored {f1(pts)}. One big game is not a role, so check his snaps before spending much." for p, r, pts, pj, g in wa]))
    body.append(P_("Projections for next week update with the next data run, and BFF value, rankings and trade values follow."))
    ment = [x[0] for x in rows[:6]] + [x[0] for x in beats + miss + wa]
    dek = f"Who won your {day}, who disappointed, and who to grab off waivers, from the box scores."
    return dict(kind='recap', src=[{'s': 'ESPN box scores', 'u': 'https://www.espn.com/nfl/scoreboard'}, {'s': 'Official stats (nflverse)', 'u': 'https://github.com/nflverse/nflverse-data'}, {'s': 'BFF projections', 'u': ''}], title=title, dek=dek, body=body, players=uniq(ment), teams=sorted({t for g in gs for t in (g['home'], g['away'])}), wk=w,
                img={'k': 'player', 'pid': top[0]['id']}), None


def teammates(p, n=3):
    L = [q for q in P if q['t'] == p['t'] and q['id'] != p['id'] and q['p'] == p['p'] and (q.get('rl') or 0) > 0]
    return sorted(L, key=lambda q: -(q.get('rl') or 0))[:n]
def write_breaking(p, ev, key):
    w = p.get('nw') or D['asof']['next_week']; kind = ev['kind']; n = p['n']; ln = last(n)
    what = {'ir': f"{n} has been placed on injured reserve", 'out': f"{n} has been ruled out for week {w}", 'doubtful': f"{n} is doubtful for week {w}",
            'traded': f"{n} has been traded", 'released': f"{n} has been released"}[kind]
    title = pick({'ir': [f"{n} to injured reserve: what it means for fantasy", f"{n} lands on IR. Here is the fantasy fallout", f"Fantasy fallout: {n} heads to injured reserve"],
                  'out': [f"{n} ruled out for week {w}: who to start instead", f"Fantasy fallout: {n} is out this week", f"{n} out for week {w}. Here is what to do"],
                  'doubtful': [f"{n} doubtful for week {w}: pivot now", f"{n} is doubtful. Here is your backup plan"],
                  'traded': [f"{n} traded: what it means for fantasy", f"Fantasy fallout from the {n} trade"],
                  'released': [f"{n} released: the fantasy fallout", f"{n} cut: who benefits"]}[kind], key)
    body = [P_(f"{what}{(' (' + ev['why'] + ')') if ev.get('why') else ''}." + (f" First reported by {ev['src']}." if ev.get('src') else ''))]
    ur = usual_rank(p)
    body.append(P_(f"{ln} has averaged {f1(p.get('fpg') or 0)} PPR points a game this season" + (f" and projects as a {p['p']}{ur} the rest of the way when healthy" if ur and ur <= 60 else '') + "."
                   + (f" BFF expects him back around week {p['ret']}, and injured-reserve returns often slip." if kind == 'ir' and p.get('ret') else '')))
    tm = teammates(p); body.append(H_('Who benefits'))
    if tm:
        L = []
        for q in tm:
            s = f"{q['n']} ({q['p']}, {q.get('role') or 'depth'})" + (f": projects for {f1(proj_wk(q, w))} in week {w}" if proj_wk(q, w) > 0 else '')
            if q.get('own') is not None: s += f", rostered in {q['own']}% of leagues"
            L.append(s + '.')
        body.append(UL(L))
        free = [q for q in tm if q.get('own') is not None and q['own'] < 50]
        body.append(P_(f"Waiver priority: {free[0]['n']} is the add if he is on your wire." if free else f"The {p['t']} depth behind {ln} is mostly rostered, so look for help elsewhere on waivers."))
    else:
        body.append(P_(f"The {tm_name(p['t'])} have no clear replacement at {p['p']} in BFF's data, so expect a committee."))
    if p['p'] in ('RB', 'WR', 'TE'):
        qb = next((q for q in P if q['t'] == p['t'] and q['p'] == 'QB' and q.get('role') == 'QB1'), None)
        if qb and p['p'] != 'RB': body.append(P_(f"For {qb['n']}, losing a top target lowers his ceiling; BFF's projections already shift those targets to the receivers still active."))
    body.append(H_('What to do'))
    body.append(UL([{'ir': f"Move {ln} to an IR slot if your league has one; do not drop him unless you need the roster spot for a starter.",
                     'out': f"Start someone else in week {w}; {ln} keeps his rest-of-season value.", 'doubtful': f"Plan to start someone else in week {w} and check the inactive list 90 minutes before kickoff.",
                     'traded': "Wait for his new role before moving him; trade values update after the next data run.", 'released': "He is droppable in most leagues until he signs somewhere."}[kind],
                    "BFF's projections, rankings and trade values already reflect this, or will after the next data update (every 3 hours)."]))
    dek = f"{what}. Who benefits on the {tm_name(p['t'])}, waiver moves and what to do with your lineup."
    src = ([{'s': ev['src'], 'u': ev['url']}] if ev.get('url') else []) + [{'s': 'BFF projections and depth charts (nflverse)', 'u': ''}]
    return dict(kind='breaking', title=title, dek=dek, body=body, players=uniq([p] + tm), teams=[p['t']], wk=w, img={'k': 'player', 'pid': p['id']}, src=src), None


def breaking_events():
    """fresh, fantasy-relevant news: official injury report and transactions (data run), and headlines (every 10 minutes)"""
    E = []
    rel = lambda p: p and ((p.get('ecr') or 999) <= 150 or (p.get('rl') or 0) >= 9 or p.get('role') in ('QB1', 'RB1', 'WR1', 'WR2', 'TE1'))
    built = pdt(D['asof'].get('built') + 'T12:00:00+00:00') if D['asof'].get('built') else NOW
    nw = D['asof'].get('next_week')
    for d in D.get('news') or []:
        p = PI.get(d.get('id'))
        if not rel(p): continue
        x = d.get('x') or ''; m_ = re.search(r'week (\d+)', f"{d.get('d') or ''} {x}")
        if m_ and int(m_.group(1)) not in (nw, p.get('nw')): continue   # last week's report is not news
        if d['k'] == 'ir': E.append(dict(p=p, kind='ir', why=None, src='official roster data (nflverse)', at=pdt(d.get('d')) or built))
        elif d['k'] == 'inj' and d.get('st') in ('Out', 'Doubtful'):
            m = re.search(r'\(([^)]+)\)', x); E.append(dict(p=p, kind=d['st'].lower(), why=m.group(1) if m else None, src='the official injury report', at=pdt(d.get('d')) or built))
        elif d['k'] == 'move' and re.search(r'\btrade', x, re.I): E.append(dict(p=p, kind='traded', why=None, src='official roster data (nflverse)', at=pdt(d.get('d')) or built))
        elif d['k'] == 'move' and re.search(r'releas|waiv|cut', x, re.I): E.append(dict(p=p, kind='released', why=None, src='official roster data (nflverse)', at=pdt(d.get('d')) or built))
    for h in NEWS.get('items') or []:
        if h.get('st') != 'out': continue
        for pid in h.get('p') or []:
            p = PI.get(pid)
            if rel(p):
                k = 'ir' if re.search(r'\b(ir|injured reserve)\b', h.get('h', ''), re.I) else 'out'
                E.append(dict(p=p, kind=k, why=None, src=h.get('s') or 'news reports', url=h.get('u') or '', at=pdt(h.get('d')) or NOW))
    E = [e for e in E if e['at'] and NOW - e['at'] < datetime.timedelta(hours=48)]
    E.sort(key=lambda e: (-(e['p'].get('rl') or 0)))
    return E


# ---------------------------------------------------------------- the optional Claude writer
def claude_rewrite(art, facts):
    key = os.environ.get('ANTHROPIC_API_KEY')
    if not key: return None
    if len(AI_LOG) >= AI_MAX: print(f'Claude writer: daily limit of {AI_MAX} calls reached, using BFF text'); return None
    AI_LOG.append(iso(NOW))
    model = os.environ.get('BFF_AI_MODEL') or 'claude-sonnet-5-5'
    sysmsg = ("You are the lead writer for BFF (Ben's Fantasy Football). Rewrite the draft article you are given into a polished, original, engaging "
              "fantasy football article in a professional sports-media voice. Use ONLY the facts in the draft and fact sheet: never invent statistics, "
              "quotes, injuries, people or events, and keep every number exactly as given. Keep game sections in the same order, each starting with "
              'its ["game", away, home] block. Keep it tight: about 120 words per game or 250-600 words in all. Return ONLY JSON: '
              '{"title": str, "dek": str, "body": [["h", text] | ["p", text] | ["ul", [text, ...]] | ["game", away, home]]}.')
    msg = json.dumps({'draft': {k: art[k] for k in ('title', 'dek', 'body')}, 'facts': facts}, separators=(',', ':'))
    req = urllib.request.Request(os.environ.get('BFF_AI_URL') or 'https://api.anthropic.com/v1/messages', method='POST', data=json.dumps(
        {'model': model, 'max_tokens': 4000 if art['kind'] == 'slate' else 2500, 'system': sysmsg, 'messages': [{'role': 'user', 'content': msg}]}).encode(),
        headers={'x-api-key': key, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=90) as r: R = json.loads(r.read())
        txt = ''.join(b.get('text', '') for b in R.get('content', []) if b.get('type') == 'text')
        o = json.loads(txt[txt.index('{'):txt.rindex('}') + 1])
        allowed = set(re.findall(r'\d+(?:\.\d+)?', msg)) | {str(i) for i in range(0, 21)}
        out_txt = json.dumps(o)
        bad = [n for n in re.findall(r'\d+(?:\.\d+)?', out_txt) if n not in allowed]
        if bad or not isinstance(o.get('body'), list) or not o.get('title'):
            print('Claude version not used (numbers not in the facts: %s)' % bad[:5]); return None
        body = []; gids = {(b[1], b[2]): b[3] for b in art['body'] if b[0] == 'game'}
        for b in o['body']:
            if isinstance(b, list) and len(b) == 2 and b[0] in ('h', 'p') and isinstance(b[1], str): body.append(b)
            elif isinstance(b, list) and len(b) == 2 and b[0] == 'ul' and isinstance(b[1], list): body.append(['ul', [str(x) for x in b[1]]])
            elif isinstance(b, list) and len(b) >= 3 and b[0] == 'game' and (b[1], b[2]) in gids: body.append(['game', b[1], b[2], gids[(b[1], b[2])]])
        if len(gids) and sum(1 for b in body if b[0] == 'game') != len(gids): print('Claude version not used (games missing)'); return None
        if len(body) < 3: return None
        return dict(title=str(o['title'])[:140], dek=str(o.get('dek') or art['dek'])[:300], body=body)
    except Exception as e:
        print('Claude writer unavailable, using BFF text:', str(e)[:120]); return None


# ---------------------------------------------------------------- deciding what to publish
def publish(aid, key, made, open_ok=True):
    art, digest = made
    if not art: return False
    old = ARTS.get(aid); now = iso(NOW)
    sig = hashlib.md5(json.dumps([art['title'], art['body']], sort_keys=True).encode()).hexdigest()
    if old and old.get('sig') == sig: return False
    if old and old.get('kind') in ('recap', 'breaking'): return False   # written once
    notes = list((old or {}).get('notes') or [])
    if old and digest:
        ch = change_notes(old.get('digest'), digest)
        if ch: notes = [[now, 'Updated: ' + '; '.join(ch) + '.']] + notes[:4]
    ai = claude_rewrite(art, {'week': art['wk'], 'players': {i: {k: PI[i].get(k) for k in ('n', 'p', 't', 'proj', 'rl', 'fpg', 'inj', 'own', 'role')} for i in art['players'][:25] if i in PI}})
    if ai: art.update(ai)
    ARTS[aid] = dict(art, id=aid, key=key, sig=sig, digest=digest, notes=notes, pub=(old or {}).get('pub') or now, upd=now, by='BFF AI Desk (Claude)' if ai else 'BFF Data Desk', ai=bool(ai), season=SEASON)
    print(('updated' if old else 'published'), aid, '|', ARTS[aid]['title']); return True


def run():
    made = 0
    by_day = {}
    for g in GAMES:
        if g['kick'] - NOW > datetime.timedelta(days=8) or NOW - g['kick'] > datetime.timedelta(days=3): continue
        by_day.setdefault(gday(g), []).append(g)
    for day, gs in sorted(by_day.items()):
        first = min(g['kick'] for g in gs); dname = DOW[day.weekday()].lower()[:3]; w = gs[0]['wk']
        # previews: Sunday's on Saturday from 8 AM ET; other days 10 hours before the first kickoff; rewritten until kickoff
        if day.weekday() == 6: opens = datetime.datetime.combine(day - datetime.timedelta(days=1), datetime.time(8, 0), ET).astimezone(UTC)
        else: opens = first - datetime.timedelta(hours=10)
        pre = [g for g in gs if g['state'] == 'pre']
        if opens <= NOW < first and pre:
            aid = f"{SEASON}-w{w}-{dname}-preview"
            made += publish(aid, aid, (write_slate if day.weekday() == 6 else write_game_day)(gs, aid))
        # recaps: once every game that day is final
        if all(g['state'] == 'post' for g in gs) and NOW - max(g['kick'] for g in gs) < datetime.timedelta(days=3):
            aid = f"{SEASON}-w{w}-{dname}-recap"
            if aid not in ARTS: made += publish(aid, aid, write_recap(gs, aid))
    # breaking news
    today = [a for a in ARTS.values() if a.get('kind') == 'breaking' and pdt(a.get('pub')) and NOW - pdt(a['pub']) < datetime.timedelta(hours=24)]
    room = min(MAX_BRK_RUN, MAX_BRK_DAY - len(today)); done = set(); first_run = 'seen' not in OLD; cur = set()
    for e in breaking_events():
        k = f"brk-{e['p']['id']}-{e['kind']}"; cur.add(k)
        if k not in SEEN: SEEN[k] = iso(NOW)
        # only news first seen in the last 6 hours becomes an article (the first run just learns what is already known)
        if first_run or room <= 0 or NOW - pdt(SEEN[k]) > datetime.timedelta(hours=6): continue
        recent = [a for a in ARTS.values() if a.get('key') == k and pdt(a.get('pub')) and NOW - pdt(a['pub']) < datetime.timedelta(days=6)]
        if recent or k in done: continue
        done.add(k); aid = f"{SEASON}-{k}-{NOW.strftime('%m%d')}"
        if publish(aid, k, write_breaking(e['p'], e, aid)): room -= 1; made += 1
    # keep three weeks
    keep = {i: a for i, a in ARTS.items() if pdt(a.get('upd')) and NOW - pdt(a['upd']) < datetime.timedelta(days=KEEP_DAYS)}
    items = sorted(keep.values(), key=lambda a: a['upd'], reverse=True)
    seen = {k: v for k, v in SEEN.items() if k in cur or (pdt(v) and NOW - pdt(v) < datetime.timedelta(days=14))}
    new = {'season': SEASON, 'at': iso(NOW) if made else OLD.get('at', iso(NOW)), 'items': items, 'seen': seen, **({'ai_log': AI_LOG} if AI_LOG else {})}
    if made or len(items) != len(OLD.get('items') or []) or seen != OLD.get('seen') or AI_LOG != (OLD.get('ai_log') or []) or not os.path.exists(OUT):
        json.dump(new, open(OUT, 'w'), separators=(',', ':')); print(f'articles: {made} new or updated, {len(items)} kept')
    else: print('articles: nothing new')


if __name__ == '__main__':
    try: run()
    except Exception:   # never break the live job
        import traceback; traceback.print_exc(); print('articles: skipped this run'); sys.exit(0)
