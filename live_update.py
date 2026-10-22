"""Refresh live.json with ESPN's public scoreboard and box scores (run every few minutes on game days), and ESPN's injury
list for every game not yet started, re-read more often as kickoff nears (the data build and the page use it for each
player's status).
The page loads ESPN directly every 30 seconds when it can; live.json is the backup copy it falls back to."""
import json, os, re, time, urllib.request, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
EMAP = {"WSH": "WAS", "LAR": "LA"}
BASE = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/"

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "gridiron-fantasy"})
    with urllib.request.urlopen(req, timeout=12) as r: return json.load(r)

def ab(c): k = ((c.get("team") or {}).get("abbreviation")) or "?"; return EMAP.get(k, k)

def _num(v):
    try: return int(float(v))
    except (TypeError, ValueError): return 0

def games(sb):
    out = []
    for e in sb.get("events") or []:
        c = (e.get("competitions") or [{}])[0]; C = c.get("competitors") or []
        h = next((x for x in C if x.get("homeAway") == "home"), {}); a = next((x for x in C if x.get("homeAway") == "away"), {})
        s = e.get("status") or c.get("status") or {}; t = s.get("type") or {}; sit = c.get("situation") or {}; o = (c.get("odds") or [{}])[0]
        pp = any(k in (t.get("name") or "") for k in ("POSTPONED", "CANCELED", "SUSPENDED"))
        pre = pp or t.get("state") == "pre"; poss = None if pp else sit.get("possession")
        if len(C) < 2: continue
        out.append({"id": e.get("id"), "home": ab(h), "away": ab(a), "hs": None if pre else int(h.get("score") or 0), "as": None if pre else int(a.get("score") or 0),
                    "state": "pre" if pp else (t.get("state") or "pre"), "detail": (t.get("description") or "Postponed") if pp else (t.get("shortDetail") or t.get("detail") or ""), "clock": s.get("displayClock"), "q": s.get("period"),
                    "poss": (ab(h) if poss == h.get("id") else ab(a)) if poss else None, "dd": sit.get("shortDownDistanceText") or sit.get("downDistanceText"),
                    "ddl": sit.get("downDistanceText"), "down": sit.get("down"), "dist": sit.get("distance"), "yl": sit.get("yardLine"), "ptxt": sit.get("possessionText"),
                    "rz": bool(sit.get("isRedZone")), "kick": e.get("date"), "venue": (c.get("venue") or {}).get("fullName"),
                    "vid": (c.get("venue") or {}).get("id"), "neutral": bool(c.get("neutralSite")),
                    "rimg": ((((c.get("headlines") or [{}])[0]).get("video") or [{}])[0]).get("thumbnail"), "rhl": ((c.get("headlines") or [{}])[0]).get("shortLinkText"),
                    "tv": (((c.get("broadcasts") or [{}])[0]).get("names") or [None])[0], "odds": o.get("details"), "ou": o.get("overUnder"),
                    "last": (sit.get("lastPlay") or {}).get("text"), **extra(sit, h, a, pre, t.get("state")),
                    "ls": [[_num(x.get("value")) for x in (a.get("linescores") or [])], [_num(x.get("value")) for x in (h.get("linescores") or [])]] if not pre else None})
    return out

def extra(sit, h, a, pre, state):
    """what ESPN's scoreboard says about a game in progress: timeouts left, its win probability after the last play, the
    drive so far and where it started, and the last play's type and team (the page's live game tracker)"""
    if pre: return {}
    lp = sit.get("lastPlay") or {}; pr = lp.get("probability") or {}; dv = lp.get("drive") or {}; lt = (lp.get("team") or {}).get("id")
    num = lambda v: v if isinstance(v, (int, float)) and not isinstance(v, bool) else None
    live = state == "in"; w = num(pr.get("homeWinPercentage"))
    return {"toA": num(sit.get("awayTimeouts")) if live else None, "toH": num(sit.get("homeTimeouts")) if live else None,
            "wp": max(0.0, min(1.0, w)) if live and w is not None else None, "drv": (dv.get("description") or None) if live else None,
            "dst": ((dv.get("start") or {}).get("text") or None) if live else None, "lty": (lp.get("type") or {}).get("text"),
            "ltm": (ab(h) if lt == h.get("id") else ab(a) if lt == a.get("id") else None) if lt else None}

def pbp(sm):
    """the play-by-play the page shows for a live or finished game: the current drive's plays (or the last drive's), the
    drives, the scoring plays and ESPN's win probability through the game (at most 121 points)"""
    dr = sm.get("drives") or {}; num = lambda v: v if isinstance(v, (int, float)) and not isinstance(v, bool) else None
    def tm(d): k = (d.get("team") or {}).get("abbreviation"); return EMAP.get(k, k) if k else None
    def play(p): return {"t": str(p.get("text") or ""), "c": (p.get("clock") or {}).get("displayValue") or "", "q": (p.get("period") or {}).get("number"),
                         "ty": (p.get("type") or {}).get("text") or "", "sc": bool(p.get("scoringPlay")), "y": num(p.get("statYardage")),
                         "dd": (p.get("start") or {}).get("downDistanceText") or ""}
    def drv(d): st = d.get("start") or {}; return {"tm": tm(d), "r": d.get("displayResult") or d.get("result") or "", "d": d.get("description") or "",
                                                  "st": st.get("text") or "", "q": (st.get("period") or {}).get("number"), "c": (st.get("clock") or {}).get("displayValue") or "",
                                                  "sc": bool(d.get("isScore"))}
    cur = dr.get("current") or {}; prev = dr.get("previous") or []
    c = dict(drv(cur), plays=[play(p) for p in (cur.get("plays") or [])[-12:]]) if cur.get("plays") else None
    sp = [{"q": (p.get("period") or {}).get("number"), "c": (p.get("clock") or {}).get("displayValue") or "", "tm": tm(p),
           "ty": (p.get("type") or {}).get("text") or (p.get("scoringType") or {}).get("displayName") or "", "t": str(p.get("text") or ""),
           "as": num(p.get("awayScore")), "hs": num(p.get("homeScore"))} for p in sm.get("scoringPlays") or []]
    wp = [w for w in (num((x or {}).get("homeWinPercentage")) for x in sm.get("winprobability") or []) if w is not None and 0 <= w <= 1]
    if len(wp) > 121: k = (len(wp) - 1) / 120; wp = [wp[round(i * k)] for i in range(121)]
    return {"cur": c, "prev": [drv(d) for d in prev[-16:]], "last": [play(p) for p in ((prev[-1].get("plays") or [])[-6:] if prev else [])],
            "sp": sp, "wp": [round(v, 3) for v in wp]}

def box(sm):
    """Official box score: every stat category per team (as ESPN lists it), team stats, plus normalized lines for fantasy points."""
    players, cats, ts = {}, {}, {}
    for tp in ((sm.get("boxscore") or {}).get("players") or []):
        tm = EMAP.get((tp.get("team") or {}).get("abbreviation"), (tp.get("team") or {}).get("abbreviation"))
        for cat in tp.get("statistics") or []:
            keys = cat.get("keys") or []; lab = [str(x).upper() for x in (cat.get("labels") or [])]; n = cat.get("name")
            rows = []
            for at in cat.get("athletes") or []:
                nm = (at.get("athlete") or {}).get("displayName"); st = at.get("stats") or []
                if not nm: continue
                rows.append([nm] + [str(x) for x in st])
                r = players.setdefault((nm, tm), {"n": nm, "t": tm})
                def gv(k, l):
                    i = keys.index(k) if k in keys else (lab.index(l) if l in lab else -1)
                    return st[i] if 0 <= i < len(st) else None
                num = lambda v: float(v) if v not in (None, "", "--") and str(v).replace(".", "", 1).replace("-", "", 1).isdigit() else 0.0
                if n == "passing":
                    ca = str(gv("completions/passingAttempts", "C/ATT") or "0/0").split("/")
                    r.update(pc=int(num(ca[0])), pa=int(num(ca[1]) if len(ca) > 1 else 0), py=num(gv("passingYards", "YDS")), ptd=num(gv("passingTouchdowns", "TD")), int=num(gv("interceptions", "INT")))
                elif n == "rushing": r.update(ra=num(gv("rushingAttempts", "CAR")), ry=num(gv("rushingYards", "YDS")), rtd=num(gv("rushingTouchdowns", "TD")))
                elif n == "receiving": r.update(rec=num(gv("receptions", "REC")), ty=num(gv("receivingYards", "YDS")), rectd=num(gv("receivingTouchdowns", "TD")), tg=num(gv("receivingTargets", "TGTS")))
                elif n == "fumbles": r.update(fl=num(gv("fumblesLost", "LOST")))
            if rows: cats.setdefault(tm, []).append({"n": n, "t": cat.get("text") or (n or "").title(), "l": cat.get("labels") or [], "r": rows, "tot": [str(x) for x in (cat.get("totals") or [])]})
    for tt in ((sm.get("boxscore") or {}).get("teams") or []):
        tm = EMAP.get((tt.get("team") or {}).get("abbreviation"), (tt.get("team") or {}).get("abbreviation"))
        ts[tm] = [[s.get("label") or s.get("name"), s.get("displayValue")] for s in (tt.get("statistics") or []) if s.get("displayValue") is not None]
    # scoring plays, for the game story in recaps: [quarter, clock, team, type, text, away score, home score]
    sp = []
    for x in sm.get("scoringPlays") or []:
        try:
            tm = EMAP.get((x.get("team") or {}).get("abbreviation"), (x.get("team") or {}).get("abbreviation"))
            sp.append([(x.get("period") or {}).get("number"), (x.get("clock") or {}).get("displayValue"), tm, ((x.get("scoringType") or {}).get("abbreviation") or (x.get("type") or {}).get("abbreviation") or ""),
                       str(x.get("text") or "")[:160], x.get("awayScore"), x.get("homeScore")])
        except Exception: continue
    return {"players": list(players.values()), "cats": cats, "ts": ts, "sp": sp}

FPOS = {"QB", "RB", "WR", "TE", "FB"}
def injuries(sm):
    """ESPN's injury list for each team in a game (fantasy positions): [espn id, name, position, status, injury, estimated return, date]"""
    out = {}
    for blk in sm.get("injuries") or []:
        k = (blk.get("team") or {}).get("abbreviation"); tm = EMAP.get(k, k)
        if not tm: continue
        L = []
        for it in blk.get("injuries") or []:
            a = it.get("athlete") or {}; pos = (a.get("position") or {}).get("abbreviation") or ""
            if pos not in FPOS or not a.get("displayName"): continue
            d = it.get("details") or {}
            st = it.get("status") or (it.get("type") or {}).get("description") or ""
            L.append([str(a.get("id") or ""), a.get("displayName"), pos, str(st), str(d.get("type") or ""), str(d.get("returnDate") or "")[:10], str(it.get("date") or "")[:10]])
        out[tm] = sorted(L)
    return out

def recent(g, hours=36):
    """kicked off within the last day and a half (recap photos are published after the game)"""
    try: return (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(str(g.get("kick")).replace("Z", "+00:00"))).total_seconds() < hours * 3600
    except Exception: return False

def _pkey(u):
    """the same picture in another size or with a query string counts as the same picture"""
    return re.sub(r"_\d{2,4}x\d{2,4}(_[\d-]+)?(?=\.\w+$)", "", str(u or "").split("?")[0].split("#")[0]).lower()

def _when(s):
    try: return datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception: return None

def media(sm):
    """Pictures that belong to this game, as ESPN publishes them: the recap photo (final games), stories ESPN tags with
    this game (or with one of its teams, naming a team and published after kickoff), highlight videos naming a team and
    published after kickoff, and the stadium photo. The summary also carries league-wide news, which is left out.
    Only links are kept; the pictures stay on ESPN's servers."""
    out, seen = [], set()
    def add(u, h, l, k):
        if u and str(u).startswith("https://") and _pkey(u) not in seen: seen.add(_pkey(u)); out.append({"u": u, "h": h or "", "l": l or "", "k": k})
    comp = ((sm.get("header") or {}).get("competitions") or [{}])[0]
    ev = str((sm.get("header") or {}).get("id") or comp.get("id") or ""); kick = _when(comp.get("date"))
    teams = [str((c.get("team") or {}).get("id") or c.get("id") or "") for c in comp.get("competitors") or []]
    words = set()
    for c in comp.get("competitors") or []:
        t = c.get("team") or {}
        for w in (t.get("displayName"), t.get("name"), t.get("shortDisplayName"), t.get("location"), t.get("nickname")):
            if w and len(str(w)) >= 4: words.add(str(w).lower())
    names = lambda txt: any(w in str(txt or "").lower() for w in words)
    after = lambda a: bool(kick and _when(a.get("published") or a.get("originalPublishDate") or a.get("lastModified")) and _when(a.get("published") or a.get("originalPublishDate") or a.get("lastModified")) >= kick)
    def own(a):
        C = a.get("categories") or []
        if ev and any(str(c.get("eventId") or "") == ev or (c.get("type") == "event" and str(c.get("id") or "") == ev) for c in C if isinstance(c, dict)): return True
        tagged = any(c.get("type") == "team" and str(c.get("teamId") or (c.get("team") or {}).get("id") or "") in teams for c in C if isinstance(c, dict))
        return tagged and names(a.get("headline")) and after(a)
    state = ((comp.get("status") or {}).get("type") or {}).get("state")
    art = sm.get("article") or {}
    if state == "post" and (own(art) or names(art.get("headline"))):
        add(next((i.get("url") for i in art.get("images") or [] if i.get("url")), None), art.get("headline"), ((art.get("links") or {}).get("web") or {}).get("href"), "Recap")
    for a in ((sm.get("news") or {}).get("articles") or []) if state != "pre" else []:
        if own(a): add(next((i.get("url") for i in a.get("images") or [] if i.get("url")), None), a.get("headline"), ((a.get("links") or {}).get("web") or {}).get("href"), "Story")
    for v in (sm.get("videos") or []) if state != "pre" else []:
        if names(v.get("headline")) and after(v): add(v.get("thumbnail"), v.get("headline"), (((v.get("links") or {}).get("web")) or {}).get("href"), "Video")
    vi = [i for i in (((sm.get("gameInfo") or {}).get("venue") or {}).get("images") or []) if i.get("href")]
    day = next((i for i in vi if "interior" not in i["href"]), vi[0] if vi else None)
    return {"ph": out[:8], "venue": day["href"] if day else None}

def pre_due(g, M, I, now=None):
    """a game not yet started: is its summary (injury list, preview pictures) due for a re-read this run?"""
    if g["id"] not in M or g["id"] not in I: return True
    now = now or time.time(); slot = int(now // 600)          # this run's 10-minute slot
    try: h = (datetime.datetime.fromisoformat(str(g["kick"]).replace("Z", "+00:00")).timestamp() - now) / 3600
    except (TypeError, ValueError): return True
    return h <= 4 or (h <= 48 and slot % 3 == 0) or slot % 12 == 0

def drop_shared(M):
    """a picture that turns up for two games is not either game's picture"""
    cnt = {}
    for m in M.values():
        for k in {_pkey(p["u"]) for p in m.get("ph") or []}: cnt[k] = cnt.get(k, 0) + 1
    return {g: dict(m, ph=[p for p in m.get("ph") or [] if cnt.get(_pkey(p["u"]), 0) < 2]) for g, m in M.items()}

if __name__ == "__main__":
    old = json.load(open("live.json")) if os.path.exists("live.json") else {}
    try:
        sb = get(BASE + "scoreboard"); G = games(sb); B = {k: v for k, v in (old.get("box") or {}).items() if isinstance(v, dict)}
        M = {k: v for k, v in (old.get("media") or {}).items() if isinstance(v, dict)}; V = dict(old.get("venues") or {})
        I = {k: v for k, v in (old.get("inj") or {}).items() if isinstance(v, dict)}
        PB = {k: v for k, v in (old.get("pbp") or {}).items() if isinstance(v, dict)}
        for g in G:
            if g.get("vid") and not g.get("neutral"): V[g["home"]] = str(g["vid"])
        # games not yet started are re-read for their injury lists on a schedule that tightens toward kickoff: every run in
        # the last 4 hours (inactives, late scratches), every half hour within two days (practice reports), every two
        # hours before that. Live games and finals still missing a box score or recap are read every run.
        need = [g for g in G if g["state"] == "in" or (g["state"] == "pre" and pre_due(g, M, I)) or (g["state"] == "post" and (not B.get(g["id"]) or g["id"] not in PB))
                or g["id"] not in M or (g["state"] == "post" and recent(g) and not any(p.get("k") in ("Recap", "Story") for p in M[g["id"]].get("ph") or []))]
        print(f"reading {len(need)} of {len(G)} game summaries")
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=4) as ex:   # box scores 4 at a time, and never more than ~2 minutes in total
            futs = {ex.submit(get, BASE + "summary?event=" + str(g["id"])): g["id"] for g in need}
            for f in as_completed(futs, timeout=150):
                try:
                    sm = f.result(); gid = futs[f]; M[gid] = media(sm); stt = next(g for g in G if g["id"] == gid)["state"]
                    if stt != "pre":
                        B[gid] = box(sm)
                        try: PB[gid] = pbp(sm)
                        except Exception as e: print("play-by-play unavailable for", gid, e)
                    else:
                        try:
                            iv = injuries(sm)
                            if iv or "injuries" in sm: I[gid] = {"t": iv, "w": (sb.get("week") or {}).get("number")}
                        except Exception as e: print("injury list unavailable for", gid, e)
                except Exception as e: print("box score unavailable for", futs[f], e)
                if time.time() - t0 > 140: print("time budget reached; keeping earlier box scores for the rest"); break
        cur = lambda d: {k: v for k, v in d.items() if any(str(x["id"]) == str(k) for x in G)}
        cnt = {}
        for v in cur(M).values():
            for u in {p["u"] for p in v.get("ph") or []}: cnt[u] = cnt.get(u, 0) + 1
        for v in M.values(): v["ph"] = [p for p in v.get("ph") or [] if cnt.get(p["u"], 0) <= 1]
        new = {"src": "ESPN, refreshed every few minutes", "week": (sb.get("week") or {}).get("number"), "games": G, "box": cur(B), "media": drop_shared(cur(M)), "venues": V, "inj": cur(I), "pbp": cur(PB)}
        if {k: old.get(k) for k in ("games", "box", "media", "venues", "inj", "pbp")} != {k: new[k] for k in ("games", "box", "media", "venues", "inj", "pbp")}:
            new["at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
            json.dump(new, open("live.json", "w"), separators=(",", ":")); print("live.json updated:", sum(g["state"] == "in" for g in G), "games live")
        else: print("no change")
    except Exception as e:
        print("ESPN unavailable, keeping the previous live.json:", e)
