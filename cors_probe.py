"""One-off check: can a web page (another site, e.g. bengasparian.github.io) read ESPN's and Yahoo's fantasy league APIs
straight from the visitor's browser? A browser allows it only when the response carries Access-Control-Allow-Origin for that
site. Records status codes and CORS headers (no league data is kept beyond whether rosters came back)."""
import json, urllib.request, urllib.error
ORIGIN = 'https://bengasparian.github.io'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36'
def probe(url, method='GET', extra=None):
    h = {'User-Agent': UA, 'Origin': ORIGIN, 'Accept': 'application/json'}; h.update(extra or {})
    req = urllib.request.Request(url, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r: code, hd, body = r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e: code, hd, body = e.code, dict(e.headers), e.read()
    except Exception as e: return {'url': url, 'method': method, 'error': str(e)}
    cors = {k: v for k, v in hd.items() if k.lower().startswith('access-control')}
    out = {'url': url, 'method': method, 'status': code, 'cors': cors, 'bytes': len(body), 'ctype': hd.get('Content-Type')}
    try:
        j = json.loads(body); out['teams'] = len(j.get('teams') or []); out['rosters'] = sum(len(((t.get('roster') or {}).get('entries') or [])) for t in (j.get('teams') or []))
        out['keys'] = list(j)[:12] if isinstance(j, dict) else None
    except Exception: out['head'] = body[:160].decode('utf-8', 'replace')
    return out
R = []
for host in ('lm-api-reads.fantasy.espn.com', 'fantasy.espn.com'):
    for lid in (1, 1245, 336358, 1086064, 24481082, 98765432):
        R.append(probe(f'https://{host}/apis/v3/games/ffl/seasons/2026/segments/0/leagues/{lid}?view=mTeam&view=mRoster&view=mSettings'))
R.append(probe('https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/segments/0/leagues/1245?view=mRoster', 'OPTIONS', {'Access-Control-Request-Method': 'GET'}))
R.append(probe('https://fantasysports.yahooapis.com/fantasy/v2/league/nfl.l.12345/teams?format=json'))
R.append(probe('https://fantasysports.yahooapis.com/fantasy/v2/league/nfl.l.12345/teams?format=json', 'OPTIONS', {'Access-Control-Request-Method': 'GET', 'Access-Control-Request-Headers': 'authorization'}))
R.append(probe('https://api.sleeper.app/v1/league/1/rosters'))
import os; os.makedirs('stats', exist_ok=True)
json.dump(R, open('stats/cors_probe.json', 'w'), indent=1); print(json.dumps(R, indent=1)[:6000])
