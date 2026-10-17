"""Refresh live.json with ESPN's public scoreboard and box scores (run every few minutes on game days), and ESPN's injury
list for every game not yet started (the data build and the page use it for each player's status).
The page loads ESPN directly every 30 seconds when it can; live.json is the backup copy it falls back to."""
import json, os, time, urllib.request, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
EMAP = {"WSH": "WAS", "LAR": "LA"}
BASE = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/"

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "gridiron-fantasy"})
    with urllib.request.urlopen(req, timeout=12) as r: return json.load(r)

def ab(c): k = ((c.get("team") or {}).get("abbreviation")) or "?"; return EMAP.get(k, k)

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
                    "last": (sit.get("lastPlay") or {}).get("text")})
    return out

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
    return {"players": list(players.values()), "cats": cats, "ts": ts}

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

def media(sm):
    """Pictures for a game, as ESPN publishes them with its coverage: the recap photo, story photos, video thumbnails,
    and the stadium photo. Only links are kept; the pictures stay on ESPN's servers."""
    out, seen = [], set()
    def add(u, h, l, k):
        if u and str(u).startswith("https://") and u not in seen: seen.add(u); out.append({"u": u, "h": h or "", "l": l or "", "k": k})
    art = sm.get("article") or {}
    add(next((i.get("url") for i in art.get("images") or [] if i.get("url")), None), art.get("headline"), ((art.get("links") or {}).get("web") or {}).get("href"), "Recap")
    for a in (sm.get("news") or {}).get("articles") or []:
        add(next((i.get("url") for i in a.get("images") or [] if i.get("url")), None), a.get("headline"), ((a.get("links") or {}).get("web") or {}).get("href"), "Story")
    for v in sm.get("videos") or []: add(v.get("thumbnail"), v.get("headline"), (((v.get("links") or {}).get("web")) or {}).get("href"), "Video")
    vi = [i for i in (((sm.get("gameInfo") or {}).get("venue") or {}).get("images") or []) if i.get("href")]
    day = next((i for i in vi if "interior" not in i["href"]), vi[0] if vi else None)
    return {"ph": out[:8], "venue": day["href"] if day else None}

if __name__ == "__main__":
    old = json.load(open("live.json")) if os.path.exists("live.json") else {}
    try:
        sb = get(BASE + "scoreboard"); G = games(sb); B = {k: v for k, v in (old.get("box") or {}).items() if isinstance(v, dict)}
        M = {k: v for k, v in (old.get("media") or {}).items() if isinstance(v, dict)}; V = dict(old.get("venues") or {})
        I = {k: v for k, v in (old.get("inj") or {}).items() if isinstance(v, dict)}
        for g in G:
            if g.get("vid") and not g.get("neutral"): V[g["home"]] = str(g["vid"])
        # every game not yet started is re-read each run for its injury list (the official report and ESPN's updates)
        need = [g for g in G if g["state"] in ("in", "pre") or (g["state"] == "post" and not B.get(g["id"])) or g["id"] not in M
                or (g["state"] == "post" and recent(g) and not any(p.get("k") in ("Recap", "Story") for p in M[g["id"]].get("ph") or []))]
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=4) as ex:   # box scores 4 at a time, and never more than ~2 minutes in total
            futs = {ex.submit(get, BASE + "summary?event=" + str(g["id"])): g["id"] for g in need}
            for f in as_completed(futs, timeout=150):
                try:
                    sm = f.result(); gid = futs[f]; M[gid] = media(sm); stt = next(g for g in G if g["id"] == gid)["state"]
                    if stt != "pre": B[gid] = box(sm)
                    else:
                        try:
                            iv = injuries(sm)
                            if iv or "injuries" in sm: I[gid] = {"t": iv, "w": (sb.get("week") or {}).get("number")}
                        except Exception as e: print("injury list unavailable for", gid, e)
                except Exception as e: print("box score unavailable for", futs[f], e)
                if time.time() - t0 > 140: print("time budget reached; keeping earlier box scores for the rest"); break
        cur = lambda d: {k: v for k, v in d.items() if any(str(x["id"]) == str(k) for x in G)}
        new = {"src": "ESPN, refreshed every few minutes", "week": (sb.get("week") or {}).get("number"), "games": G, "box": cur(B), "media": cur(M), "venues": V, "inj": cur(I)}
        if {k: old.get(k) for k in ("games", "box", "media", "venues", "inj")} != {k: new[k] for k in ("games", "box", "media", "venues", "inj")}:
            new["at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
            json.dump(new, open("live.json", "w"), separators=(",", ":")); print("live.json updated:", sum(g["state"] == "in" for g in G), "games live")
        else: print("no change")
    except Exception as e:
        print("ESPN unavailable, keeping the previous live.json:", e)
