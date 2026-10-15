# BFF · Ben's Fantasy Football: auto-updating version

This folder turns BFF (Ben's Fantasy Football) into a free website that keeps itself up to date all year, with nothing
to edit from one season to the next. Two GitHub workflows do the work, no API keys needed:

| Workflow | File | When | What it does |
|---|---|---|---|
| **Update Gridiron Fantasy** | `update.yml` | every 3 hours (23 minutes past) | downloads the latest NFL data, rebuilds every projection, ranking, trend and prop line, saves and grades the weekly calls, collects news, optionally syncs your Sleeper league, checks the page, saves it |
| **Live scores, news and lines** | `scores.yml` | every 10 minutes | live scores and box scores, news from every source, prop lines moved by the latest odds and news, parlay picks; only saves when something changed |

Both share one queue, so they never save at the same moment. Before anything is saved, `check_page.py` checks the
page (data readable, enough players, no script errors) and the live files; anything broken is put back to the
last good version, so the published site never breaks.

## What's on the site
- **Home:** the first section cycles through the week's games: live games first, then finals, with the top fantasy
  performer of each. It stays on that week until 12:00 AM Eastern on the Wednesday after its last game, then switches to
  next week's upcoming games (kickoff, spread, total, win chances, players to watch). Below: every tool one tap away,
  the week's games, and dashboard sections (swipeable on phones). Every card links to its full section.
- **Live:** just the games and scores, each with its photo: the featured game on top, then every game of the week.
  **Fantasy points** (your lineup live, top performers, leaders by position) is one tap away on the same tab. Tap a game
  for its full-screen game center (outlook, win chances, injuries, top performers, box score). Past and future weeks too.
- **News:** a sports-site layout with a top story, lead stories with pictures, a trending list (players covered by
  the most outlets in the last day), most-added players on Sleeper and the official injury report. Stories come from
  ESPN, CBS Sports, Yahoo Sports, Pro Football Talk, RotoWire, RotoBaller, PFF and Sharp Football Analysis. Headlines
  stay exactly as each publisher wrote them and link to the original; the labels (Breaking, Injury alert, Waiver
  wire...), outlet counts and "fantasy impact" notes are BFF's. Pictures load from each publisher's own feed image.
- **Players:** this week's rankings, **Trade values** (the rest-of-season BFF value chart, tiered, for your league
  settings), a start/sit cheat sheet, and a card for every player with projections, usage, game logs, schedule, news
  and this week's prop lines.
- **My League:** link a Sleeper, ESPN or Yahoo league for your best lineup, waiver targets, trade ideas and a
  matchup simulator.
- **Draft:** a mock draft against AI teams with different strategies, graded at the end.
- **Fantasy Help:** **Weekly calls** (below), Trends (best bets, buy & sell, usage, proof), Matchups (this week,
  defenses, schedules), draft guide, waivers & trades, the trade analyzer with **Find trades**, betting, and tips.
- **Weekly calls:** every week's must starts, must sits, buy lows and sell highs, saved by `calls_update.py`. Start and
  sit calls keep updating until that player's game kicks off, then lock; buy and sell calls lock at the week's first
  kickoff. After the games each call is graded with official stats: a must start hits when he finishes as a starter
  (top 12 QB, 24 RB, 30 WR, 12 TE in PPR), a must sit hits when he finishes outside those spots, and buy lows and sell
  highs are graded on the player's next 3 games. A season scorecard shows the hit rates next to honest yardsticks
  (starting the best season averages; all usual starters). Weeks 2-5 of 2026 were rebuilt with `calls_backfill.py`
  from the same model using only pre-game information and are labeled "rebuilt"; everything from week 6 on is saved live.
- **Favorites:** star any player to track him in Players → Favorites (this week's outlook, live points, status, props,
  news) and on Home. Saved in each visitor's own browser.
- **BFF Coach:** the chat button on every page (in the header on phones) answers start/sit, trade, waiver, prop and "how does BFF work"
  questions instantly with the site's own projections, trade values and lines, and declines questions that are not
  about football or the site. On your GitHub site it runs on BFF's own rules (no AI service or key needed). On the
  claude.ai copy it can also ask Claude, on the visitor's own Claude account with their permission, for open-ended
  scenarios; Claude gets the same BFF numbers through the page's tools.
- **Learn:** how everything works, accuracy, and **Sources & citations** for every number and story.
- **Updates bar:** on wider screens, a broadcast-style bar at the bottom of every page cycles through updates that fit the page
  (Home: everything; Live: scores and top performers; News: news; Fantasy Help: fantasy and betting updates;
  My League: your players). Pause, step through, or hide it.
- **Accounts:** visitors can create an account (they must agree to the Terms of Use and Privacy Policy) to save their
  linked leagues, team, favorite players and settings and get them back on any device. See **Accounts** below.
- **Phones:** an app-style layout: a compact header (search, BFF Coach, account), each tab's sections pinned under it,
  one compact top story under the sections, a bottom tab bar and a More sheet, and tighter player rows. The floating
  updates bar and chat button are left to bigger screens. Add it to your home screen for an app icon (on iPhone it then
  opens full screen).

## Projections
- A model trained on the four seasons before the latest completed one and tested on every game of that season (in 2026:
  trained on 2021-2024, tested on 2025). It retrains every run, and each finished season joins the window on its own.
  Inputs: usage-based expected points, scoring this season blended with last season, the defense, the Vegas team total,
  home/away and injured teammates.
- **Recent games count more.** Every input also has a recent-form version (each game counts half as much as the one 2.5
  games after it), plus how his snap, target and carry shares are trending against his season average; rookies start
  from what players drafted in their range usually score. A second model aims at the rest of the season (each player's
  next six games), and later weeks use the average of the two. 2023-2025 backtest, out of sample: rest-of-season rank
  accuracy 0.390 -> 0.415, average miss 3.54 -> 3.45 points a game; next game 4.57 -> 4.53 and 0.622 -> 0.630. How much
  recent games count is learned from the data each run, not fixed by hand.
- **Expert consensus blend:** next week's projection blends the model (35%) with the FantasyPros weekly expert
  consensus (65%), mapped onto our own projection scale (the k-th ranked RB gets our k-th best RB projection). On every
  2023-2025 week, out of sample, rank accuracy went from 0.419 to 0.467 and the average miss from 5.56 to 5.43 points.
  The page's **Why?** breakdown shows the consensus adjustment as its own bar.
- **Half PPR and standard:** a player's catches are removed in proportion to how much the projection regressed his
  scoring (tested on 2023-2025: lower error than removing his full catches per game).

## BFF value: trade values and rankings
- For every week from now through week 17, BFF value adds up the starting-lineup points a player should give you over
  the best player at his position who would **not** start in your league (your lineup slots times your league size,
  with flex and superflex filled by projection). Each week counts `0.98 x 0.985^weeks-away` (the chance he is still
  active) times the expected points above that level, allowing for weekly ups and downs, so fringe players keep a little
  upside value. Byes, injured reserve and "out" this week come from the weekly projections.
- It is blended with the **FantasyPros rest-of-season expert consensus** (60% in PPR, 50% half PPR, 40% standard;
  a little more for running backs and for players with two games or fewer this season, where the consensus proved more
  reliable), mapped onto the same curve, then scaled 0-100 (the top players sit near 100).
- **Games since the consensus count right away.** The consensus file updates on Fridays, so Sunday's and Monday's games
  are not in it yet. BFF adds half of the change in its own value from the games played since the consensus was taken
  (2023-2025: value accuracy R² 0.297 -> 0.305, lopsided trades called for the side that really added more 68.5% ->
  70.2%, points above replacement about the same). Example, week 6 of 2026: Jaylen Warren, slow start then 20.6, 15.6
  and 36.8 points, rose from RB16 to RB12 by BFF value while the week-old consensus still had him RB19.
- **Injured reserve:** nothing before his estimated return, then (chance he plays) x (value if he plays), using what
  really happened to such players in 2023-2025: about 1 in 10 played the first week after the estimated return, 1 in 3
  by the fourth week, about half later, and 53% never played again that season. (The old rule counted 75% of every week.)
- Packages: the best player counts fully, then 80%, 60%, 45% (measured: adding two players to a team added
  best + 0.82 x second). A trade is **fair** only when BFF value is within 10%, the consensus within 30% and our
  projections alone within 50%; labels run Even / Slightly favors / Favors / Heavily favors.
- **Backtest, 2023-2025** (14 checkpoints, weeks 4-12, using only what was known at the time; truth = real
  starting-lineup points each player added in simulated 12-team leagues, and real points above a starter-level
  replacement): value accuracy R² 0.22 -> 0.30 and 0.18 -> 0.26; more accurate at 13 of 14
  checkpoints; "fair" calls that the expert consensus saw as 2x lopsided fell from 41% to 9% (0% with the
  consensus check). The old formula used a dynasty market, which overrated young players for a one-season league.
- The same value drives the Trade values chart, BFF rank on player cards, Find trades, the trade analyzer, the mock
  draft board (AI teams also follow the consensus), the draft guide, waiver targets and BFF Coach.

## Trade analyzer and waivers
- **Trade analyzer** (Fantasy Help, and "Analyze in depth" on every offer in My League): a photo card for each player
  (BFF value, points a game, next 4 weeks, playoff weeks 15-17, bye, injury, usage signal, boom/bust), the package math,
  the three fairness checks, your starting lineup's change week by week with next-4, rest-of-season and playoff totals,
  the other team's change, the roster spots each side must open or can fill (drops and best free agents), startable
  depth by position, and the single additions that would make an unfair offer fair.
- **Waivers:** every target shows its BFF value, the value of the player you would drop, and a FAAB guide based on the
  lineup points he adds the rest of the season (30+ points: 25-40% of your budget; 15-30: 12-25%; 8-15: 5-12%;
  3-8: 1-5%; less: a minimum bid). Targets need a real role, and without a linked league "free" means rostered in under
  half of ESPN and Yahoo leagues.

## Look and pictures
- Every tab reads like the News tab: a cover story on the tab's own artwork with picture headlines beside it, a headline
  rail on wide screens (headlines under the page on smaller ones), and Top stories on Home.
- **News that fits the tab:** every headline gets a relevance score for each tab (your players on My League; top
  players on Players; start/sit, waivers and betting on Fantasy Help; rookies and drafts on Draft; analytics on Learn;
  this week's games on Live), less a point for each day of age. Covers, side stories and rails use it, and each real
  story photo leads one tab only.
- **Readable text on every picture:** text on a photo sits on a dark scrim sized to the text block. When the picture
  can be measured, its brightness behind the text sets the scrim (strong on a white photo, light on a dark one);
  otherwise BFF assumes the brightest possible photo, so white text keeps at least 4.5:1 contrast either way. Text on
  team colors switches to dark ink where white would be hard to read (Steelers gold, Raiders silver, Seahawks green).
- **Real pictures** on your own site: story photos, ESPN headshots everywhere a player is listed, team logos, photo
  cards on the Trade values chart and in the trade analyzer, and the player-card News tab with each story's picture.
  A player without an ESPN photo gets his jersey in team colors. Pages on claude.ai cannot load outside pictures, so
  that copy shows the tab artwork, jerseys and team colors.
- **Game photos:** every Live game card opens with a photo band and both team logos: the home stadium before kickoff,
  a photo from ESPN's coverage once it starts, the recap photo after the final. The game center puts that photo behind
  the score (no separate photo section). `live_update.py` saves each game's photo links and stadium ids in `live.json`
  (links only), so the photos show even when the page can't reach ESPN directly. The camera button turns outside
  pictures off.

## Accounts (optional; about 10 minutes, free)
Without this the site works exactly as before: everything a visitor links or stars is saved in their own browser.
With it, the account button (top right) lets visitors create an account and get their leagues, team, favorites and
settings back on any device. Creating one requires ticking a box agreeing to the **Terms of Use** and **Privacy Policy**
(both open from the account panel and the footer). Accounts are stored in a free Google Firebase project that you own:
1. Go to [console.firebase.google.com](https://console.firebase.google.com), **Create a project** (any name; Google
   Analytics is not needed).
2. **Security > Authentication > Get started > Sign-in method:** enable **Email/password**, then **Save**.
3. **Databases & Storage > Firestore > Create database:** pick a location, choose **production mode**, create it. Open
   its **Rules** tab, replace everything with the contents of `firestore.rules` from this kit, and **Publish**. (These
   rules let each signed-in person read, save and delete only their own data.)
4. **Project settings** (gear icon) **> General > Your apps > Web app (</>)**: register an app (any nickname, no
   hosting needed) and copy the `firebaseConfig` snippet it shows.
5. In GitHub: **Settings > Secrets and variables > Actions > Variables > New repository variable**, name it
   `BFF_FIREBASE` and paste the snippet. Optional variables: `BFF_TERMS_STATE` (the state whose law governs the terms;
   California if not set) and `BFF_CONTACT` (an email address or link where people can reach you about their data).
6. Run **Update Gridiron Fantasy** once. The account button now offers **Create account** and **Sign in**.

The Firebase web config is not a secret (it is meant to be in web pages); the Firestore rules are what protect the
data. The free plan allows 50,000 reads and 20,000 writes a day, far more than a personal site needs. People can delete
their account and its data from the account panel. On the claude.ai copy, the visitor's Claude sign-in is the account
and the data is saved with the page itself, private to each person. The Terms of Use and Privacy Policy are a
plain-language starting point, not legal advice: have a lawyer review them if the site grows, and note that no terms
can stop every lawsuit; they limit liability, require individual arbitration and rule out class actions where the law
allows.

## Runs by itself all year
- **Seasons roll over on their own.** `fetch_data.py` reads the NFL schedule to decide the season: in progress, about
  to start, or (after the last regular-season game) the next one. The model always learns from the five latest completed
  seasons and tests on the most recent, so each finished season joins on its own; nothing is tied to a year.
- **Offseason:** once a regular season ends, the site switches to the next season: rankings, trade values and the mock
  draft are built from last season's data, rookies and players who changed teams come in through the rosters and the
  consensus top 300, and Live says when the schedule usually arrives (May). When the schedule is published, week 1
  projections, opponents, byes and prop lines appear automatically, and live scores start with the first game.
- **New players** join from rosters, depth charts, the consensus top 300 and weekly stats; nobody keeps a list.
- **Health report:** after every data run `health.py` writes `status.json` (which steps worked, the season, the last
  good build). It changes at least once a day, which also keeps GitHub from pausing the scheduled jobs (GitHub pauses
  them after 60 days without activity in a public repository).
- **Safe by default:** tested library versions are pinned in `requirements.txt` (the newest versions install if those
  ever stop installing); each run checks the page before saving and keeps the last good version if anything fails;
  missing or late data files are skipped and picked up on the next run; GitHub emails you if a run fails.
- Feature tables for past seasons are cached between runs (`.cache`), so a run takes a few minutes.

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

## Updating an existing site to this version
Upload (replace) these files: `template.html`, `app.css`, `index.html`, `ff_build2.py`, `ff_produce.py`,
`fetch_data.py`, `assemble.py`, `ff_lines.py`, `parlay_update.py`, `ff_news.py`, `news_update.py`, `live_update.py`,
`health.py`, `requirements.txt`, `firestore.rules`, `.gitignore`, `README.md`, and both workflow files in
`.github/workflows/` (`update.yml`, `scores.yml`). Leave your `*_history.json`, `lines.json`, `parlays.json` and
`bet_inputs.json` alone; your workflows keep those up to date. `DTR.parquet` and `D25.parquet` are no longer used and
can be deleted. Then run **Update Gridiron Fantasy** once (the first run builds the feature tables, about 5 extra minutes).

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
8. Optional: switch on **Accounts** (above) and **Sleeper sync** (below).

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
- Player photos, team logos and news pictures load from ESPN's and the publishers' servers on your own site (the
  camera button turns them off). They belong to the NFL, ESPN, the teams and the publishers. The claude.ai copy shows
  team-color graphics instead.
- A free GitHub Pages site is public. A synced Sleeper league's team names and rosters are visible to anyone with
  the link. Leagues you import by hand are saved only in your own browser.
- GitHub pauses scheduled workflows in a public repository after 60 days with no activity; the daily health report
  keeps the repository active. If updates ever stop, open **Actions** and re-enable the workflows.
- If a run fails, open it in the **Actions** tab to see the error. The usual cause is a data file that has not been
  published yet. The site keeps the last good version until the next run succeeds.

## Sources
- [nflverse](https://github.com/nflverse/nflverse-data): play-by-play, weekly stats, snap counts, rosters, depth
  charts, injury reports; [nfldata](https://github.com/nflverse/nfldata) schedules with Vegas spreads and totals.
- [FantasyPros](https://www.fantasypros.com) expert consensus rankings (weekly and rest of season, PPR) and roster
  percentages, mirrored by [DynastyProcess](https://github.com/dynastyprocess/data), which also supplies the player ID
  crosswalk. If they cannot be downloaded, the site uses its own projections alone.
- ESPN public scoreboard, game and news data; Sleeper trending adds; the news publishers listed above.
- BFF is not affiliated with the NFL, its teams, or any source listed here.
