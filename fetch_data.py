"""Download the public data the pipeline needs (nflverse, DynastyProcess, FantasyPros consensus) into this folder.
The consensus rankings are optional: if they cannot be downloaded the site falls back to its own projections."""
import sys, urllib.request
SEASON = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
B = "https://github.com/nflverse/nflverse-data/releases/download/"
DP = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/"
files = {}
for y in range(2021, SEASON + 1):
    files[f"pbp_{y}.parquet"] = B + f"pbp/play_by_play_{y}.parquet"
    files[f"stats_player_week_{y}.parquet"] = B + f"stats_player/stats_player_week_{y}.parquet"
    files[f"snap_counts_{y}.parquet"] = B + f"snap_counts/snap_counts_{y}.parquet"
files["db_playerids.csv"] = DP + "db_playerids.csv"              # player ID crosswalk
optional = {
    "values.csv": DP + "values-players.csv",                    # dynasty market (only used to keep injured stars in the player pool)
    "db_fpecr_latest.csv": DP + "db_fpecr_latest.csv",          # FantasyPros consensus rankings, rest of season
    "fp_latest_weekly.csv": DP + "fp_latest_weekly.csv",        # FantasyPros consensus rankings, this week
}
def get(name, url):
    with urllib.request.urlopen(url, timeout=300) as r, open(name, "wb") as f:
        f.write(r.read())
    print("downloaded", name)
for name, url in files.items(): get(name, url)
for name, url in optional.items():
    try: get(name, url)
    except Exception as e: print(f"could not download {name} ({e}); continuing without it")
