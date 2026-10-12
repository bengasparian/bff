#!/usr/bin/env python3
"""NFL and fantasy news from many sources -> news.json. Run every 10 minutes by the scores workflow.

Every item keeps its source, a link to the original article, and its publish time, so the page can credit and link it.
Only a headline and a short teaser (at most 160 characters) are stored; readers follow the link for the full story.
Sources were checked by hand before being added; any source that fails is skipped and its last good items are kept,
so one broken feed never stops the update. Items older than 7 days drop off.

Also collected: Sleeper's public "trending adds" (players fantasy managers are adding most in the last 24 hours).
Each item is tagged with the players it names, a category (injury, transaction, fantasy, betting, news), and, for
clear statements such as "ruled out" or "expected to miss time", a status the prop lines use to pull a line.
"""
import json, os, re, html, datetime, urllib.request, email.utils
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

UA = {'User-Agent': 'BFF-fantasy-football/1.0 (+https://github.com)'}
SOURCES = [   # name, feed, homepage, kind, keep(link, title)
    ('ESPN', 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/news?limit=50', 'https://www.espn.com/nfl/', 'espn', None),
    ('CBS Sports', 'https://www.cbssports.com/rss/headlines/nfl/', 'https://www.cbssports.com/nfl/', 'rss', lambda u, t: '/nfl/' in u),
    ('Yahoo Sports', 'https://sports.yahoo.com/nfl/rss.xml', 'https://sports.yahoo.com/nfl/', 'rss', None),
    ('Pro Football Talk', 'https://www.nbcsports.com/profootballtalk.rss', 'https://www.nbcsports.com/nfl/profootballtalk', 'rss', None),
    ('RotoWire', 'https://www.rotowire.com/rss/news.php?sport=NFL', 'https://www.rotowire.com/football/', 'rss', None),
    ('RotoBaller', 'https://www.rotoballer.com/category/nfl/feed', 'https://www.rotoballer.com/nfl', 'rss', None),
    ('PFF', 'https://www.pff.com/feed', 'https://www.pff.com/nfl', 'rss', None),
    ('Sharp Football Analysis', 'https://www.sharpfootballanalysis.com/feed/', 'https://www.sharpfootballanalysis.com/', 'rss', None),
]
TRENDING = 'https://api.sleeper.app/v1/players/nfl/trending/add?lookback_hours=24&limit=25'
COLLEGE = re.compile(r'\b(college football|cfb|ncaa|heisman|big ten|big 12|\bsec\b|\bacc\b|cfp|recruit|bowl game|draft prospect|mock draft 20\d\d|top 25)\b', re.I)
OUT_RE = re.compile(r"(ruled out|won't play|will not play|will miss|expected to miss|out for (the )?(season|year|week|game|\w+ weeks?)|out indefinitely|season[- ]ending|"
                    r"placed on (ir|injured reserve)|lands on (ir|injured reserve)|to (ir|injured reserve)\b|inactive for|doubtful (for|to play))", re.I)
OK_RE = re.compile(r"(cleared to play|will play|activated from|returns? to practice|full participant|no injury designation|good to go|expected to play)", re.I)
INJ_RE = re.compile(r'(injur|hamstring|ankle|knee|concussion|questionable|doubtful|ruled out|\bIR\b|out for|miss time|limited|did not practice|MRI|surgery|sprain|strain|torn)', re.I)
TX_RE = re.compile(r'\b(sign(s|ed|ing)?|release[sd]?|waive[sd]?|trade[sd]?|acquire[sd]?|claim(s|ed)?|practice squad|re-sign|extension|contract|cut[s]?)\b', re.I)
FAN_RE = re.compile(r'(fantasy|waiver|start[/ ]sit|sleeper|rankings|\bPPR\b|DFS|dynasty|pickups?|buy low|sell high|breakout)', re.I)
BET_RE = re.compile(r'(\bodds\b|betting|\bbets?\b|\bprops?\b|parlay|spread|over/under|picks? against)', re.I)

def get(url, timeout=12):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r: return r.read()
def clean(s, n=None):
    s = html.unescape(re.sub(r'<[^>]+>', ' ', s or '')); s = re.sub(r'\s+', ' ', s).strip()
    if n and len(s) > n: s = s[:n].rsplit(' ', 1)[0].rstrip(',.;:') + '…'
    return s
def when(s):
    try:
        d = email.utils.parsedate_to_datetime(s)
        if d.tzinfo is None: d = d.replace(tzinfo=datetime.timezone.utc)
        return d.astimezone(datetime.timezone.utc).isoformat(timespec='seconds')
    except Exception:
        try: return datetime.datetime.fromisoformat(s.replace('Z', '+00:00')).astimezone(datetime.timezone.utc).isoformat(timespec='seconds')
        except Exception: return None

def rss(name, url, keep):
    root = ET.fromstring(get(url)); out = []
    for it in root.iter('item'):
        t = clean(it.findtext('title')); u = (it.findtext('link') or '').strip()
        if not t or not u.startswith('http'): continue
        if keep and not keep(u, t): continue
        out.append({'h': t, 'u': u, 'd': when(it.findtext('pubDate') or ''), 'x': clean(it.findtext('description'), 160), 's': name})
    return out
def espn(name, url, keep):
    j = json.loads(get(url)); out = []
    for a in j.get('articles') or []:
        h = clean(a.get('headline')); u = (((a.get('links') or {}).get('web') or {}).get('href'))
        if not h or not u: continue
        ath = [str(c.get('athleteId') or (c.get('athlete') or {}).get('id')) for c in a.get('categories') or [] if c.get('type') == 'athlete' and (c.get('athleteId') or (c.get('athlete') or {}).get('id'))]
        out.append({'h': h, 'u': u, 'd': when(a.get('published') or a.get('lastModified') or ''), 'x': clean(a.get('description'), 160), 's': name, 'a': ath, 'prem': bool(a.get('premium'))})
    return out

def player_index():
    """Names to match in headlines (from the data job's inputs); only full names, so 'Wilson' alone never matches."""
    try: P = json.load(open('bet_inputs.json'))['players']
    except Exception:
        try: P = json.load(open('ff_data.json'))['players']
        except Exception: return [], {}
    idx = []
    for p in P:
        n = re.sub(r'\s+(jr|sr|ii|iii|iv|v)\.?$', '', (p.get('n') or '').strip(), flags=re.I)   # 'Deebo Samuel Sr.' also matches 'Deebo Samuel'
        if len(n.split()) < 2: continue
        pat = re.escape(n).replace(r'\.', r'\.?').replace("\\'", "['’]?")
        idx.append((re.compile(r'(?<![\w])' + pat + r"(?:\s+(?:Jr|Sr|II|III|IV|V)\.?)?(?![\w])", re.I), p['id']))
    sid = {str(p['sid']): p['id'] for p in P if p.get('sid')}
    return idx, sid

def tag(it, idx, now):
    txt = it['h'] + ' ' + (it.get('x') or '')
    it['p'] = sorted({pid for rx, pid in idx if rx.search(it['h'])} or {pid for rx, pid in idx if rx.search(txt)})[:4]
    h = it['h']
    it['c'] = 'inj' if INJ_RE.search(h) else 'tx' if TX_RE.search(h) else 'bet' if BET_RE.search(h) else 'fan' if FAN_RE.search(h) else 'news'
    if it['p'] and OUT_RE.search(h): it['st'] = 'out'
    elif it['p'] and OK_RE.search(h): it['st'] = 'ok'
    return it

def build_news(write=True):
    now = datetime.datetime.now(datetime.timezone.utc); stamp = now.isoformat(timespec='seconds')
    old = {}
    try: old = json.load(open('news.json'))
    except Exception: pass
    idx, sid = player_index()
    def run(src):
        name, url, home, kind, keep = src
        try:
            items = (espn if kind == 'espn' else rss)(name, url, keep)
            return name, items, None
        except Exception as e: return name, None, str(e)[:120]
    with ThreadPoolExecutor(max_workers=6) as ex: results = list(ex.map(run, SOURCES))
    seen_first = {it['u']: it.get('d') for it in old.get('items') or []}
    items, status = [], []
    for (name, url, home, kind, keep), (_, got, err) in zip(SOURCES, results):
        status.append({'s': name, 'home': home, 'ok': got is not None, 'n': len(got or []), 'err': err})
        for it in got or []:
            if COLLEGE.search(it['h']) or '/college' in it['u'] or 'ncaa' in it['u']: continue
            it['d'] = it['d'] or seen_first.get(it['u']) or stamp      # feeds without a date: first time we saw it
            items.append(it)
    # keep earlier items (short feeds only show their latest few), drop anything older than 7 days, de-duplicate
    cutoff = (now - datetime.timedelta(days=7)).isoformat()
    key = lambda it: re.sub(r'[^a-z0-9]', '', it['h'].lower())[:70]
    merged, keys, urls = [], set(), set()
    for it in sorted(items + (old.get('items') or []), key=lambda x: x.get('d') or '', reverse=True):
        k = key(it)
        if it['u'] in urls or k in keys or (it.get('d') or '') < cutoff: continue
        urls.add(it['u']); keys.add(k); merged.append(tag(it, idx, now))
    merged = merged[:400]
    trend = old.get('trend') or []
    try:
        T = json.loads(get(TRENDING)); trend = [{'pid': sid[str(x['player_id'])], 'n': int(x['count'])} for x in T if str(x.get('player_id')) in sid][:20]
        status.append({'s': 'Sleeper (trending adds)', 'home': 'https://sleeper.com', 'ok': True, 'n': len(trend), 'err': None})
    except Exception as e:
        status.append({'s': 'Sleeper (trending adds)', 'home': 'https://sleeper.com', 'ok': False, 'n': 0, 'err': str(e)[:120]})
    out = {'at': stamp, 'src': status, 'items': merged, 'trend': trend}
    changed = (merged != old.get('items')) or (trend != old.get('trend'))
    if write and changed: json.dump(out, open('news.json', 'w'), separators=(',', ':'))
    return out, changed

def fetch_headlines():   # kept for the data job (ff_produce.py)
    return build_news(write=True)[0]['items']

if __name__ == '__main__':
    try:
        out, changed = build_news()
        ok = [s['s'] + f" ({s['n']})" for s in out['src'] if s['ok']]; bad = [s['s'] for s in out['src'] if not s['ok']]
        print(f"news: {len(out['items'])} items from {len(ok)} sources: {', '.join(ok)}" + (f" | unavailable this run: {', '.join(bad)}" if bad else '') + ('' if changed else ' (no change)'))
    except Exception as e:
        print('news update failed, keeping the previous news.json:', e)
