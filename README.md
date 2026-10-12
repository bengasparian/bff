# BFF · Ben's Fantasy Football: auto-updating version

This folder turns BFF (Ben's Fantasy Football) into a free website that keeps itself up to date. Two GitHub
workflows do the work, no API keys needed:

| Workflow | File | When | What it does |
|---|---|---|---|
| **Update Gridiron Fantasy** | `update.yml` | every 3 hours (23 minutes past) | downloads the latest NFL data, rebuilds every projection, ranking, trend and prop line, collects news, optionally syncs your Sleeper league, checks the page, saves it |
| **Live scores, news and lines** | `scores.yml` | every 10 minutes | live scores and box scores, news from every source, prop lines moved by the latest odds and news, parlay picks; only saves when something changed |

Both share one queue, so they never save at the same moment. Before anything is saved, `check_page.py` checks the
page (data readable, enough players, no script errors) and the live files; anything broken is put back to the
last good version, so the published site never breaks.

## What's on the site
- **Home:** this week at a glance in a stadium-lit hero, a rotating spotlight (top play, best pick, game of the
  week, breaking news, trending adds, your lineup), every tool one tap away, the week's games, and dashboard cards.
  Every card links to its full section (for example Buy low · sell high opens Fantasy Help → Trends → Buy & sell).
- **Live:** scores, down and distance, and a full-screen game center for every game (outlook, win chances,
  injuries, expected top performers, box score). Past and future weeks too.
- **News:** stories from ESPN, CBS Sports, Yahoo Sports, Pro Football Talk, RotoWire, RotoBaller, PFF and Sharp
  Football Analysis, plus official injury reports, depth-chart changes and roster moves (nflverse) and Sleeper
  trending adds. Every story names its publisher and links to the original; only headlines and short teasers are kept.
- **Players:** rankings, a start/sit cheat sheet, and a card for every player with projections, usage, game logs,
  schedule, news and this week's prop lines.
- **My League:** link a Sleeper, ESPN or Yahoo league for your best lineup, waiver targets, trade ideas and a
  matchup simulator.
- **Draft:** a mock draft against AI teams with different strategies, graded at the end.
- **Fantasy Help:** Trends (best bets, buy & sell, usage, proof), Matchups (this week, defenses, schedules), draft
  guide, waivers & trades, the trade analyzer with **Find trades**, betting, and tips.
- **Learn:** how everything works, accuracy, and **Sources & citations** for every number and story.
- **Updates bar:** a broadcast-style bar at the bottom of every page cycles through updates that fit the page
  (Home: everything; Live: scores and top performers; News: news; Fantasy Help: fantasy and betting updates;
  My League: your players). Pause, step through, or hide it.
- **Phones:** an app-style layout with a bottom tab bar and a More sheet. Add it to your home screen for an app
  icon (on iPhone it then opens full screen).

## Predicted prop lines (`ff_lines.py`)
- Built the way books build them, from **opportunity**: expected targets, carries or pass attempts (recent full
  games count most, last season fills in early) times the player's efficiency, adjusted for the Vegas team total
  and the defense. Partial games (injury exits) are marked down, and teammates' injuries add volume.
- Lines **move during the week**: every 10 minutes the scores workflow re-reads the current ESPN odds and the news.
  A line moves when the Vegas total changes, when the 3-hourly data update brings new injury reports or roles,
  and is pulled when a player is reported out. Each line keeps its opening number and the reason for every move.
- Tested honestly: tuned on 2024, then checked on every 2025 game using only what was known before kickoff.
  Overs hit 44-50% for every stat (a fair line is about 50%); typical miss 65 passing yards, 26 rushing yards,
  1.7 catches, 22 receiving yards. Picks at 55% or more won 59.6% of 1,080 (passing TDs 58%, passing yards 60%,
  receptions 60%, rushing yards 54%). Receiving-yard picks won only 46%, so they are never made. Real app lines
  can be sharper than ours, so expect real results to run lower.
- `parlay_update.py` builds the best 2-, 3- and 5-pick parlays from tested picks only (one leg per game, no
  questionable players), locks them at the week's first kickoff, and grades them from official box scores.
- For entertainment, 21+ where legal. Gambling problem? Call or text 1-800-GAMBLER.

## One-time setup (about 10 minutes)
1. Create a free account at github.com and sign in.
2. Click **New repository**, name it `gridiron-fantasy`, choose **Public**, and create it.
3. Click **uploading an existing file** and drag in everything from this folder **except** the hidden `.github`
   folder and `.nojekyll` file. Click **Commit changes**. Then **Add file > Create new file**, name it `.nojekyll`,
   leave it empty, and commit (it tells GitHub to publish the files as they are).
4. Add the two workflow files: **Add file > Create new file**, name it `.github/workflows/update.yml`, paste in the
   contents of `update.yml` from this kit, and commit. Repeat for `.github/workflows/scores.yml`.
   (Already set up? Replace both files with these new versions.)
5. **Settings > Actions > General > Workflow permissions:** choose **Read and write permissions**, then **Save**.
6. **Settings > Pages:** set the branch to `main` and `/ (root)`, then **Save**. Your site will be at
   `https://YOUR-USERNAME.github.io/gridiron-fantasy/`.
7. Test it: **Actions** tab > **Update Gridiron Fantasy** > **Run workflow**. A run takes about 5 to 10 minutes
   because it downloads several seasons of play-by-play data. Then run **Live scores, news and lines** once.

## Sync your Sleeper league automatically (optional)
1. Find your league ID: the long number in your league's web address on sleeper.com.
2. **Settings > Secrets and variables > Actions > Variables tab > New repository variable**. Name it
   `SLEEPER_LEAGUE_ID` and paste the number.
3. Run the data workflow again. Sleeper league data is public and needs no password. ESPN and Yahoo need a login,
   so for those leagues use the paste-in import on the page.

## Good to know
- GitHub Pages has a soft limit of 10 site builds per hour, which is why the live workflow runs every 10 minutes
  and saves only when something changed. GitHub can also delay scheduled runs at busy times.
- On your own site, scores also load straight from ESPN in your browser every 30 seconds during games, and news,
  lines and parlays refresh every few minutes without reloading the page.
- Player photos and team logos load from ESPN's image servers on your own site (the camera button turns photos
  off). They belong to the NFL, ESPN and the teams. The claude.ai copy shows jerseys in team colors instead.
- A free GitHub Pages site is public. A synced Sleeper league's team names and rosters are visible to anyone with
  the link. Leagues you import by hand are saved only in your own browser.
- GitHub pauses scheduled workflows in a public repository after 60 days with no activity. The workflows' own
  saves count as activity during the season; if updates stop in the offseason, re-enable them in **Actions**.
- The trained models (`DTR.parquet`, `D25.parquet`, `ff_build2.py`) are set up for the 2026 season. Before 2027,
  ask Claude to retrain them with 2026 included.
- If a run fails, open it in the **Actions** tab to see the error. The usual cause is a data file that has not been
  published yet. The site keeps the last good version until the next run succeeds.

## Sources
- [nflverse](https://github.com/nflverse/nflverse-data): play-by-play, weekly stats, snap counts, rosters, depth
  charts, injury reports; [nfldata](https://github.com/nflverse/nfldata) schedules with Vegas spreads and totals.
- [DynastyProcess](https://github.com/dynastyprocess/data): player ID crosswalk and market trade values (built on
  FantasyPros dynasty rankings, so young players are valued more than in a one-season league; BFF blends them with
  its own projections).
- ESPN public scoreboard, game and news data; Sleeper trending adds; the news publishers listed above.
- BFF is not affiliated with the NFL, its teams, or any source listed here.
