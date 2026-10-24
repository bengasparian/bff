"""Training questions for BFF Brain's intent model. Names, teams, positions and numbers are replaced by tokens before the
model sees them (the page does the same with its own player and team lists), so it learns how people ask, not who.
Tokens: PLAYER, TEAM, POSN (a position word), NUM."""
import random

R = random.Random(7)
P, P2, P3, T, T2, POS, N = 'PLAYER', 'PLAYER', 'PLAYER', 'TEAM', 'TEAM', 'POSN', 'NUM'
WEEK = ['', ' this week', ' week NUM', ' tonight', ' on sunday', ' this weekend', ' today', ' in week NUM']
WHO = ['should i', 'do i', 'would you', 'should we', 'do you think i should', 'is it smarter to', 'better to']

T_ = {
 'start_sit': [
  '{P} or {P2}', '{P} or {P2}?', 'should i start {P} or {P2}{W}', 'start {P} or {P2}', 'who should i start {P} or {P2}', '{P} vs {P2}{W}',
  'who do i play {P} or {P2}', 'who should i flex {P} {P2} or {P3}', 'flex {P} or {P2}', 'which one {P} or {P2}', 'sit {P} or {P2}',
  'who is the better start {P} or {P2}', 'i need one of {P} and {P2}', '{P} {P2} or {P3} at flex', 'who scores more {P} or {P2}',
  'should i bench {P} for {P2}', 'start {P} over {P2}?', 'is {P} a better play than {P2}', 'who has the higher ceiling {P} or {P2}',
  'safer floor {P} or {P2}', 'who should i put in my flex', 'i have {P} and {P2} for one spot', 'who to start at POSN {P} or {P2}',
  'need upside: {P} or {P2}', 'which POSN should i start {P} or {P2}', 'play {P} or {P2} this week', 'gimme {P} or {P2}', '{P} or {P2} lol',
  'compare {P} and {P2}', 'who wins {P} or {P2} in fantasy', 'start sit {P} {P2}', 'start/sit {P} vs {P2}', 'who would you rather start {P} or {P2}',
  'between {P} and {P2} who do i go with', 'tough call {P} or {P2}', 'do i roll with {P} or {P2}'],
 'player': ['{P} outlook vs the TEAM', '{P} against the TEAM this week', 'how does {P} look against TEAM', 'should i start {P} against TEAM', 'is {P} worth playing', 'how many pts will {P} get', 'what kind of game will {P} have', 'is {P} going to ball out', 'gonna be a big week for {P}?', 'is {P} a smash play', 'should {P} be in my lineup', 'is {P} a top 10 play', 'what are you projecting for {P}', 'is {P} a flex play', 
  'how many points will {P} score{W}', 'should i start {P}{W}', 'is {P} a good start{W}', '{P} outlook', 'what about {P}', 'how is {P} looking{W}',
  'is {P} worth starting', 'can i trust {P}{W}', '{P} projection', 'what do you think of {P}', 'is {P} startable', 'thoughts on {P}', 'tell me about {P}',
  'is {P} a must start', 'should i sit {P}{W}', '{P} this week', 'how good is {P}', 'is {P} good', 'whats {P} projected for', 'what is {P} projected',
  'expectations for {P}{W}', 'boom or bust {P}', 'is {P} a sleeper', 'should i play {P}', 'is {P} a top POSN', 'where does {P} rank{W}', 'what rank is {P}',
  'is {P} going to have a good game', 'will {P} do well against TEAM', 'how does {P} matchup look', 'good matchup for {P}?', '{P} ceiling', '{P} floor',
  'start em or sit em {P}', 'confidence in {P}{W}', 'is {P} an rb1', 'is {P} a wr2'],
 'trade': [
  '{P} for {P2}', 'should i trade {P} for {P2}', 'trade {P} for {P2} and {P3}', 'is {P} for {P2} fair', 'would you do {P} for {P2}', 'i give {P} and get {P2}',
  'they offered me {P} for {P2}', 'accept {P} for {P2}?', 'is this trade fair {P} for {P2}', 'who wins this trade {P} for {P2}', 'trade {P} and {P2} for {P3}',
  'someone offered {P} for my {P2}', 'swap {P} for {P2}', 'should i accept a trade {P} for {P2}', 'my {P} for his {P2}', 'getting {P} giving {P2}',
  'do i make this deal {P} for {P2}', '{P} {P2} for {P3} who wins', 'is {P} for {P2} a fleece', 'is trading {P} for {P2} smart', 'rate this trade {P} for {P2}',
  'trade offer: {P} for {P2}', 'i get {P}, they get {P2}', 'thoughts on {P} for {P2} trade', 'counter offer {P} plus {P2} for {P3}'],
 'trade_value': ['how much value does {P} have', 'should i shop {P}', 'is {P} overvalued', 'is {P} undervalued', 'what would it take to get {P}', 'is {P} a good trade target', 'who should i target in trades', 'what is {P} market value', 
  'what is {P} worth', 'what can i get for {P}', 'trade value of {P}', 'who can i trade {P} for', 'should i trade {P}', 'is {P} a sell high', 'is {P} a buy low',
  'trade ideas for {P}', 'what should i ask for {P}', 'how much is {P} worth in a trade', 'find me a trade for {P}', 'sell {P}?', 'buy {P}?',
  'what is {P} trade value', 'fair trade for {P}', 'who should i trade {P} to get', 'should i buy low on {P}', 'should i sell {P} now'],
 'keep_drop': ['can i let {P} go', 'time to move on from {P}?', 'do i need to keep {P}', 'should {P} stay on my roster', 'is {P} cuttable', 'is {P} droppable now', 'worth holding {P}?', 'send {P} to waivers?', 'should i move on from {P}', 'is {P} safe to drop', 'do i keep {P} or cut him', 
  'should i drop {P}', 'can i drop {P}', 'is {P} droppable', 'keep or drop {P}', 'cut {P}?', 'should i hold {P}', 'is {P} worth a roster spot',
  'drop {P} for {P2}', 'drop {P} or {P2}', 'who should i drop {P} or {P2}', 'is it time to cut {P}', 'should i keep {P} on my bench',
  'should i hold {P} through his injury', 'is {P} done', 'release {P}?', 'should i stash {P}', 'is {P} worth stashing'],
 'waiver': [
  'who should i pick up', 'best waiver pickups{W}', 'who should i add', 'waiver wire POSN', 'best POSN on waivers', 'who should i grab off waivers',
  'top free agents', 'any good pickups', 'who is worth a waiver claim', 'best adds this week', 'streaming POSN{W}', 'who should i stream at POSN',
  'waiver targets', 'how much faab for {P}', 'should i pick up {P}', 'is {P} worth an add', 'should i claim {P}', 'add {P}?', 'pickup {P} or {P2}',
  'who are the best available players', 'deep league waiver adds', 'who should i bid on', 'who to add at POSN', 'need a POSN off waivers'],
 'rankings': [
  'top NUM POSN{W}', 'best POSN{W}', 'rank the POSN{W}', 'POSN rankings', 'who are the top POSN rest of season', 'best POSN for the rest of the season',
  'ros POSN rankings', 'top POSN this year', 'show me the POSN rankings', 'who is the best POSN', 'POSN1s this week', 'rank my POSN', 'top 10 POSN',
  'who is the number one POSN', 'best fantasy POSN right now', 'top POSN in ppr', 'rankings for week NUM', 'what are the rankings', 'top players this week'],
 'leaders': ['top scoring POSN so far', 'who has been the best POSN this season', 'most fantasy points at POSN this year', 'who is leading the league in yards', 
  'who leads the league in rushing yards', 'most receiving yards this season', 'who has the most touchdowns', 'passing yards leader', 'most receptions',
  'who has the most targets', 'top fantasy scorers this season', 'who has scored the most fantasy points', 'most rushing touchdowns', 'league leaders',
  'who leads the nfl in sacks', 'most passing touchdowns this year', 'who has the most yards', 'leading rusher', 'leading receiver', 'stat leaders',
  'highest scoring POSN this season', 'who is leading in receiving tds', 'most carries', 'most interceptions thrown'],
 'stats': ['what are {P} numbers', '{P} production this year', '{P} stat line', '{P} box score', 'what did {P} put up last week', '{P} fantasy points per game', 'how has {P} been producing', '{P} career stats', 
  'how many yards does {P} have', 'how many touchdowns does {P} have', '{P} stats', 'what are {P} stats this season', 'how did {P} do last week',
  '{P} last game', 'how many points did {P} score last week', '{P} season stats', '{P} game log', 'how many receptions does {P} have',
  'how many carries did {P} get', 'what is {P} target share', 'what is {P} snap count', '{P} snap share', 'how many targets does {P} get',
  '{P} yards per game', 'how is {P} doing this season', '{P} average points', 'what did {P} do against TEAM', 'how many tds did {P} score last game',
  '{P} usage', 'how much is {P} playing', 'is {P} getting the ball'],
 'injury': ['update on {P} ankle', 'whats the update on {P} hamstring', 'is {P} going to suit up', '{P} game time decision?', 'how bad is {P} knee', '{P} concussion update', 'did {P} get hurt', 'what is {P} injury', 
  'is {P} playing{W}', 'is {P} injured', '{P} injury update', 'is {P} out', 'will {P} play{W}', 'is {P} hurt', 'what is wrong with {P}', '{P} status',
  'is {P} questionable', 'when is {P} coming back', 'when does {P} return', 'is {P} on ir', 'how long is {P} out', 'did {P} practice',
  'is {P} active{W}', '{P} injury', 'injury report', 'who is injured{W}', 'who is out{W}', 'any injuries i should know about', 'latest injury news',
  'is {P} going to miss time', 'is {P} healthy', 'is {P} back'],
 'news': [
  'latest news on {P}', 'any news on {P}', 'what happened to {P}', 'news', 'latest nfl news', 'whats new with {P}', 'why did {P} score so little',
  'why is {P} not playing', 'what is going on with {P}', 'any updates', 'breaking news', 'what is the latest', 'whats happening in the nfl',
  'did {P} get traded', 'where did {P} sign', 'is {P} benched', 'why was {P} benched', 'tell me the news about TEAM'],
 'team': [
  'how are the TEAM doing', 'TEAM record', 'TEAM schedule', 'when do the TEAM play', 'who do the TEAM play{W}', 'TEAM next game', 'TEAM depth chart',
  'who is the TEAM quarterback', 'who starts at running back for the TEAM', 'TEAM roster', 'TEAM injuries', 'are the TEAM good', 'TEAM offense',
  'who is the TEAM top receiver', 'TEAM bye week', 'when is the TEAM bye', 'what channel is the TEAM game on', 'TEAM standings', 'TEAM playoff chances',
  'who coaches the TEAM', 'TEAM fantasy outlook', 'best fantasy players on the TEAM'],
 'defense': ['who gives up the most points to POSN', 'which team allows the most fantasy points to POSN', 'is the TEAM d tough on POSN', 'is TEAM soft against POSN', 'worst pass defense', 'worst run defense', 'which defenses are bad against the run', 'who should i stream at defense', 
  'which defense allows the most points to POSN', 'worst defenses against POSN', 'is TEAM a good matchup for POSN', 'TEAM defense vs POSN',
  'easiest matchups for POSN{W}', 'toughest matchups{W}', 'how good is the TEAM defense', 'does TEAM give up a lot to POSN', 'best matchups{W}',
  'strength of schedule for {P}', 'who has the easiest schedule', 'playoff schedule for {P}', 'defense vs position', 'what defense should i stream',
  'best dst{W}', 'which defense should i start'],
 'game': ['who do you like in the TEAM game', 'who you got TEAM or TEAM2', 'your pick for TEAM TEAM2', 'TEAM or TEAM2 who wins', 'what will the score be TEAM TEAM2', 'upset alert TEAM', 
  'who wins TEAM vs TEAM2', 'who will win TEAM at TEAM2', 'TEAM TEAM2 prediction', 'what is the spread for TEAM', 'over under TEAM TEAM2',
  'who is favored TEAM or TEAM2', 'predict the TEAM game', 'final score prediction TEAM TEAM2', 'will the TEAM cover', 'who wins tonight',
  'who wins the game tonight', 'thursday night prediction', 'monday night football prediction', 'what are the odds for TEAM', 'TEAM moneyline',
  'what is the total for TEAM TEAM2', 'will TEAM beat TEAM2', 'who will win the super bowl', 'game predictions{W}', 'pick the winner TEAM TEAM2'],
 'prop': ['{P} to score tonight?', '{P} anytime touchdown odds', '{P} receiving yards over under', 'is the over on {P} good', 
  '{P} over NUM yards', '{P} over or under NUM receiving yards', 'will {P} go over NUM rushing yards', '{P} prop', '{P} props', '{P} o/u NUM',
  'over NUM receptions for {P}', 'should i take {P} under NUM', '{P} passing yards line', 'what is {P} receiving yards line', '{P} over NUM.5',
  'hit the over on {P}', '{P} anytime td', 'will {P} score a touchdown', 'is {P} a good td bet', '{P} receptions prop', 'best props for {P}'],
 'parlay': [
  'build me a parlay', 'NUM leg parlay', 'give me a NUM leg parlay{W}', 'same game parlay TEAM TEAM2', 'sgp for the TEAM game', 'parlay for tonight',
  'best parlay{W}', 'make me a parlay', 'safe parlay', 'longshot parlay', 'parlay with {P} and {P2}', 'three leg parlay', 'parlay picks{W}',
  'best bets{W}', 'what should i bet on', 'best prop bets{W}', 'locks of the week', 'give me some picks'],
 'td': ['who should i bet to score', 'best anytime td bets', 'who will score a td in the TEAM game', 'touchdown scorer picks', 
  'who will score a touchdown{W}', 'anytime td scorers', 'td picks{W}', 'who scores tonight', 'best touchdown bets', 'who is most likely to score a td',
  'first td scorer', 'touchdown predictions{W}', 'who will find the end zone', 'anytime touchdown picks for TEAM TEAM2'],
 'lineup': [
  'set my lineup', 'who should i start on my team', 'optimize my lineup', 'best lineup{W}', 'help me set my lineup', 'who should i start{W}',
  'my lineup', 'is my lineup good', 'who do i start this week', 'what is my optimal lineup', 'start sit for my team', 'fix my lineup'],
 'roster': [
  'my team is {P} {P2} {P3}', 'rate my team {P} {P2} {P3}', 'how good is my team', 'grade my roster', 'what does my team need', 'my roster: {P}, {P2}, {P3}',
  'here is my team {P} {P2} {P3} what should i do', 'trade ideas for my team', 'who should i trade for', 'mock trades for my team', 'give me trade ideas',
  'what trades should i make', 'how can i improve my team', 'is my team a contender', 'what position should i upgrade', 'analyze my team'],
 'calls': ['must start players', 'who are this weeks must starts', 'smash plays{W}', 'who should everyone start{W}', 'players to avoid{W}', 'trap plays{W}', 
  'must starts{W}', 'must sits{W}', 'who are the sleepers{W}', 'sleepers', 'buy low candidates', 'sell high candidates', 'who should i buy low on',
  'who should i sell high', 'busts{W}', 'who to avoid{W}', 'fades{W}', 'weekly calls', 'how accurate are your calls', 'what is your track record',
  'how did bff do last week', 'start em sit em{W}', 'cheat sheet', 'breakout candidates', 'deep sleepers'],
 'site': ['how is your projection made', 'how are your rankings made', 'how do you rank players', 'how is the trade value made', 'what model do you use', 'how do you know who to start', 'what is this website', 
  'how does bff work', 'how do you make projections', 'how is bff value calculated', 'what is bff value', 'how accurate is bff', 'how does the trade analyzer work',
  'how do i link my league', 'how do i connect sleeper', 'how do i change scoring', 'where are the rankings', 'what is the mock draft', 'how do favorites work',
  'where are the articles', 'what are bff originals', 'how does the live tracker work', 'how do i use this site', 'what can you do', 'what can i ask you',
  'help', 'how do i set custom scoring', 'where do your numbers come from', 'are you better than espn', 'why should i trust bff', 'what data do you use',
  'how often do projections update', 'what is the range on the player card', 'what does boom percent mean on the site'],
 'knowledge': ['who has the most career receiving yards', 'who has the most career passing yards', 'all time rushing leader', 'nfl records', 'who holds the single season rushing record', 'how many super bowls have the TEAM won', 'when was the first super bowl', 
  'what is ppr', 'how many points is a safety', 'what is a two point conversion', 'how does overtime work', 'what is a flex', 'what is superflex', 'what is a handcuff',
  'what is faab', 'how long is an nfl game', 'how many teams make the playoffs', 'when is the super bowl', 'who won the last super bowl', 'what is target share',
  'what is epa', 'what is a sack', 'how do downs work', 'what is pass interference', 'what is the red zone', 'what is a bye week', 'what is dynasty',
  'what does questionable mean', 'when is the trade deadline', 'how many players on a team', 'what is zero rb', 'what is vorp', 'what is a parlay',
  'what does the spread mean', 'who has the most rushing yards ever', 'what is cover 2', 'how big is a football field', 'what is a fair catch',
  'how does the draft work', 'what is a franchise tag', 'what is ir', 'who has the most super bowls', 'how many games in the season', 'what is a touchback',
  'what is play action', 'what is an rpo', 'what is adp', 'what is a stack', 'what is streaming', 'explain the kickoff rule', 'what is a pick six',
  'how many timeouts does a team get', 'what is the two minute warning', 'how do challenges work', 'what is holding', 'what is a false start'],
 'greeting': ['good evening', 'good afternoon', 'hey there', 'hi there', 'whats good', 'hey man', 'hello bff', 'hi', 'hello', 'hey', 'yo', 'sup', 'good morning', 'hey bff', 'whats up', 'hello there', 'hiya', 'howdy'],
 'thanks': ['thanks a lot', 'thanks so much', 'thank you so much', 'much appreciated', 'cheers', 'sweet thanks', 'you rock', 'helpful thanks', 'thanks', 'thank you', 'thx', 'ty', 'appreciate it', 'great thanks', 'awesome thank you', 'perfect', 'ok cool', 'got it', 'nice', 'that helps'],
 'smalltalk': ['how are you', 'how are you doing', 'hows it going', 'how you doing today', 'what are you up to', 'how is your day', 'who are you', 'what are you',
  'are you a real person', 'are you human', 'am i talking to a real person', 'is this a bot', 'are you a bot', 'are you ben', 'is this ben', 'who made you',
  'who built you', 'who created this site', 'what is your name', 'whats your name', 'do you have a name', 'tell me a joke', 'tell me a football joke', 'do you know any jokes', 'any good jokes', 'joke please',
  'say something funny', 'make me laugh', 'whats your favorite team', 'who is your favorite player', 'who do you root for', 'what can you do',
  'what do you know', 'are you smart', 'are you better than chatgpt', 'do you like football', 'what is your favorite color', 'are you alive'],
 'vent': ['my team sucks', 'i lost again', 'i lost by one point', 'my season is over', 'i hate fantasy football', 'injuries ruined my season',
  'my team is so bad', 'my team is awful', 'my roster is trash this year', 'my team stinks this season', 'my squad is horrible', 'i am 0 and NUM', 'im 0 NUM', 'i keep losing', 'my rbs keep getting hurt', 'worst week ever', 'my lineup got destroyed',
  'i lost on monday night', 'i got unlucky again', 'i scored the second most points and still lost', 'this league hates me', 'ugh my team',
  'my qb got hurt', 'i benched the wrong guy', 'i started the wrong player', 'i am so mad', 'i am frustrated with my team', 'how do i save my season',
  'lost my matchup by NUM points', 'my team is cursed', 'everyone on my team is injured'],
 'complaint': ['you were wrong', 'that was bad advice', 'your projections are wrong', 'your projection was way off', 'you told me to start {P} and he busted',
  'why did you say to start {P}', 'bff got it wrong', 'your site is wrong', 'this is terrible advice', 'your rankings are bad', 'you suck at this',
  'that pick was awful', 'you said {P} would score more', 'your model is broken', 'you were way off on {P}', 'worst advice ever', 'your bot is dumb',
  'why are your projections so low', 'your numbers make no sense', 'that trade advice was bad'],
 'offtopic': ['how do i bake a cake', 'whats a good recipe for chicken', 'how do i change a tire', 'what is the best laptop', 'who is the richest person', 'whats the tallest building', 'recommend a book', 'how do i learn guitar', 'what is the best video game', 'what is the capital of france', 'can you help me write an essay', 'who won the stanley cup', 'how do i make pasta', 'whats the best phone to buy', 'who is taylor swift', 'solve this math problem', 'what should i eat for dinner', 'help me with my resume', 'how far is the moon', 'who won the masters', 'nba trade rumors', 'what is the meaning of life', 'write a cover letter', 'summarize this article', 
  'what is the weather', 'write me a poem', 'help with my homework', 'what is 2 plus 2', 'who won the nba finals', 'best pizza near me',
  'how do i code in python', 'what stock should i buy', 'who is the president', 'recommend a movie', 'how do i lose weight', 'what time is it',
  'translate this to spanish', 'who won the world series', 'how tall is mount everest', 'explain quantum physics', 'book a flight', 'what is bitcoin',
  'nhl scores', 'premier league table', 'how do i fix my car'],
}

NOISE_PRE = ['', '', '', 'yo ', 'hey ', 'quick question ', 'bff ', 'ok ', 'so ', 'help ', 'honestly ', 'real quick ']
NOISE_POST = ['', '', '', '?', '??', ' lol', ' pls', ' please', ' thanks', '!', ' bro', ' asap']


def typo(s, rate=.04):
    out = []
    for ch in s:
        r = R.random()
        if ch.isalpha() and r < rate / 3: continue                       # drop
        if ch.isalpha() and r < 2 * rate / 3: out.append(ch + ch); continue  # double
        out.append(ch)
    return ''.join(out)


def fill(t):
    s = t.format(P=P, P2=P2, P3=P3, W=R.choice(WEEK))
    return s


TERMS = ['ppr', 'half ppr', 'superflex', 'a flex', 'a handcuff', 'faab', 'a waiver wire', 'a bye week', 'dst', 'a dynasty league', 'a keeper league', 'best ball',
         'adp', 'zero rb', 'hero rb', 'a stack', 'streaming', 'a sleeper', 'a bust', 'a floor', 'a ceiling', 'buy low', 'sell high', 'regression', 'target share',
         'snap share', 'air yards', 'adot', 'wopr', 'yards per route run', 'epa', 'cpoe', 'success rate', 'proe', 'vorp', 'a vulture', 'a committee backfield',
         'garbage time', 'game script', 'an ir slot', 'a safety', 'a touchback', 'a fair catch', 'a two point conversion', 'an extra point', 'a field goal', 'a sack',
         'a pick six', 'an interception', 'a fumble', 'pass interference', 'holding', 'a false start', 'offsides', 'roughing the passer', 'intentional grounding',
         'the red zone', 'a first down', 'a turnover on downs', 'cover 2', 'cover 3', 'man coverage', 'zone coverage', 'a blitz', 'nickel defense', 'play action', 'an rpo',
         'a screen pass', 'a hail mary', 'an onside kick', 'a franchise tag', 'a fifth year option', 'the practice squad', 'injured reserve', 'pup', 'the spread',
         'a moneyline', 'an over under', 'a parlay', 'a prop bet', 'the vig', 'an implied total', 'the play clock', 'the two minute warning', 'a challenge', 'overtime',
         'the dynamic kickoff', 'a wild card', 'the draft', 'compensatory picks', 'the trade deadline', 'questionable', 'doubtful']
KPAT = ['what is {t}', 'whats {t}', 'define {t}', 'what does {t} mean', 'explain {t}', 'what is {t} in football', 'what is {t} in fantasy', 'meaning of {t}', 'how does {t} work', 'can you explain {t}']
OFF = ['the capital of {x}', 'the population of {x}', 'the weather in {x}', 'the best restaurant in {x}', 'flights to {x}']
OFFX = ['france', 'japan', 'texas', 'chicago', 'brazil', 'canada', 'new york', 'italy']
OFFQ = ['what is {o}', 'tell me {o}', 'whats {o}', 'find {o}']


def generate(n_per=500):
    X, Y = [], []
    for lab, temps in T_.items():
        k = n_per if lab not in ('greeting', 'thanks', 'smalltalk', 'vent', 'complaint') else n_per // 3
        for _ in range(k):
            s = fill(R.choice(temps))
            if R.random() < .15 and lab in ('start_sit', 'player', 'trade', 'keep_drop', 'waiver', 'injury', 'stats', 'prop'): s = s.replace('should i', R.choice(WHO))
            s = R.choice(NOISE_PRE) + s + R.choice(NOISE_POST)
            if R.random() < .3: s = typo(s)
            if R.random() < .5: s = s.lower()
            X.append(s); Y.append(lab)
    for _ in range(n_per):
        s = R.choice(KPAT).format(t=R.choice(TERMS)) + R.choice(NOISE_POST)
        if R.random() < .3: s = typo(s)
        X.append(s); Y.append('knowledge')
    for _ in range(n_per // 2):
        s = R.choice(OFFQ).format(o=R.choice(OFF).format(x=R.choice(OFFX))); X.append(s); Y.append('offtopic')
    return X, Y


# hand-written questions the model never trains on (how people really type), for an honest accuracy check
TEST = [
 ('PLAYER or PLAYER this week?', 'start_sit'), ('who do i flex, PLAYER or PLAYER', 'start_sit'), ('PLAYER vs PLAYER who goes off', 'start_sit'),
 ('should PLAYER be in my lineup over PLAYER', 'start_sit'), ('im torn between PLAYER and PLAYER for my last spot', 'start_sit'),
 ('is PLAYER gonna be good against the TEAM', 'player'), ('PLAYER worth playing this week?', 'player'), ('how many pts u think PLAYER gets', 'player'),
 ('is PLAYER still a top 12 POSN', 'player'), ('what do you have PLAYER projected at', 'player'), ('PLAYER?', 'player'),
 ('would you trade PLAYER for PLAYER straight up', 'trade'), ('offered PLAYER and PLAYER for my PLAYER, accept?', 'trade'),
 ('PLAYER for PLAYER who says no', 'trade'), ('getting PLAYER for PLAYER good deal?', 'trade'), ('my PLAYER for their PLAYER and PLAYER', 'trade'),
 ('what could PLAYER fetch in a trade', 'trade_value'), ('is now the time to sell PLAYER', 'trade_value'), ('PLAYER trade value rn', 'trade_value'),
 ('is PLAYER cuttable', 'keep_drop'), ('time to drop PLAYER?', 'keep_drop'), ('do i keep holding PLAYER', 'keep_drop'),
 ('who should i grab at POSN off the wire', 'waiver'), ('any POSN worth picking up', 'waiver'), ('best available POSN for my bench', 'waiver'), ('should i use faab on PLAYER', 'waiver'),
 ('top 5 POSN for week NUM', 'rankings'), ('who are the best POSN right now', 'rankings'), ('give me your POSN rankings', 'rankings'),
 ('who has the most rushing yards this year', 'leaders'), ('receiving yards leaders', 'leaders'), ('who leads in td catches', 'leaders'),
 ('what are PLAYER numbers this year', 'stats'), ('how many yards did PLAYER have last week', 'stats'), ('PLAYER targets per game', 'stats'),
 ('is PLAYER gonna play sunday', 'injury'), ('whats the update on PLAYER ankle', 'injury'), ('PLAYER out?', 'injury'), ('when is PLAYER back from ir', 'injury'),
 ('whats the latest with PLAYER', 'news'), ('why did PLAYER only play half the snaps', 'news'), ('any breaking news today', 'news'),
 ('how good are the TEAM this year', 'team'), ('who do the TEAM have next', 'team'), ('who is TEAM starting at qb', 'team'), ('TEAM bye?', 'team'),
 ('who gives up the most fantasy points to POSN', 'defense'), ('is the TEAM d tough on POSN', 'defense'), ('what dst should i stream', 'defense'),
 ('who wins TEAM TEAM tonight', 'game'), ('TEAM -NUM, will they cover', 'game'), ('who do you like in the TEAM game', 'game'),
 ('PLAYER over NUM rec yards?', 'prop'), ('will PLAYER hit the over', 'prop'), ('PLAYER anytime touchdown?', 'prop'),
 ('give me a NUM legger for sunday', 'parlay'), ('need a sgp for tonight', 'parlay'), ('best bets this weekend', 'parlay'),
 ('who scores a td in the TEAM game', 'td'), ('td scorers tonight', 'td'),
 ('who should i start in my league', 'lineup'), ('optimize my starters', 'lineup'),
 ('my squad: PLAYER PLAYER PLAYER PLAYER, what trades', 'roster'), ('what does my roster need', 'roster'), ('find me trades for my team', 'roster'),
 ('who are your sleepers this week', 'calls'), ('who are the buy lows', 'calls'), ('must start players', 'calls'),
 ('how do you calculate trade value', 'site'), ('how do i import my espn league', 'site'), ('what does this site do', 'site'), ('is bff better than the experts', 'site'),
 ('what does ppr mean', 'knowledge'), ('how does overtime work in the nfl now', 'knowledge'), ('whats a handcuff in fantasy', 'knowledge'),
 ('how many points do you get for a safety', 'knowledge'), ('what is a wild card team', 'knowledge'), ('who won the super bowl this year', 'knowledge'),
 ('what is target share', 'knowledge'), ('when is the nfl trade deadline', 'knowledge'),
 ('hey whats up', 'greeting'), ('thank u', 'thanks'), ('cool thanks', 'thanks'),
 ('what is the capital of france', 'offtopic'), ('can you help me write an essay', 'offtopic'), ('who won the stanley cup', 'offtopic'),
]

# a second, fresh set written after the model was finished (never used to change it): the accuracy BFF reports
TEST2 = [
 ('PLAYER or PLAYER in a ppr league', 'start_sit'), ('i got PLAYER and PLAYER, only one can play', 'start_sit'), ('flex dilemma PLAYER PLAYER PLAYER', 'start_sit'),
 ('who would u roll out PLAYER or PLAYER', 'start_sit'), ('PLAYER over PLAYER this week yes or no', 'start_sit'), ('which of PLAYER and PLAYER has the better matchup', 'start_sit'),
 ('do you like PLAYER this week', 'player'), ('PLAYER outlook vs the TEAM', 'player'), ('PLAYER a must play?', 'player'), ('how high is PLAYER ceiling this week', 'player'),
 ('is PLAYER a bust candidate this week', 'player'), ('how will PLAYER do', 'player'),
 ('i was offered PLAYER for PLAYER, good?', 'trade'), ('trading away PLAYER for PLAYER and PLAYER, thoughts', 'trade'), ('would PLAYER for PLAYER help my team', 'trade'),
 ('2 for 1: PLAYER and PLAYER for PLAYER', 'trade'), ('should i do this deal: PLAYER for PLAYER', 'trade'),
 ('how much value does PLAYER have', 'trade_value'), ('should i shop PLAYER', 'trade_value'), ('is PLAYER worth more than his production', 'trade_value'),
 ('can i let PLAYER go', 'keep_drop'), ('PLAYER bench stash or drop', 'keep_drop'), ('should i keep PLAYER through the bye', 'keep_drop'),
 ('best POSN available to pick up', 'waiver'), ('who is the top waiver add', 'waiver'), ('how much should i bid on PLAYER', 'waiver'), ('is PLAYER worth picking up', 'waiver'),
 ('who are the top POSN going forward', 'rankings'), ('POSN rankings week NUM', 'rankings'), ('who is POSN1 for the rest of the year', 'rankings'),
 ('rushing leaders this season', 'leaders'), ('who has the most catches this year', 'leaders'), ('top scoring POSN so far', 'leaders'),
 ('what did PLAYER do last sunday', 'stats'), ('PLAYER yards this season', 'stats'), ('how many targets did PLAYER get last game', 'stats'), ('PLAYER snaps', 'stats'),
 ('PLAYER injury status', 'injury'), ('will PLAYER suit up thursday', 'injury'), ('how long will PLAYER be out', 'injury'), ('is PLAYER ok', 'injury'),
 ('anything new on PLAYER', 'news'), ('what is going on with the TEAM', 'news'), ('why did PLAYER get so few touches', 'news'),
 ('TEAM record this year', 'team'), ('who are the TEAM playing this week', 'team'), ('TEAM starting running back', 'team'), ('when is the TEAM game', 'team'),
 ('worst defense against POSN', 'defense'), ('which teams are easy for POSN', 'defense'), ('TEAM defense against the run', 'defense'),
 ('prediction for TEAM at TEAM', 'game'), ('who covers TEAM TEAM', 'game'), ('over or under in the TEAM game', 'game'),
 ('PLAYER over NUM catches', 'prop'), ('PLAYER rushing yards over under', 'prop'), ('PLAYER to score tonight?', 'prop'),
 ('NUM team parlay', 'parlay'), ('build a same game parlay for TEAM', 'parlay'), ('good bets for monday night', 'parlay'),
 ('anytime touchdown scorers for sunday', 'td'), ('who should i bet to score', 'td'),
 ('who should i start from my roster', 'lineup'), ('best lineup for my team', 'lineup'),
 ('PLAYER PLAYER PLAYER PLAYER PLAYER is my team, what should i do', 'roster'), ('suggest some trades for my roster', 'roster'),
 ('who are the sleepers at POSN', 'calls'), ('sell high players right now', 'calls'), ('who busts this week', 'calls'),
 ('how is your projection made', 'site'), ('can i connect my yahoo league', 'site'), ('how do i change to half ppr on the site', 'site'), ('what are bff originals', 'site'),
 ('what does superflex mean', 'knowledge'), ('how many points is a pick six worth', 'knowledge'), ('what is an onside kick', 'knowledge'), ('how long is the play clock', 'knowledge'),
 ('who has the most career receiving yards', 'knowledge'), ('how do nfl playoffs work', 'knowledge'), ('what does doubtful mean', 'knowledge'),
 ('good evening', 'greeting'), ('thanks a lot', 'thanks'), ('appreciate the help', 'thanks'),
 ('who won the nba championship', 'offtopic'), ('how do i bake a cake', 'offtopic'), ('what is the best laptop', 'offtopic'), ('who is the richest person', 'offtopic'),
]


# the final check, written before the last training run: never used to tune anything
TEST3 = [
 ('PLAYER or PLAYER for my RB2 spot', 'start_sit'), ('can you help me decide between PLAYER and PLAYER', 'start_sit'), ('PLAYER PLAYER who do i trust more this week', 'start_sit'),
 ('PLAYER or PLAYER, need a safe floor', 'start_sit'), ('is PLAYER a better start than PLAYER', 'start_sit'),
 ('what are your thoughts on PLAYER this week', 'player'), ('is PLAYER a good play in ppr', 'player'), ('PLAYER projection for sunday', 'player'),
 ('expect a big game from PLAYER?', 'player'), ('should PLAYER be starting for me', 'player'),
 ('is it worth trading PLAYER for PLAYER', 'trade'), ('they want PLAYER for PLAYER and PLAYER', 'trade'), ('PLAYER for PLAYER, who wins the trade', 'trade'),
 ('would you give up PLAYER to get PLAYER', 'trade'),
 ('what is the trade value of PLAYER right now', 'trade_value'), ('is PLAYER someone i should sell', 'trade_value'), ('what kind of return can i get for PLAYER', 'trade_value'),
 ('should PLAYER be dropped', 'keep_drop'), ('is it safe to cut PLAYER', 'keep_drop'), ('drop PLAYER for a waiver guy?', 'keep_drop'),
 ('who should i claim off waivers this week', 'waiver'), ('top waiver POSN', 'waiver'), ('is PLAYER a good pickup', 'waiver'), ('who to stream at qb', 'waiver'),
 ('rank the top POSN for me', 'rankings'), ('best POSN week NUM', 'rankings'), ('rest of season POSN rankings', 'rankings'),
 ('who leads the nfl in receiving yards', 'leaders'), ('most rushing tds this season', 'leaders'), ('who has scored the most fantasy points this year', 'leaders'),
 ('PLAYER stats last week', 'stats'), ('how many touchdowns has PLAYER scored', 'stats'), ('what is PLAYER averaging', 'stats'),
 ('is PLAYER going to play this week', 'injury'), ('PLAYER hamstring update', 'injury'), ('is PLAYER on the injury report', 'injury'), ('when will PLAYER return from injury', 'injury'),
 ('latest on PLAYER', 'news'), ('did something happen to PLAYER', 'news'), ('top nfl headlines today', 'news'),
 ('how are the TEAM this season', 'team'), ('TEAM upcoming schedule', 'team'), ('who is the TEAM backup quarterback', 'team'),
 ('which defenses are worst against POSN', 'defense'), ('is the TEAM defense good against POSN', 'defense'), ('best defense to stream this week', 'defense'),
 ('who will win TEAM TEAM on sunday', 'game'), ('what is the line on the TEAM game', 'game'), ('do the TEAM win tonight', 'game'),
 ('PLAYER passing yards prop', 'prop'), ('over NUM rushing yards for PLAYER?', 'prop'), ('PLAYER over or under NUM receptions', 'prop'),
 ('give me a parlay for sunday', 'parlay'), ('NUM leg same game parlay', 'parlay'), ('what are your best bets', 'parlay'),
 ('who scores a touchdown tonight', 'td'), ('touchdown picks for the TEAM game', 'td'),
 ('set my lineup for this week', 'lineup'), ('which of my players should start', 'lineup'),
 ('my team: PLAYER, PLAYER, PLAYER, PLAYER. any trades?', 'roster'), ('what should my team trade for', 'roster'), ('rate my roster', 'roster'),
 ('who are your sleepers', 'calls'), ('any buy low guys', 'calls'), ('who should i avoid starting this week', 'calls'),
 ('how does bff value work', 'site'), ('how do i link my sleeper league', 'site'), ('how often do you update', 'site'), ('what is the bff accuracy', 'site'),
 ('what is a handcuff', 'knowledge'), ('how many points for a field goal', 'knowledge'), ('what is the red zone in football', 'knowledge'),
 ('what does ppr stand for', 'knowledge'), ('how many teams are in the nfl', 'knowledge'), ('what is a two point conversion', 'knowledge'), ('what is pass interference', 'knowledge'),
 ('hey', 'greeting'), ('hello!', 'greeting'), ('thanks!', 'thanks'), ('ok thank you', 'thanks'),
 ('what is the weather tomorrow', 'offtopic'), ('who won the world cup', 'offtopic'), ('help me with math homework', 'offtopic'), ('recommend a good movie tonight', 'offtopic'),
 ('hey hows it going', 'smalltalk'), ('wait are you an actual person', 'smalltalk'), ('who built this thing', 'smalltalk'), ('got any jokes', 'smalltalk'),
 ('my team is terrible this year', 'vent'), ('lost by 2 points again ugh', 'vent'), ('my whole team got hurt', 'vent'),
 ('you were totally wrong about PLAYER', 'complaint'), ('your projections stink', 'complaint'), ('that advice cost me my matchup', 'complaint'),
]
