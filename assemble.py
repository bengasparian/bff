"""Combine the template, styles, and data into index.html (the published page).

Accounts (optional): paste your Firebase web app config (the whole `const firebaseConfig = {...}` snippet is fine) into
a GitHub repository variable named BFF_FIREBASE, or into a file named accounts.json. Optional variables BFF_TERMS_STATE
(the state whose law governs the Terms of Use, default California) and BFF_CONTACT (how people reach you about their
data, e.g. an email address or a link). Nothing here is secret: Firebase web keys are meant to be public, and the
Firestore rules in firestore.rules are what protect each person's data.
"""
import os, sys, re, json
if not os.path.exists("ff_data.json"):
    print("No new data this run (for example, the regular season is over); keeping the current page."); sys.exit(0)


def accounts():
    raw = os.environ.get("BFF_FIREBASE", "")
    cfg = {}
    if os.path.exists("accounts.json"):
        try: cfg = json.load(open("accounts.json"))
        except Exception as e: print("accounts.json could not be read:", e)
        raw = raw or json.dumps(cfg.get("firebase", cfg))
    key = re.search(r'apiKey["\']?\s*[:=]\s*["\']([A-Za-z0-9_\-]{20,})["\']', raw)
    pid = re.search(r'projectId["\']?\s*[:=]\s*["\']([a-z0-9\-]{4,})["\']', raw)
    out = {}
    if key and pid: out["firebase"] = {"apiKey": key.group(1), "projectId": pid.group(1)}
    elif raw.strip(): print("BFF_FIREBASE is set but apiKey/projectId were not found in it; accounts stay off")
    law = os.environ.get("BFF_TERMS_STATE") or cfg.get("law"); contact = os.environ.get("BFF_CONTACT") or cfg.get("contact")
    if law: out["law"] = str(law)[:40]
    if contact: out["contact"] = str(contact)[:120]
    return out


t = open("template.html").read()
assert t.count("__CSS__") == 1 and t.count("__DATA__") == 1
D = json.load(open("ff_data.json"))
A = accounts()
if A: D["auth"] = A
# BFF Originals (articles.py): the latest ones ride along in the page, for copies that cannot load articles.json
if os.path.exists("articles.json"):
    try:
        AR = json.load(open("articles.json")); D["articles"] = {"at": AR.get("at"), "items": [{k: v for k, v in a.items() if k not in ("digest", "sig", "key")} for a in AR.get("items", [])[:30]]}
    except Exception as e: print("articles.json could not be read:", e)
# ESPN's injury lists for games not yet started (live.json), so the page can lay the newest status over the data build
if os.path.exists("live.json"):
    try:
        LV = json.load(open("live.json")); GS = {str(g.get("id")): g for g in LV.get("games") or []}
        D["liveinj"] = {k: v for k, v in (LV.get("inj") or {}).items() if (GS.get(str(k)) or {}).get("state") == "pre" and isinstance(v, dict)}
    except Exception as e: print("live.json injuries skipped:", e)
# Super Bowl and conference championship results for BFF Coach (from the NFL schedule fetch_data.py downloads)
if os.path.exists("games.csv"):
    try:
        import csv
        D["post"] = [[int(g["season"]), g["game_type"], *((g["home_team"], g["away_team"], int(g["home_score"]), int(g["away_score"])) if int(g["home_score"]) >= int(g["away_score"]) else (g["away_team"], g["home_team"], int(g["away_score"]), int(g["home_score"]))), g.get("stadium") or "", g.get("gameday") or ""]
                     for g in csv.DictReader(open("games.csv", newline="")) if g.get("game_type") in ("SB", "CON") and g.get("home_score") not in ("", "NA", None) and g.get("away_score") not in ("", "NA", None)]
    except Exception as e: print("postseason results skipped:", e)
print("accounts:", "on (Firebase project " + A["firebase"]["projectId"] + ")" if A.get("firebase") else "off (set BFF_FIREBASE to turn them on)")
data = json.dumps(D, separators=(",", ":"), allow_nan=False).replace("</", "<\\/")
open("index.html", "w").write(t.replace("__CSS__", open("app.css").read()).replace("__DATA__", data))
print("index.html written")
