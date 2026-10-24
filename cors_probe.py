"""One-off check, part 2: the shape of ESPN's league API for a public league (structure and counts only: no team, member
or player names are saved), so the site can import ESPN leagues by link."""
import json, urllib.request, urllib.error
ORIGIN = 'https://bengasparian.github.io'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36'
LID = 24481082
def get(q):
    url = f'https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/segments/0/leagues/{LID}?{q}'
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Origin': ORIGIN, 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r: return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e: return e.code, None
def shape(v, depth=0):
    if depth > 5: return type(v).__name__
    if isinstance(v, dict): return {k: shape(x, depth + 1) for k, x in list(v.items())[:40]}
    if isinstance(v, list): return [shape(v[0], depth + 1), f'len={len(v)}'] if v else []
    if isinstance(v, str): return 'str'
    return type(v).__name__
R = {}
for q in ('view=mTeam&view=mRoster&view=mSettings', 'view=mRoster', 'view=mRoster&scoringPeriodId=7', 'view=mTeam', 'view=mSettings'):
    code, j = get(q); out = {'status': code}
    if isinstance(j, dict):
        T = j.get('teams') or []
        out['top_keys'] = list(j)
        out['teams'] = len(T); out['entries_per_team'] = [len(((t.get('roster') or {}).get('entries') or [])) for t in T]
        out['team_shape'] = shape(T[0]) if T else None
        out['members_shape'] = shape((j.get('members') or [None])[0]) if j.get('members') else None
        st = j.get('settings') or {}
        out['settings_keys'] = list(st)
        out['scoring_items'] = [(x.get('statId'), x.get('points')) for x in (st.get('scoringSettings') or {}).get('scoringItems', [])][:40]
        out['lineup_slots'] = (st.get('rosterSettings') or {}).get('lineupSlotCounts')
        out['size'] = st.get('size'); out['scoringPeriodId'] = j.get('scoringPeriodId')
    R[q] = out
json.dump(R, open('stats/espn_league_shape.json', 'w'), indent=1); print(json.dumps(R, indent=1)[:8000])
