import os,json,io,urllib.request,datetime,sys
import pandas as pd, numpy as np
from scipy.stats import spearmanr
# data, features and the season (rolls forward on its own; see ff_build2.py)
from ff_build2 import (POS, SEASON, PHASE, EW_H, r, st, ids, SC, gm, prev, dvp_table, dvp_factor)
B='https://github.com/nflverse/nflverse-data/releases/download/'
def get(rel):
    with urllib.request.urlopen(B+rel,timeout=180) as r_: return pd.read_parquet(io.BytesIO(r_.read()))
def local_or(name,rel=None):
    """a data file fetch_data.py saved, else a download, else None (some files do not exist before the season starts)"""
    try:
        if os.path.exists(name): return pd.read_parquet(name)
        return get(rel) if rel else None
    except Exception as e: print('not available:',name,e); return None
# ---------------- the model (version 5; ff_feat.py builds the features, ff_model.py the trees). It learns from the 13
# completed seasons before this one; the latest of them is first predicted by models trained only on the seasons before it,
# which gives the accuracy, ranges and boom/bust spreads shown on the site. Completed seasons' features are cached.
import ff_feat as FX, ff_model as FM
NHIST=13; FIRST=SEASON-NHIST; XFPY=[FIRST-1,FIRST]; TEST=SEASON-1; TRAIN=list(range(FIRST,TEST)); HIST5=list(range(FIRST,SEASON))
CACHE='.cache'; FV='f5'; os.makedirs(CACHE,exist_ok=True)
_cf=lambda s_:f'{CACHE}/{FV}_{SEASON}_{s_}.parquet'; _rf=f'{CACHE}/{FV}_{SEASON}_xfp.json'
SCOL=['passing_yards','passing_tds','passing_interceptions','rushing_yards','rushing_tds','receptions','receiving_yards','receiving_tds']
WARM=all(os.path.exists(_cf(s_)) for s_ in HIST5) and os.path.exists(_rf)
if WARM:
    C5=FX.Ctx(sorted({SEASON-2,SEASON-1,SEASON}),XFPY,rates=json.load(open(_rf))); DH=pd.concat([pd.read_parquet(_cf(s_)) for s_ in HIST5],ignore_index=True)
else:
    C5=FX.Ctx(list(range(FIRST-1,SEASON+1)),XFPY); json.dump(C5.rates,open(_rf,'w')); parts_=[]
    for s_ in HIST5:
        d_=C5.season_rows(s_).merge(C5.st[['player_id','season','week']+SCOL].drop_duplicates(['player_id','season','week']),on=['player_id','season','week'],how='left')
        d_[SCOL]=d_[SCOL].fillna(0); d_.to_parquet(_cf(s_)); parts_.append(d_)
    DH=pd.concat(parts_,ignore_index=True)
FCOLS=[c for c in DH.columns if c not in SCOL]
print('training rows',{int(k):int(v) for k,v in DH.groupby('season').size().items()},'| features cached' if WARM else '| features built',flush=True)
res={}; RNG={}; QS={}
EV=FM.Model(DH[DH.season.isin(TRAIN)],FCOLS,seeds=1,ros=False); DTE=DH[DH.season==TEST]
for pos in POS:
    t=DTE[DTE.pos==pos]; pp=EV.next(pos,t); base_=FM.prep(t,EV.pr).b.values
    def sp(pred): return float(np.nanmean([spearmanr(x.pp,x.y).correlation for w,x in t.assign(pp=pred).groupby('week') if len(x)>8]))
    res[pos]={'n':int(len(t)),'mae_base':r(float(np.mean(np.abs(base_-t.y)))),'rank_base':r(sp(base_),3),'mae':r(float(np.mean(np.abs(pp-t.y)))),'rank':r(sp(pp),3),'model':'v5'}
    q=t.assign(pp=pp); q=q[q.pp>=5]; ratio=q.y/q.pp; RNG[pos]=[r(ratio.quantile(.1)),r(ratio.quantile(.9))]
    QS.setdefault(pos,{})
    for lo,hi in ((5,10),(10,15),(15,99)):
        qq=t.assign(pp=pp); qq=qq[(qq.pp>=lo)&(qq.pp<hi)]; rt=qq.y/qq.pp
        QS[pos][str(lo)]=[r(rt.quantile(k/20),3) for k in range(1,20)] if len(rt)>=60 else None
    print(pos,'test',TEST,res[pos],flush=True)
MODEL=FM.Model(DH,FCOLS,seeds=3,ros=False); POSAVG={p:float(v) for p,v in MODEL.pr.pavg.items()}
# a sample for the spreadsheet's 'BFF Formula' (a straight-line stand-in for the trees, fit to their projections):
# last completed season's rows, the model's projection and the inputs the spreadsheet can compute
try:
    _fr=[]
    for pos in POS:
        t=FM.prep(DTE[DTE.pos==pos],MODEL.pr); _fr.append(t.assign(model=MODEL.next(pos,DTE[DTE.pos==pos]))[['player_id','season','week','pos','y','model','g','b','be','bx','bxe','l1_fp','it','spread','total','dvp','home','e_snap','e_ts','e_cs','bump','qbm','q','prac','dc','pv','p_fp','p_g','m_fp','e_fp','m_xfp','e_xfp','ew']])
    pd.concat(_fr).to_parquet(f'{CACHE}/formula_rows.parquet')
except Exception as e_: print('formula sample skipped:',e_)
print('model trained on',min(HIST5),'-',max(HIST5),flush=True)
# ---------------- this season's state (falls back to last season's rosters and depth charts before the first game)
S26=st[st.season==SEASON]; LAST=int(S26.week.max()) if len(S26) else 0
wr=local_or(f'roster_weekly_{SEASON}.parquet',f'weekly_rosters/roster_weekly_{SEASON}.parquet')
if wr is None or not len(wr):
    wr=local_or(f'roster_{SEASON}.parquet')   # season roster (offseason moves, rookies) before weekly rosters exist
    if wr is not None and 'week' not in wr.columns: wr=wr.assign(week=0)
if wr is None or not len(wr): wr=local_or(f'roster_weekly_{SEASON-1}.parquet',f'weekly_rosters/roster_weekly_{SEASON-1}.parquet')
for _c in ('status_description_abbr','jersey_number','full_name','position','status','team'):
    if _c not in wr.columns: wr[_c]=None
wr=wr.dropna(subset=['gsis_id']).sort_values('week'); cur=wr.groupby('gsis_id').tail(1).set_index('gsis_id')
dc=local_or(f'depth_charts_{SEASON}.parquet',f'depth_charts/depth_charts_{SEASON}.parquet')
if dc is None or not len(dc) or 'dt' not in dc.columns: dc=local_or(f'depth_charts_{SEASON-1}.parquet',f'depth_charts/depth_charts_{SEASON-1}.parquet')
if dc is None or 'dt' not in getattr(dc,'columns',[]): dc=pd.DataFrame(columns=['dt','gsis_id','team','pos_abb','pos_rank','player_name'])
dc=dc[dc.dt==dc.dt.max()]
_INJC=['gsis_id','team','week','report_status','practice_status']
injall=local_or(f'injuries_{SEASON}.parquet',f'injuries/injuries_{SEASON}.parquet')
if injall is None or not len(injall): injall=pd.DataFrame(columns=_INJC)
for _c in ('report_primary_injury','full_name'):
    if _c not in injall.columns: injall[_c]=None
injfull=injall.copy()
injall=injall[injall.week==injall.groupby('team').week.transform('max')] if len(injall) else injall
inj=injall[injall.report_status.isin(['Out','Doubtful','Questionable'])]
injs=inj.drop_duplicates('gsis_id',keep='last').set_index('gsis_id')
def short_prac(v):
    v=str(v or ''); return 'DNP' if 'Did Not' in v else 'Limited' if 'Limited' in v else 'Full' if 'Full' in v else None
PRAC={r_.gsis_id:short_prac(r_.practice_status) for r_ in injall.itertuples() if short_prac(r_.practice_status)}
_pf=f'pbp_{SEASON}.parquet' if os.path.exists(f'pbp_{SEASON}.parquet') else f'pbp_{SEASON-1}.parquet'   # team pace: last season's until this one starts
P26=pd.read_parquet(_pf,columns=['week','posteam','play_type','qb_kneel','qb_spike','epa']); P26=P26[P26.play_type.isin(['pass','run'])&(P26.qb_kneel!=1)&(P26.qb_spike!=1)]
TV=P26.groupby(['posteam','week']).agg(pl=('epa','size'),pr=('play_type',lambda x:(x=='pass').mean())).groupby('posteam').mean()
RMAP={'QB':'QB','RB':'RB','HB':'RB','WR':'WR','LWR':'WR','RWR':'WR','SWR':'WR','TE':'TE'}   # fullbacks (FB) are not ranked as running backs
dc2=dc[dc.pos_abb.isin(RMAP)].copy(); dc2['pg']=dc2.pos_abb.map(RMAP); role=dc2.sort_values('pos_rank').drop_duplicates('gsis_id').set_index('gsis_id')
# pool: anyone with fantasy activity this season at QB/RB/WR/TE, plus depth-chart starters/backups (and, below, injured stars and the consensus top 300)
pool={x for x in set(S26.player_id)|set(dc2[dc2.pos_rank<=(3)].gsis_id) if isinstance(x,str) and x}
info=st.sort_values(['season','week']).groupby('player_id').tail(1).set_index('player_id')
idx=ids.dropna(subset=['gsis_id']).drop_duplicates('gsis_id').set_index('gsis_id')
# ---- bio for the player card: height, weight, birth date, college, draft, experience (season roster, else last season's, else the ID table)
BIO={}
for _y in (SEASON-1,SEASON):
    _r=local_or(f'roster_{_y}.parquet',f'rosters/roster_{_y}.parquet')
    if _r is None or not len(_r): continue
    for _x in _r.dropna(subset=['gsis_id']).drop_duplicates('gsis_id',keep='last').itertuples():
        _b={}
        if pd.notna(getattr(_x,'height',None)): _b['ht']=int(float(_x.height))
        if pd.notna(getattr(_x,'weight',None)): _b['wt']=int(float(_x.weight))
        if isinstance(getattr(_x,'birth_date',None),str) and len(_x.birth_date)>=10: _b['bd']=_x.birth_date[:10]
        if isinstance(getattr(_x,'college',None),str) and _x.college.strip(): _b['col']=_x.college.split(';')[0].strip()
        if pd.notna(getattr(_x,'years_exp',None)): _b['exp']=int(_x.years_exp)+(SEASON-_y)
        if pd.notna(getattr(_x,'entry_year',None)): _b['ey']=int(_x.entry_year)
        if pd.notna(getattr(_x,'draft_number',None)): _b['dp']=int(_x.draft_number)
        if isinstance(getattr(_x,'draft_club',None),str) and _x.draft_club: _b['dc']=_x.draft_club
        if _b: BIO[_x.gsis_id]=_b
def bio_of(pid):
    b=dict(BIO.get(pid,{}))
    if pid in idx.index:
        x_=idx.loc[pid]
        if 'ht' not in b and pd.notna(x_.get('height')): b['ht']=int(float(x_['height']))
        if 'wt' not in b and pd.notna(x_.get('weight')): b['wt']=int(float(x_['weight']))
        if 'col' not in b and isinstance(x_.get('college'),str): b['col']=x_['college']
        if 'bd' not in b and isinstance(x_.get('birthdate'),str): b['bd']=x_['birthdate'][:10]
        if pd.notna(x_.get('draft_year')): b['dy']=int(x_['draft_year'])
        if pd.notna(x_.get('draft_round')): b['dr']=int(x_['draft_round'])
        if 'dp' not in b and pd.notna(x_.get('draft_ovr')): b['dp']=int(x_['draft_ovr'])
    return b or None
try: dv=pd.read_csv('values.csv'); dvm=dv.set_index('fp_id').value_1qb.to_dict()   # dynasty market value: only used to keep injured stars in the player pool
except Exception as _e: print('dynasty values unavailable:',_e); dvm={}
# ---- FantasyPros rest-of-season expert consensus (PPR; mirrored daily by DynastyProcess): overall rank, position rank, and how widely each player is rostered.
# This is the redraft market check for trade values and the draft board (backtested 2023-25: see README).
ECR={}; ECR_DATE=None; TODAY=datetime.date.fromisoformat(os.environ['BFF_AS_OF']) if os.environ.get('BFF_AS_OF') else datetime.date.today()
try:
    _E=pd.read_csv('db_fpecr_latest.csv',dtype={'id':str},low_memory=False)
    _ro=_E[_E.page_type=='redraft-overall'].sort_values('ecr'); _rp=_E[_E.page_type.isin(['redraft-qb','redraft-rb','redraft-wr','redraft-te'])]
    for _k,_x in enumerate(_ro.itertuples()):
        ECR.setdefault(str(_x.id),{})['o']=_k+1
        if _x.player_owned_avg==_x.player_owned_avg: ECR[str(_x.id)]['own']=round(float(_x.player_owned_avg))
    for _pg,_G in _rp.groupby('page_type'):
        for _k,_x in enumerate(_G.sort_values('ecr').itertuples()):
            ECR.setdefault(str(_x.id),{})['p']=_k+1
            if 'own' not in ECR[str(_x.id)] and _x.player_owned_avg==_x.player_owned_avg: ECR[str(_x.id)]['own']=round(float(_x.player_owned_avg))
    ECR_DATE=str(_ro.scrape_date.max()) if len(_ro) else None
    print('consensus rankings:',len(_ro),'overall,',len(_rp),'by position, as of',ECR_DATE)
    if ECR_DATE and (TODAY-datetime.date.fromisoformat(ECR_DATE[:10])).days>14:
        print('consensus rankings are more than two weeks old; not using them'); ECR={}; ECR_DATE=None
except Exception as _e: print('consensus rankings unavailable (trade values fall back to projections only):',_e)
# ---- FantasyPros WEEKLY expert consensus for the coming week (PPR ranks by position). Blended into next week's projection:
# 2023-25 backtest, 46 weeks, 13,120 player-games, every season predicted by models trained only on earlier seasons:
# rank accuracy (mean weekly Spearman by position) model alone 0.594, experts alone 0.631, blend at 85% experts 0.632;
# average miss model alone 4.63, blend 4.49 points. The weight chosen leaving one season out each time was 0.85-1.0
# (the old 65% ranked a little worse than the experts alone: 0.630).
WK={}; WK_W=0.6   # the experts' share in the weekly mix (chosen on 2021-22, tested on 2023-26)
try:
    _W=pd.read_csv('fp_latest_weekly.csv',low_memory=False); _W=_W[_W.page.isin(['qb','ppr-rb','ppr-wr','ppr-te'])]
    if not len(SC[(SC.season==SEASON)&SC.pts.isna()]): raise ValueError('no schedule yet')
    _gd=pd.to_datetime(gm[(gm.season==SEASON)&(gm.week==int(SC[(SC.season==SEASON)&SC.pts.isna()].week.min()))].gameday)
    _kd=pd.to_datetime(_W.player_game_kickoff_ts,unit='s',utc=True).dt.tz_convert('America/New_York').dt.tz_localize(None).dt.normalize()
    _W=_W[(_kd>=_gd.min()-pd.Timedelta(days=1))&(_kd<=_gd.max()+pd.Timedelta(days=1))]   # only rankings for this week's games
    for _x in _W.itertuples(): WK[str(int(_x.fantasypros_id))]=int(_x.rank)
    print('weekly consensus:',len(WK),'players ranked for this week')
except Exception as _e: print('weekly consensus unavailable (next-week projections use the model only):',_e)
def wk_of(pid):
    if pid not in idx.index or 'fantasypros_id' not in idx.columns: return None
    f=idx.loc[pid,'fantasypros_id']
    return None if f is None or f!=f else WK.get(str(int(f)))
def ecr_of(pid):
    if pid not in idx.index or 'fantasypros_id' not in idx.columns: return {}
    f=idx.loc[pid,'fantasypros_id']
    if f is None or f!=f: return {}
    return ECR.get(str(int(f)),{})
# also keep injured and reserve players who still matter (market value or real production), e.g. on IR or PUP with no snaps this season
_pp1=st[st.season==SEASON-1].groupby('player_id').fantasy_points_ppr.agg(['mean','size']); _pp2=st[st.season==SEASON-2].groupby('player_id').fantasy_points_ppr.agg(['mean','size'])
_fpid=idx['fantasypros_id'].to_dict() if 'fantasypros_id' in idx.columns else {}
def _relevant(pid):
    v=dvm.get(_fpid.get(pid)) if pid in _fpid else None
    if v is not None and v==v and v>=150: return True
    if pid in _pp1.index and _pp1.loc[pid,'size']>=4 and _pp1.loc[pid,'mean']>=7: return True
    return bool(pid in _pp2.index and _pp2.loc[pid,'size']>=6 and _pp2.loc[pid,'mean']>=9)
_extra={pid for pid,r_ in cur.iterrows() if r_.get('position') in POS and r_.get('status') in ('RES','ACT','INA') and pid not in pool and _relevant(pid)}
pool|=_extra
# the consensus top 300 too (in the offseason that brings in rookies and players who changed teams)
_fp2g={str(int(f)):g for g,f in idx['fantasypros_id'].items() if f==f} if 'fantasypros_id' in idx.columns else {}
_ecrp={_fp2g[k] for k,v in ECR.items() if v.get('o',999)<=300 and k in _fp2g}-pool; pool|=_ecrp
# players on no NFL roster now (released, retired, never signed) have no games to project: in season, a player counts
# only if the latest weekly roster has him with a team (active, reserve, inactive, practice squad or exempt list), or, when
# that week does not list him, the season roster does; the depth chart decides only for players neither roster has.
ONTEAM=('ACT','RES','INA','DEV','EXE')
FREE=set()
if PHASE=='season' and 'week' in wr.columns and len(wr) and int(wr.week.max())>0:
    _MW=int(wr.week.max()); _R26=local_or(f'roster_{SEASON}.parquet',f'rosters/roster_{SEASON}.parquet')
    _R26=_R26.dropna(subset=['gsis_id']).sort_values('week' if 'week' in _R26.columns else 'gsis_id').groupby('gsis_id').tail(1).set_index('gsis_id') if _R26 is not None and len(_R26) and 'gsis_id' in _R26.columns else None
    for pid_ in list(pool):
        if pid_ in cur.index and int(cur.at[pid_,'week'])==_MW: ok_=cur.at[pid_,'status'] in ONTEAM
        elif _R26 is not None and pid_ in _R26.index: ok_=_R26.at[pid_,'status'] in ONTEAM
        else: ok_=pid_ in set(dc2.gsis_id)
        if not ok_: FREE.add(pid_)
    pool-=FREE
print(f'player pool: {len(pool)} ({len(_extra)} injured or reserve players added back, {len(_ecrp)} from the consensus top 300, {len(FREE)} on no NFL roster left out)')
SC26=SC[SC.season==SEASON]; SCHED_KNOWN=len(SC26)>0
if not SCHED_KNOWN:   # offseason before the schedule is out: 17 games against opponents still to be announced
    _tm=sorted(SC[SC.season==SEASON-1].team.unique())
    SC26=pd.DataFrame([(SEASON,w_,t_,'TBD',np.nan,np.nan,np.nan) for t_ in _tm for w_ in range(1,18)],columns=SC.columns)
if SC26.pts.isna().sum()==0: print('Regular season complete: no unplayed games, keeping the current page.'); sys.exit(0)
NEXT=int(SC26[SC26.pts.isna()].week.min()); byes={}   # current NFL week = earliest week with an unplayed game
for t in SC26.team.unique():
    wk=set(SC26[SC26.team==t].week); byes[t]=[w for w in range(1,19) if w not in wk] if SCHED_KNOWN else []
RET={}; AIR=[.12,.24,.30,.35,.42,.47,.50,.52]
for pid_,G_ in wr[wr.gsis_id.isin(set(cur[cur.status=='RES'].index))].groupby('gsis_id'):
    G_=G_.sort_values('week'); st_=list(G_.status); wk_=list(G_.week); i_=len(st_)-1
    while i_>0 and st_[i_-1]=='RES': i_-=1
    RET[pid_]=max(NEXT+1,int(wk_[i_])+4)   # still on the list now, so next week at the earliest
RSV={pid_:('PUP' if str(x).startswith('P') else 'NFI' if str(x).startswith('N') else 'Suspended' if str(x).startswith('S') else 'IR') for pid_,x in cur[cur.status=='RES'].get('status_description_abbr',pd.Series(dtype=str)).items()}
IDT={'GBP':'GB','JAC':'JAX','KCC':'KC','LVR':'LV','NEP':'NE','NOS':'NO','SFO':'SF','TBB':'TB','LAR':'LA','RAM':'LA','WSH':'WAS'}
def team_of(pid):
    if pid in cur.index and cur.loc[pid,'status'] in ('ACT','RES','INA','DEV','EXE'): return cur.loc[pid,'team'],cur.loc[pid,'status']
    if pid in role.index: return role.loc[pid,'team'],'ACT'
    if pid in info.index and (info.loc[pid,'season']==SEASON or pid not in idx.index): return info.loc[pid,'team'],None
    if pid in idx.index and isinstance(idx.loc[pid,'team'],str) and idx.loc[pid,'team'] not in ('FA','FA*'): return IDT.get(idx.loc[pid,'team'],idx.loc[pid,'team']),None
    return (info.loc[pid,'team'] if pid in info.index else None),None
players=[]; prev_pg=prev; GDAY=dict(zip(gm.game_id,gm.gameday)); AVL={}; NOUSE={'RB':1.2,'WR':1.1,'TE':0.6}; NOU={}
# per-game stat mix for custom scoring: this season's games plus three games' worth of last season (or of his position's
# typical mix when he has no last season). Order: pass yd, pass TD, INT, pass 2pt, carries, rush yd, rush TD, receptions,
# rec yd, rec TD, rush/rec 2pt, passing first downs, rushing + receiving first downs, fumbles lost.
MXC=[('passing_yards',),('passing_tds',),('passing_interceptions',),('passing_2pt_conversions',),('carries',),('rushing_yards',),('rushing_tds',),
     ('receptions',),('receiving_yards',),('receiving_tds',),('rushing_2pt_conversions','receiving_2pt_conversions'),('passing_first_downs',),
     ('rushing_first_downs','receiving_first_downs'),('rushing_fumbles_lost','receiving_fumbles_lost','sack_fumbles_lost')]
def _comp(d):
    return pd.DataFrame({k:sum((d[c].fillna(0).astype(float) if c in d.columns else 0.0) for c in grp) for k,grp in enumerate(MXC)},index=d.index)
_c26=_comp(S26).assign(player_id=S26.player_id.values); _S25=st[st.season==SEASON-1]; _c25=_comp(_S25).assign(player_id=_S25.player_id.values,position=_S25.position.values,fp=_S25.fp.values)
MX_SUM=_c26.groupby('player_id').sum(); MX_G=_c26.groupby('player_id').size()
_g25=_c25.groupby('player_id'); MX_PREV=_g25[list(range(len(MXC)))].mean()[_g25.size()>=3]
MX_POS=_c25[_c25.fp>=5].groupby('position')[list(range(len(MXC)))].mean()
def mix_of(pid,pos):
    base=MX_PREV.loc[pid].values if pid in MX_PREV.index else (MX_POS.loc[pos].values if pos in MX_POS.index else np.zeros(len(MXC)))
    g_=int(MX_G.get(pid,0)); s_=MX_SUM.loc[pid].values if pid in MX_SUM.index else np.zeros(len(MXC))
    return [round(float(x),2) for x in (s_+3*base)/(g_+3)]
_GLC=['completions','attempts','passing_yards','passing_tds','passing_interceptions','carries','rushing_yards','rushing_tds','receptions','targets','receiving_yards','receiving_tds']
_g=S26.copy()
for _c in _GLC+['sack_fumbles_lost','rushing_fumbles_lost','receiving_fumbles_lost']:
    if _c not in _g.columns: _g[_c]=0
_g['_fl']=_g[['sack_fumbles_lost','rushing_fumbles_lost','receiving_fumbles_lost']].fillna(0).sum(axis=1)
GL={pid:[[int(x['week'])]+[int(round(float(x[c] or 0))) for c in _GLC]+[int(x['_fl'])] for _,x in grp.sort_values('week').iterrows()] for pid,grp in _g.fillna(0).groupby('player_id')}
# ---- injury status for each player's next game. 2021-25 reports vs who really played (QB/RB/WR/TE who played 3+ games):
# Doubtful played 0.4% of the time, Questionable 61%; out last week and not practicing this week (before game statuses
# are set) 1.3%, limited 40%, full 74%. After an Out (not injured reserve), availability relative to healthy players was
# 39% the next week, 69% after two weeks, 85% after three and about 90% later (OUTA).
OUTA=[.39,.69,.85,.9]
# Questionable and then inactive (2021-25, n=558): 52.5% played the team's next game and 62.5% the one after, against 29%
# and 46% after an Out, so relative to healthy players about 0.7 and 0.9 (QINA)
QINA=[.7,.9,.9,.9]
NXW={t_:int(G_[G_.pts.isna()].week.min()) for t_,G_ in SC26.groupby('team') if G_.pts.isna().any()}
KD={}
for _g in gm[gm.season==SEASON].itertuples():
    for _t in (_g.home_team,_g.away_team): KD[(_t,int(_g.week))]=str(_g.gameday)
E2G={str(int(e)):g_ for g_,e in idx['espn_id'].items() if e==e} if 'espn_id' in idx.columns else {}
_nm=lambda s:' '.join(str(s or '').lower().replace('.','').replace("'",'').replace('-',' ').split())
N2G={(r_.team,_nm(r_.full_name)):g_ for g_,r_ in cur.iterrows() if isinstance(r_.full_name,str)}
def _espn_status(s):
    s=str(s or '').lower()
    if 'reserve' in s or 'physically unable' in s or s=='pup' or 'non-football' in s: return 'IR'
    return 'Out' if s.startswith('out') or 'suspen' in s else 'Doubtful' if s.startswith('doubt') else 'Questionable' if s.startswith('quest') else None
def _ret_week(tm_,d_):
    if not d_: return None
    W_=[w_ for (t_,w_),gd in KD.items() if t_==tm_ and gd>=str(d_)[:10]]
    return min(W_) if W_ else 99
STATUS={}; ESPN_T=set()
try:   # 1. ESPN's injury list for each team's next game (live.json; only games that have not started, in that team's next week)
    _lv=json.load(open('live.json')) if os.path.exists('live.json') else {}
    _gm={str(g_.get('id')):g_ for g_ in _lv.get('games') or []}
    for gid_,blk in (_lv.get('inj') or {}).items():
        g_=_gm.get(str(gid_)) or {}
        if g_.get('state')!='pre': continue
        for tm_,L_ in (blk.get('t') or {}).items():
            if NXW.get(tm_)!=(blk.get('w') or _lv.get('week')) or tm_ not in (g_.get('home'),g_.get('away')): continue
            ESPN_T.add(tm_)
            for e_ in L_:
                pid_=E2G.get(str(e_[0])) or N2G.get((tm_,_nm(e_[1]))); s_=_espn_status(e_[3])
                if pid_ and s_ and s_!='IR': STATUS[pid_]={'s':s_,'src':'ESPN','d':e_[4] or None,'rw':_ret_week(tm_,e_[5]) if s_ in ('Out','Doubtful') and len(e_)>5 else None}
    if ESPN_T: print('injuries: ESPN game lists for',len(ESPN_T),'teams')
except Exception as _e: print('ESPN injuries unavailable (using the official report):',_e)
# 2. the official report for teams ESPN did not cover (and what it implies before Friday's game statuses)
for tm_,G_ in (injfull.groupby('team') if len(injfull) else []):
    tm_=IDT.get(tm_,tm_)
    if tm_ in ESPN_T or tm_ not in NXW: continue
    wr_=int(G_.week.max()); nx_=NXW[tm_]; cw_=G_[G_.week==wr_]
    _pv=G_[(G_.week==wr_-1)&G_.report_status.isin(['Out','Doubtful'])]; prevO={a_:(b_ if isinstance(b_,str) else None) for a_,b_ in zip(_pv.gsis_id,_pv.report_primary_injury)}
    if wr_==nx_:
        for x_ in cw_.itertuples():
            s_=x_.report_status if x_.report_status in ('Out','Doubtful','Questionable') else None; d_=x_.report_primary_injury if isinstance(x_.report_primary_injury,str) else prevO.get(x_.gsis_id)
            if s_: STATUS[x_.gsis_id]={'s':s_,'src':'report','d':d_}
            elif x_.gsis_id in prevO:
                pr_=short_prac(x_.practice_status)
                if pr_=='DNP': STATUS[x_.gsis_id]={'s':'Out','src':'expected','d':d_,'n':f'Expected out: missed week {wr_-1} and not practicing'}
                elif pr_=='Limited': STATUS[x_.gsis_id]={'s':'Questionable','src':'expected','d':d_,'n':f'Missed week {wr_-1}; limited in practice'}
    elif wr_<nx_:
        # missed the reported game: listed Out or Doubtful, or Questionable and then inactive for it (weekly roster)
        _ina=set(wr[(wr.week==wr_)&(wr.status=='INA')].gsis_id)
        _miss=cw_.report_status.isin(['Out','Doubtful'])|((cw_.report_status=='Questionable')&cw_.gsis_id.isin(_ina))
        for x_ in cw_[_miss].itertuples():
            q_=x_.report_status=='Questionable'
            STATUS[x_.gsis_id]={'s':'Questionable','src':'expected','k':nx_-wr_,'cv':'q' if q_ else None,'d':x_.report_primary_injury if isinstance(x_.report_primary_injury,str) else None,'n':(f'Questionable for week {wr_} and did not play' if q_ else f'Missed week {wr_}')+f'; no injury report for week {nx_} yet'}
# 2b. the commissioner's exempt list (not allowed to play, like a suspension): out until the roster or the news says otherwise
EXEMPT={pid_ for pid_,x_ in cur.iterrows() if x_.get('status')=='EXE' and x_.get('position') in POS}
for pid_ in EXEMPT: STATUS[pid_]={'s':'Out','src':'roster','d':None,'n':"On the commissioner's exempt list (not allowed to play)"}
# 3. timelines reported in the news ("out at least three weeks", "out for the season") for a player whose next game has
#    no ESPN or official status yet: out until his team's week (next game after the story) + N weeks
import re as _re
_NUMW={'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10}
_TLW=_re.compile(r"\b(?:out|miss|sidelined|shelved)\b(?:\s+(?:for|at least|a minimum of|minimum of|roughly|about|approximately|around|another|an additional)){0,2}\s+(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)(?:\s*(?:-|–|to|or)\s*(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten))?\s+(?:more\s+)?weeks?\b",_re.I)
_TLS=_re.compile(r"\b(out for (the )?((rest|remainder) of (the )?)?(season|year)|season[- ]ending|(miss|misses|missing|sit out) (the )?((rest|remainder) of (the )?)?(season|year)(?!\s*(opener|finale|debut|'s first))|done for the (season|year))\b",_re.I)
_TLX=_re.compile(r"\b(return|returns|returning|back|activated|cleared|after missing|after being|designated to return)\b",_re.I)
_REIN=_re.compile(r"\b(reinstat\w*|removed? from (the )?(commissioner'?s )?exempt list|off (the )?(commissioner'?s )?exempt list|can play again|eligible to (play|return)|cleared to play|on track (to play|for (his |a |sunday'?s? |monday'?s? |thursday'?s? |week \d+ )?(debut|return))|(?<!not )(?<!n't )(?<!unlikely )(expected|set|slated|poised|going|ready) to (play|suit up|debut|make (his|a) debut)|will (play|suit up|debut|make his debut))\b",_re.I)
# a reinstatement stays known after its story leaves the news feed (news_state.json), until the roster drops the exempt
# status itself (October 2026: Josh Jacobs was reinstated on Oct 16, but a week later the story had aged out of the feed
# while the roster still said exempt, so he showed as out)
try: _NST=json.load(open('news_state.json')) if os.path.exists('news_state.json') else {}
except Exception: _NST={}
_RI={pid_:(pd.Timestamp(v_['d']),v_['s']) for pid_,v_ in (_NST.get('reinstated') or {}).items() if pid_ in EXEMPT}
NEWS_TL=0
try:
    _nj=json.load(open('news.json')) if os.path.exists('news.json') else {}
    _now=pd.Timestamp.now(tz='UTC'); _TL={}
    for it_ in sorted(_nj.get('items') or [],key=lambda x:str(x.get('d') or '')):
        h_=str(it_.get('h') or ''); d_=pd.to_datetime(it_.get('d'),utc=True,errors='coerce'); P_=it_.get('p') or []
        if len(P_)!=1 or pd.isna(d_) or (_now-d_).days>35: continue
        if P_[0] in EXEMPT and _REIN.search(h_): _RI[P_[0]]=(d_,it_.get('s') or 'news'); continue
        if it_.get('st')=='ok' or _TLX.search(h_): continue
        m_=_TLW.search(h_); se_=_TLS.search(h_)
        _wn=lambda g_: (int(g_) if g_.isdigit() else _NUMW[g_.lower()]) if g_ else None
        if m_ or se_: _TL[P_[0]]=(99 if se_ else _wn(m_.group(1)),d_,it_.get('s') or 'news',None if se_ else _wn(m_.group(2)))
    for pid_,(n_,d_,s_,hi_) in _TL.items():
        if pid_ not in cur.index or (STATUS.get(pid_) or {}).get('src') in ('ESPN','report'): continue
        tm_=IDT.get(cur.at[pid_,'team'],cur.at[pid_,'team'])
        if tm_ not in NXW: continue
        w0_=_ret_week(tm_,(d_+pd.Timedelta(days=1)).strftime('%Y-%m-%d')); rw_=99 if n_>=99 else (w0_ or 99)+n_
        if rw_<=NXW[tm_]: continue
        # injured reserve: a reported timeline later than the 4-game minimum moves his estimated return (example: the Rams
        # said Davante Adams would miss 6-10 weeks, so not before week 13 instead of the minimum's week 11)
        if pid_ in RET: RET[pid_]=max(RET[pid_],rw_)
        _span=f'{n_}-{hi_} weeks' if hi_ and hi_>n_ else f'{n_} week'+('s' if n_>1 else '')
        STATUS[pid_]={'s':'Out','src':'news','d':(STATUS.get(pid_) or {}).get('d'),'rw':rw_,'n':f"Reported out {'for the season' if n_>=99 else _span} ({s_}, {d_.strftime('%b')} {d_.day})"}; NEWS_TL+=1
    for pid_,(d_,s_) in _RI.items():   # reinstated: available again (tagged until the roster catches up)
        STATUS[pid_]={'s':'Questionable','src':'news','d':None,'n':f"Reinstated from the exempt list (reported by {s_}, {d_.strftime('%b')} {d_.day})"}; NEWS_TL+=1
    if NEWS_TL: print('injuries: timelines from the news for',NEWS_TL,'players')
except Exception as _e: print('news timelines unavailable:',_e)
try:
    json.dump({'reinstated':{pid_:{'d':d_.isoformat(),'s':s_} for pid_,(d_,s_) in sorted(_RI.items())}},open('news_state.json','w'),indent=1)
    if _RI: print('reinstated from the exempt list (kept until the roster catches up):',', '.join(sorted(str(cur.at[p_,'full_name']) if p_ in cur.index and 'full_name' in cur.columns else p_ for p_ in _RI)))
except Exception as _e: print('news state not saved:',_e)
print('injury status:',sum(v['s']=='Out' for v in STATUS.values()),'out,',sum(v['s']=='Doubtful' for v in STATUS.values()),'doubtful,',sum(v['s']=='Questionable' for v in STATUS.values()),'questionable,',sum(v['src']=='expected' for v in STATUS.values()),'of them expected from the report')
# ---- teammates expected to miss games: Out/Doubtful for the next game; injured reserve for every remaining week
OUTN={pid_ for pid_,v in STATUS.items() if v['s'] in ('Out','Doubtful')}
IRS=set(cur[cur.status=='RES'].index)
SIT={}
for tm_,G_ in S26.groupby('team'):
    wks_=sorted(G_.week.unique())[-3:]; rec_=G_[G_.week.isin(wks_)].groupby('player_id').agg(xpg=('xfp','mean'),gp=('week','nunique'),pos=('position','first'),att=('attempts','sum'),name=('player_display_name','first'))
    rec_=rec_[rec_.gp>=min(2,len(wks_))]
    def _sit(outset,rec=rec_):
        miss=rec[rec.index.isin(outset)]; pres=rec[~rec.index.isin(outset)]; qb=rec[rec.pos=='QB'].sort_values('att',ascending=False)
        qbm=int(len(qb)>0 and qb.index[0] in outset and qb.att.iloc[0]>=40)
        return dict(pres=pres,vr=float(miss[(miss.pos=='RB')&(miss.xpg>=4)].xpg.sum()),vw=float(miss[miss.pos.isin(['WR','TE'])&(miss.xpg>=4)].xpg.sum()),qbm=qbm,
                    names=[n for n,x in zip(miss.name,miss.xpg) if x>=4],qbname=(qb.name.iloc[0] if qbm else None))
    SIT[tm_]={'next':_sit(OUTN|IRS),'later':_sit(IRS)}
def sit_feats(pid,pos,tm,which):
    s_=(SIT.get(tm) or {}).get(which)
    if not s_: return 0.0,0,0.0
    pres=s_['pres']
    if pid not in pres.index: return 0.0,s_['qbm'],s_['vr']+s_['vw']
    grp=['RB'] if pos=='RB' else ['WR','TE'] if pos in ('WR','TE') else []
    vac=s_['vr'] if pos=='RB' else s_['vw'] if pos in ('WR','TE') else 0.0
    tot=float(pres[pres.pos.isin(grp)].xpg.sum()) if grp else 0.0
    return (vac*float(pres.loc[pid,'xpg'])/tot if tot>0 else 0.0),s_['qbm'],s_['vr']+s_['vw']
def _ident(pid):
    """team, roster status, position and name, or None when he cannot be projected"""
    tm,status=team_of(pid)
    if tm is None: return None
    pos=(info.loc[pid,'position'] if pid in info.index else (role.loc[pid,'pg'] if pid in role.index else (cur.loc[pid,'position'] if pid in cur.index else (idx.loc[pid,'position'] if pid in idx.index else None))))
    if pos not in POS: return None
    name=(info.loc[pid,'player_display_name'] if pid in info.index else role.loc[pid,'player_name'] if pid in role.index else None)
    if (not isinstance(name,str) or not name.strip()) and pid in cur.index: name=cur.loc[pid,'full_name']
    if (not isinstance(name,str) or not name.strip()) and pid in idx.index: name=idx.loc[pid,'name']
    if not isinstance(name,str) or not name.strip(): return None
    return tm,status,pos,name
# ---- every unplayed game of every player, projected at once. Betting lines where they are out; for weeks further ahead
# each team's points scored and allowed so far stand in for them (the same rule the value backtest used).
_TTN=C5.TT[(C5.TT.season==SEASON)&(C5.TT.week==NEXT)].set_index('team') if len(C5.TT) else pd.DataFrame()
_SCX={(int(x.week),x.team):x for x in C5.SC[C5.SC.season==SEASON].itertuples()}
def _proxy(tm,op):
    if tm in _TTN.index and op in _TTN.index:
        it_=(_TTN.loc[tm,'pts_t']+_TTN.loc[op,'pa_t'])/2; io_=(_TTN.loc[op,'pts_t']+_TTN.loc[tm,'pa_t'])/2; return float(it_),float(it_-io_),float(it_+io_)
    return 22.0,0.0,44.0
def _games(tm,sched):
    out=[]
    for g in sched.itertuples():
        x=_SCX.get((int(g.week),tm)); op=g.opp; hm=float(g.home) if g.home==g.home else 0.5
        it_,sp_,tt_=(x.it,x.spread,x.total) if x is not None else (np.nan,np.nan,np.nan)
        if not (it_==it_ and sp_==sp_ and tt_==tt_): it_,sp_,tt_=_proxy(tm,op)
        out.append((int(g.week),tm,op,hm,float(it_),float(sp_),float(tt_),float(x.dome) if x is not None and x.dome==x.dome else 0.0,float(x.rest) if x is not None and x.rest==x.rest else 0.0,float(x.div) if x is not None and x.div==x.div else 0.0))
    return out
_PRC={'DNP':0.0,'Limited':1.0,'Full':2.0}
_ID={}; _PL={}; _GM={}
for pid in pool:
    _i=_ident(pid)
    if _i is None: continue
    tm,status,pos,name=_i; sched=SC26[(SC26.team==tm)&SC26.pts.isna()].sort_values('week')   # this team's unplayed games
    if not len(sched): continue
    _ID[pid]=_i; _PL[pid]=pos; _GM[pid]=_games(tm,sched)
U5=C5.upcoming(SEASON,NEXT,_PL,_GM)
if not len(U5): U5=pd.DataFrame(columns=['player_id','pos','team','opp','week','gi','q','prac','bump','qbm','vac_all','dvp','e_fp'])
U5['gi']=U5.groupby('player_id').cumcount()
_sit=[sit_feats(pid_,pos_,tm_,'next' if gi_==0 else 'later') for pid_,pos_,tm_,gi_ in zip(U5.player_id,U5.pos,U5.team,U5.gi)]
U5['bump']=[x[0] for x in _sit]; U5['qbm']=[x[1] for x in _sit]; U5['vac_all']=[x[2] for x in _sit]
_first=U5.gi==0   # his next game: this week's injury report and practice
U5.loc[_first,'q']=[1.0 if (STATUS.get(pid_) or {}).get('s')=='Questionable' else 0.0 for pid_ in U5[_first].player_id]
U5.loc[_first,'prac']=[_PRC.get(PRAC.get(pid_),np.nan) for pid_ in U5[_first].player_id]
U5.loc[~_first,'q']=0.0; U5.loc[~_first,'prac']=np.nan
_LG={c:float(_TTN[c].mean()) for c in _TTN.columns if c.endswith('_t')} if len(_TTN) else {}
PRED={}
for pos in POS:
    u=U5[U5.pos==pos]
    if not len(u): continue
    P_=MODEL.next(pos,u); F1=u[u.gi==0]
    Pm_=MODEL.next(pos,F1.assign(dvp=1.0,**{'o_'+k:v for k,v in _LG.items()}))   # an average defense
    _px=[_proxy(t_,o_) for t_,o_ in zip(F1.team,F1.opp)]
    Pv_=MODEL.next(pos,F1.assign(it=[x[0] for x in _px],spread=[x[1] for x in _px],total=[x[2] for x in _px]))   # no betting line
    Pt_=MODEL.next(pos,F1.assign(bump=0.0,qbm=0,vac_all=0.0))   # no teammates out
    XL_=MODEL.parts(pos,F1)
    for pid_,ix in u.groupby('player_id',sort=False).indices.items():
        PRED[pid_]={'P':P_[ix],'wk':u.week.values[ix],'dvp':u.dvp.values[ix],'bump':u.bump.values[ix],'efp':float(u.e_fp.values[ix[0]]) if u.e_fp.values[ix[0]]==u.e_fp.values[ix[0]] else None}
    for j,pid_ in enumerate(F1.player_id.values):
        PRED[pid_].update(Pm=float(Pm_[j]),Pv=float(Pv_[j]),Pt=float(Pt_[j]),xl={c:round(float(v[j]),1) for c,v in XL_.items()})
# rest-of-season level = the average of his remaining game projections, each with its own opponent and team totals
# (2023-25 value backtest: better than adding a separate rest-of-season model, which the old version used)
for pid_,X in PRED.items():
    m_=X['wk']<=17; X['L']=float(np.mean(X['P'][m_])) if m_.any() else float(np.mean(X['P'])); X['PR']=X['P']
# how far his rest-of-season level moved with games played after the consensus was taken (the page adds half of that
# change in value to the consensus)
if ECR_DATE:
    _WE=int(gm[(gm.season==SEASON)&(pd.to_datetime(gm.gameday)>=pd.Timestamp(ECR_DATE[:10]))].week.min()) if ((gm.season==SEASON)&(pd.to_datetime(gm.gameday)>=pd.Timestamp(ECR_DATE[:10]))).any() else NEXT
    if _WE<NEXT:
        _chg={pid_:_PL[pid_] for pid_ in PRED if ((S26.player_id==pid_)&(S26.week>=_WE)).any()}
        if _chg:
            UE=C5.upcoming(SEASON,_WE,_chg,{pid_:_GM[pid_] for pid_ in _chg})
            for pos in POS:
                u=UE[UE.pos==pos]
                if not len(u): continue
                PE=MODEL.next(pos,u)
                for pid_,ix in u.groupby('player_id',sort=False).indices.items():
                    m_=u.week.values[ix]<=17; pb_=float(np.mean(PE[ix][m_])) if m_.any() else float(np.mean(PE[ix])); PRED[pid_]['dc']=r(PRED[pid_]['L']-pb_,2)
print('projected',len(PRED),'players,',len(U5),'games',flush=True)
for pid in pool:
    if pid not in PRED: continue
    tm,status,pos,name=_ID[pid]; X=PRED[pid]
    rows=S26[S26.player_id==pid].sort_values('week')
    pv=prev_pg.get((pid,SEASON),np.nan)
    if (pv is None or pv!=pv) and pid in _pp2.index and _pp2.loc[pid,'size']>=6: pv=0.9*float(_pp2.loc[pid,'mean'])   # missed last season: use the season before
    G_=_GM[pid]; wk_rows=[(g_[0],g_[2],g_[3],g_[4],{'dvp':float(X['dvp'][i_]) if X['dvp'][i_]==X['dvp'][i_] else None,'bump':float(X['bump'][i_])}) for i_,g_ in enumerate(G_)]
    P=X['P']; PR=X['PR']; Pr=np.array([X['L']]); dc_=X.get('dc'); Pm,Pv,Pt=X['Pm'],X['Pv'],X['Pt']; base={'efp':X['efp']}
    S_=STATUS.get(pid,{}); out=S_.get('s'); ir=status=='RES'
    nxt=wk_rows[0]; proj_next=float(P[0]); nw_=int(nxt[0])
    def _avail(w_):
        # chance he plays week w_: out now -> the measured return curve (or ESPN's estimated return); missed his last game
        # with no new report -> the same curve from that game
        if out in ('Out','Doubtful'):
            k_=w_-nw_; rw_=S_.get('rw')
            if k_<=0: return 0.0
            if rw_: return 0.0 if w_<rw_ else OUTA[min(3,1+w_-rw_)]
            return OUTA[min(3,k_-1)]
        if S_.get('k'): return (QINA if S_.get('cv')=='q' else OUTA)[min(3,S_['k']-1+w_-nw_)]
        return 1.0
    if out in ('Out','Doubtful') or ir: proj_next=0.0
    elif S_.get('k'): proj_next*=_avail(nw_)
    rec_pg=float(rows.receptions.mean()) if len(rows) else float(st[(st.player_id==pid)&(st.season==SEASON-1)].receptions.mean() or 0)
    ret_=RET.get(pid) if ir else None
    # injured reserve: nothing before his estimated return, then the share of games such players really played after it
    # (2023-25: 11% the first week, 34% by the fourth, about half later; 53% did not play again that season)
    _av=[(0.0 if ret_ and w[0]<ret_ else (AIR[min(len(AIR)-1,int(w[0])-ret_)] if ret_ else 1.0)) if ir else _avail(int(w[0])) for w in wk_rows if w[0]<=17]
    _raw=[float(P[i] if i==0 else PR[i]) for i,w in enumerate(wk_rows) if w[0]<=17]
    ros=[[int(w[0]),w[1],r(_av[i]*_raw[i],1)] for i,w in enumerate(wk_rows) if w[0]<=17]
    AVL[pid]=(_av,_raw)
    rl=role.loc[pid] if pid in role.index else None
    # no usage: on this team for 3+ weeks this season (active, inactive or practice squad, never on a reserve list) and
    # not one fantasy stat. Measured on 2021-25 (n=1,160 RB/WR/TE), such players scored about 1 PPR point the next week
    # (RB 1.23, WR 1.08, TE 0.58; 8% scored 5+), so the projection is capped there until he gets touches. Depth-chart
    # starters keep the model's number; quarterbacks follow the starter rule below.
    if pos in NOUSE and not len(rows) and not ir and status!='EXE' and not (rl is not None and rl['team']==tm and int(rl['pos_rank'])<=(3 if pos=='WR' else 1)):
        _h=wr[(wr.gsis_id==pid)&(wr.week>=1)]
        if not (_h.status=='RES').any() and ((_h.team==tm)&_h.status.isin(['ACT','INA','DEV'])).sum()>=3: NOU[pid]=NOUSE[pos]
    players.append({'id':pid,'n':name,'p':pos,'t':tm,'bio':bio_of(pid),'age':r(idx.loc[pid,'age'],1) if pid in idx.index and 'age' in idx.columns else None,
      'role':f"{rl['pg']}{int(rl['pos_rank'])}" if rl is not None and rl['team']==tm else None,'inj':('IR' if ir else out),'ret':ret_,'bmp':[[int(w[0]),r(w[4]['bump'],2)] for w in wk_rows[:2]],'rsv':(RSV.get(pid,'IR') if ir else None),
      'num':int(cur.loc[pid,'jersey_number']) if pid in cur.index and pd.notna(cur.loc[pid,'jersey_number']) else None,'g':int(len(rows)),'fp':r(rows.fp.sum(),1),'fpg':r(rows.fp.mean(),1) if len(rows) else None,'xfpg':r(rows.xfp.mean(),1) if len(rows) else None,
      'snap':r(rows.offense_pct.mean(),3) if len(rows) and rows.offense_pct.notna().any() else None,'ts':r(rows.target_share.mean(),3) if len(rows) else None,
      'ays':r(rows.air_yards_share.mean(),3) if len(rows) else None,'wopr':r(rows.wopr.mean(),3) if len(rows) else None,'tpg':r(rows.targets.mean(),1) if len(rows) else None,
      'cpg':r(rows.carries.mean(),1) if len(rows) else None,'cs':r(rows.car_share.mean(),3) if len(rows) else None,'rz':r(rows.rzo.mean(),1) if len(rows) else None,
      'rpg':r(rec_pg,2),'mx':mix_of(pid,pos),'prev':r(pv,1),'dy':int(idx.loc[pid,'draft_year']) if pid in idx.index and pd.notna(idx.loc[pid,'draft_year']) else None,
      'gl':GL.get(pid,[]),
      'wk':[[int(x.week),r(x.fp,1),r(x.xfp,1),r(x.offense_pct,2),int(x.targets),int(x.carries),x.opponent_team] for x in rows.itertuples()],
      'proj':r(proj_next,1),'nw':int(nxt[0]),'opp':nxt[1],'home':int(nxt[2]) if nxt[2]==nxt[2] else 0,'it':r(nxt[3],1),'rl':r(Pr[0],1),'frm':r(base.get('efp'),1),'dc':dc_,
      'dvp':r(nxt[4]['dvp'],3) if nxt[4]['dvp'] is not None else None,'xl':X.get('xl'),'adjm':r(P[0]-Pm,1),'adjv':r(P[0]-Pv,1),'adjt':(0.0 if (out in ('Out','Doubtful') or ir) else r(P[0]-Pt,1)),'injd':S_.get('d'),'injn':None if ir and S_.get('src')=='expected' else S_.get('n'),'injs':None if ir and S_.get('src')=='expected' else S_.get('src'),'pj0':r(float(P[0]),1) if (out in ('Out','Doubtful') or S_.get('k')) and not ir else None,'tmo':[n for n in (SIT.get(tm,{}).get('next',{}).get('names') or []) if n!=name][:4],'qbo':(lambda q:q if q and q!=name else None)(SIT.get(tm,{}).get('next',{}).get('qbname')),'prac':PRAC.get(pid),'tpl':r(TV.pl.get(tm,np.nan),1),'tpr':r(TV.pr.get(tm,np.nan),3),'ros':ros,'bye':(byes.get(tm) or [None])[0],
      'sid':str(int(idx.loc[pid,'sleeper_id'])) if pid in idx.index and pd.notna(idx.loc[pid,'sleeper_id']) else None,
      'eid':str(int(idx.loc[pid,'espn_id'])) if pid in idx.index and pd.notna(idx.loc[pid,'espn_id']) else None,
      'yid':str(int(idx.loc[pid,'yahoo_id'])) if pid in idx.index and pd.notna(idx.loc[pid,'yahoo_id']) else None,
      'ecr':ecr_of(pid).get('o'),'ecp':ecr_of(pid).get('p'),'own':ecr_of(pid).get('own'),'wkr':wk_of(pid) if int(nxt[0])==NEXT else None})
# ---- quarterbacks: only the expected starter is projected (a backup rarely takes a snap). Starter of record = the best
# quarterback on the depth chart who is not on injured reserve; expected starter = the best one not Out/Doubtful/IR. A
# fill-in keeps next week and, later, the chance the starter is still out; every other quarterback is projected for 0.
import re as _re
def _qrk(p):
    m_=_re.match(r'QB(\d+)$',p.get('role') or ''); return int(m_.group(1)) if m_ else 9
for tm_ in sorted({p['t'] for p in players if p['p']=='QB'}):
    Q_=sorted([p for p in players if p['t']==tm_ and p['p']=='QB'],key=lambda p:(_qrk(p),-sum(g_[2] for g_ in p.get('gl') or [])))
    sor=next((p for p in Q_ if p.get('inj')!='IR'),None); ns=next((p for p in Q_ if p.get('inj') not in ('Out','Doubtful','IR')),None)
    for p in Q_:
        if p is sor or p is ns: continue
        if (p.get('proj') or 0)>0 and p.get('pj0') is None: p['pj0']=p['proj']   # kept so the page can promote him if the starter is ruled out later
        p['proj']=0.0; p['adjt']=0.0; p['qbb']=1
        for row in p['ros']: row[2]=0.0
    if ns is not None:
        ns['qbs']=1
        if sor is not None and ns is not sor:
            a_,_=AVL.get(sor['id'],([1.0]*len(ns['ros']),None)); _,raw_=AVL.get(ns['id'],(None,[row[2] for row in ns['ros']]))
            for j_,row in enumerate(ns['ros']):
                if row[0]!=ns['nw'] and j_<len(a_) and j_<len(raw_): row[2]=r(raw_[j_]*(1-a_[j_]),1)
        # the starter missed his last game and his team has no injury report for the next one yet: he plays with the
        # measured chance (see _avail) and the next quarterback gets the rest, so the team's QB total stays whole
        # (e.g. Baker Mayfield after missing week 6: about 39% his projection, Jalon Daniels about 61% of his)
        if (STATUS.get(ns['id']) or {}).get('k') and ns.get('inj')!='IR':
            a_s,_=AVL.get(ns["id"],(None,None)); bq_=next((p for p in Q_ if p is not ns and p.get('inj') not in ('Out','Doubtful','IR')),None)
            raw_b=AVL.get(bq_['id'],(None,None))[1] if bq_ is not None else None
            if a_s and raw_b:
                for j_,row in enumerate(bq_['ros']):
                    if j_<len(a_s) and j_<len(raw_b): row[2]=r(raw_b[j_]*(1-a_s[j_]),1)
                bq_['proj']=bq_['ros'][0][2] if bq_['ros'] and bq_['ros'][0][0]==bq_['nw'] else 0.0
                bq_['qbb']=0; bq_['qbf']=1; bq_['pj0']=r(raw_b[0],1)
print('quarterbacks: expected starters', sum(1 for p in players if p.get('qbs')), '| backups set to 0:', sum(1 for p in players if p.get('qbb')))
# ---- ESPN's and Sleeper's public projections for the coming week (PPR points), fetched now. If a site does not answer, the
# numbers proj_compare.py last saved for this week are used. They join the weekly stack below and show on the player card.
OTH={}
def _other_sites():
    if PHASE!='season' or not NEXT: return
    got={'e':{},'s':{}}
    if not os.environ.get('BFF_NO_SITES'):
        try:
            import proj_compare as _pcm
            for k_,fn_ in (('e',_pcm.espn),('s',_pcm.sleeper)):
                try: got[k_]=fn_(SEASON,NEXT)
                except Exception as e_: print(f'other sites: {"ESPN" if k_=="e" else "Sleeper"} did not answer ({e_})')
        except Exception as e_: print('other sites: fetch unavailable',e_)
    try:
        _pc=json.load(open('proj_compare.json')) if os.path.exists('proj_compare.json') else {}
        saved=_pc.get('weeks',{}).get(str(NEXT),{}) if _pc.get('season')==SEASON else {}
    except Exception: saved={}
    n_={'e':[0,0],'s':[0,0]}
    for p in players:
        if p['nw']!=NEXT or p['p'] not in POS: continue
        d_={}
        for k_,idk in (('e','eid'),('s','sid')):
            v_=got[k_].get(p.get(idk)) if p.get(idk) else None
            if v_ is not None: n_[k_][0]+=1
            elif k_ in saved.get(p['id'],{}): v_=saved[p['id']][k_]; n_[k_][1]+=1
            if v_ is not None and v_>0: d_[k_]=float(v_)
        if d_: OTH[p['id']]=d_; p['pe']=r(d_['e'],1) if 'e' in d_ else None; p['ps']=r(d_['s'],1) if 's' in d_ else None
    print(f"other sites, week {NEXT}: ESPN {n_['e'][0]} fetched + {n_['e'][1]} saved, Sleeper {n_['s'][0]} fetched + {n_['s'][1]} saved")
_other_sites()
# next week's projection: a stack of four forecasts (ff_stack.py). Within each position, among the players the FantasyPros
# experts ranked, every source becomes a z-score (spreads above that group's average): BFF's model 30%, the experts' weekly
# rank 10%, Sleeper's projection 30%, ESPN's 30% (re-weighted over the sources that project a player). The k-th strongest
# player gets the k-th highest of the players' average points across BFF, Sleeper and ESPN. Weights chosen on 2020-22; on
# 2023-25 and 2026, which they never saw, the stack ranked players better than ESPN, Sleeper and the FantasyPros consensus and
# missed by fewer points than ESPN and Sleeper (research/bt_sites.py). A site used here must project at least half of the
# group; with neither site, the tested mix of 40% model and 60% experts is used (research/README.md).
from ff_stack import stack as _stack
NSTK={}
for _pos in POS:
    _R=[p for p in players if p['p']==_pos and p['nw']==NEXT and (p['proj'] or 0)>0 and p.get('wkr')]
    if len(_R)<5: continue
    _fin,NSTK[_pos]=_stack([p['proj'] for p in _R],[p['wkr'] for p in _R],[OTH.get(p['id'],{}).get('s') for p in _R],[OTH.get(p['id'],{}).get('e') for p in _R],fallback=WK_W)
    for p,_v in zip(_R,_fin):
        _b=r(float(_v),1); p['adjc']=r(_b-p['proj'],1); p['proj']=_b
        if p['ros'] and p['ros'][0][0]==NEXT: p['ros'][0][2]=_b
print('weekly stack:',NSTK)
for p in players:   # the no-usage cap (above), after the consensus blend so it holds
    c_=NOU.get(p['id'])
    if c_ is None: continue
    p['nou']=1; p['proj']=min(p['proj'] or 0,c_); p['rl']=min(p.get('rl') or 0,c_)
    for row in p['ros']: row[2]=min(row[2],c_)
if NOU: print('no usage this season (projection capped at about 1 point):',', '.join(sorted(p['n'] for p in players if p.get('nou'))))
players.sort(key=lambda p:-(p['proj'] or 0))
# defense vs position, this season to date (PPR points allowed per game) with ranks (1 = allows the fewest)
a26,lg26=dvp_table(SEASON,99); DVP={}
for t in sorted(SC26.team.unique()):
    DVP[t]={}
    for pos in POS:
        if (t,pos) in a26.index: sm,c=a26.loc[(t,pos)]; DVP[t][pos]=[r(sm/c,1),int(c),r(dvp_factor(SEASON,99,t,pos),3)]
for pos in POS:
    order=sorted([t for t in DVP if pos in DVP[t]],key=lambda t:DVP[t][pos][0])
    for k,t in enumerate(order): DVP[t][pos].append(k+1)
from zoneinfo import ZoneInfo
def _i(v):
    try: return 0 if v is None or (isinstance(v,float) and np.isnan(v)) else int(v)
    except Exception: return 0
def box_from_stats(rows):
    """Official-style box score for a finished game, built from nflverse player stats."""
    players=[];cats={};ts={}
    for t,R in rows.groupby('team'):
        P_=[x for x in R.itertuples() if (_i(x.attempts) or _i(x.carries) or _i(x.targets))]
        for x in P_:
            players.append({'n':x.player_display_name,'t':t,'p':x.position,'pc':_i(x.completions),'pa':_i(x.attempts),'py':_i(x.passing_yards),'ptd':_i(x.passing_tds),'int':_i(x.passing_interceptions),
              'ra':_i(x.carries),'ry':_i(x.rushing_yards),'rtd':_i(x.rushing_tds),'rec':_i(x.receptions),'tg':_i(x.targets),'ty':_i(x.receiving_yards),'rectd':_i(x.receiving_tds),
              'fl':_i(getattr(x,'rushing_fumbles_lost',0))+_i(getattr(x,'receiving_fumbles_lost',0))+_i(getattr(x,'sack_fumbles_lost',0))})
        C=[]
        pa=[x for x in P_ if _i(x.attempts)]
        if pa: C.append({'n':'passing','t':f'{t} Passing','l':['C/ATT','YDS','TD','INT','SACKS'],'r':[[x.player_display_name,f"{_i(x.completions)}/{_i(x.attempts)}",str(_i(x.passing_yards)),str(_i(x.passing_tds)),str(_i(x.passing_interceptions)),f"{_i(getattr(x,'sacks_suffered',0))}-{_i(getattr(x,'sack_yards_lost',0))}"] for x in pa],'tot':[]})
        ru=sorted([x for x in P_ if _i(x.carries)],key=lambda x:-_i(x.rushing_yards))
        if ru: C.append({'n':'rushing','t':f'{t} Rushing','l':['CAR','YDS','AVG','TD'],'r':[[x.player_display_name,str(_i(x.carries)),str(_i(x.rushing_yards)),f"{_i(x.rushing_yards)/max(1,_i(x.carries)):.1f}",str(_i(x.rushing_tds))] for x in ru],'tot':[]})
        rc=sorted([x for x in P_ if _i(x.targets)],key=lambda x:-_i(x.receiving_yards))
        if rc: C.append({'n':'receiving','t':f'{t} Receiving','l':['REC','TGTS','YDS','AVG','TD'],'r':[[x.player_display_name,str(_i(x.receptions)),str(_i(x.targets)),str(_i(x.receiving_yards)),f"{_i(x.receiving_yards)/max(1,_i(x.receptions)):.1f}",str(_i(x.receiving_tds))] for x in rc],'tot':[]})
        fu=[p for p in players if p['t']==t and p['fl']]
        if fu: C.append({'n':'fumbles','t':f'{t} Fumbles lost','l':['LOST'],'r':[[p['n'],str(p['fl'])] for p in fu],'tot':[]})
        cats[t]=C
        py=sum(_i(x.passing_yards) for x in pa); ry=sum(_i(x.rushing_yards) for x in ru); to=sum(_i(x.passing_interceptions) for x in pa)+sum(p['fl'] for p in players if p['t']==t)
        ts[t]=[['Passing yards',str(py)],['Rushing yards',str(ry)],['Total yards',str(py+ry)],['Turnovers',str(to)]]
    return {'players':players,'cats':cats,'ts':ts}
GW=gm[(gm.season==SEASON)&(gm.week==NEXT)].sort_values(['gameday','gametime']); LGAMES=[]; LBOX={}
for g in GW.itertuples():
    kick=datetime.datetime.strptime(f"{g.gameday} {g.gametime}","%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo('America/New_York')).isoformat() if isinstance(g.gametime,str) else None
    done=not pd.isna(g.home_score)
    fav=None if pd.isna(g.spread_line) else (f"{g.home_team} -{abs(g.spread_line):g}" if g.spread_line>0 else f"{g.away_team} -{abs(g.spread_line):g}" if g.spread_line<0 else 'Pick em')
    LGAMES.append({'id':g.game_id,'away':g.away_team,'home':g.home_team,'as':None if not done else int(g.away_score),'hs':None if not done else int(g.home_score),
                   'state':'post' if done else 'pre','detail':'Final' if done else None,'kick':kick,'venue':g.stadium if isinstance(g.stadium,str) else None,'odds':fav,'ou':None if pd.isna(g.total_line) else float(g.total_line)})
    if done:
        rows=S26[S26.game_id==g.game_id]; LBOX[g.game_id]=box_from_stats(rows)
from ff_news import build_news
REL={p['id'] for p in players if (p.get('prev') or 0)>=6 or (p.get('fpg') or 0)>=6 or (p.get('role') or 'X9')[-1] in '12'}
NEWS=build_news(SEASON,REL)
try:
    from news_update import build_news as collect_news
    HEAD=collect_news()[0]
except Exception as e:
    print('headlines unavailable:',e); HEAD=None
# ---- projection history: each player's projection is refreshed every run until his game kicks off, then it stays frozen
PI_POS={p['id']:p['p'] for p in players}
HP='proj_history.json'
try: H=json.load(open(HP)) if os.path.exists(HP) else {}
except Exception: H={}
HS=H.setdefault(str(SEASON),{})
for p in players:
    if p['nw']==NEXT and p.get('proj') is not None: HS.setdefault(str(NEXT),{})[p['id']]=[p['proj'],p.get('rpg') or 0]
json.dump(H,open(HP,'w'),separators=(',',':'))
# ---- accuracy of the frozen projections against what actually happened, week by week
ACC=[]
for wk,pr in sorted(HS.items(),key=lambda x:int(x[0])):
    act=S26[S26.week==int(wk)].set_index('player_id').fp
    rows=[(v[0],float(act[pid]),PI_POS.get(pid)) for pid,v in pr.items() if pid in act.index and v[0] is not None and v[0]>0]
    if len(rows)<30: continue
    dfa=pd.DataFrame(rows,columns=['p','a','pos']); rk=[spearmanr(x.p,x.a).correlation for _,x in dfa.groupby('pos') if len(x)>=10]
    ACC.append({'wk':int(wk),'n':len(dfa),'mae':r(float((dfa.p-dfa.a).abs().mean()),2),'rank':r(float(np.nanmean(rk)),3) if rk else None})
# ---- head to head with ESPN's and Sleeper's public projections (saved before each game by proj_compare.py, frozen at
# kickoff): every source graded on the same players, weeks whose games are all final
CMP=None
try:
    _PC=json.load(open('proj_compare.json')) if os.path.exists('proj_compare.json') else {}
    if _PC.get('season')==SEASON:
        _fin={int(w_) for w_,G_ in SC26.groupby('week') if G_.pts.notna().all()}; _rows=[]
        for wk_,M_ in _PC.get('weeks',{}).items():
            if int(wk_) not in _fin: continue
            act=S26[S26.week==int(wk_)].set_index('player_id').fp
            for pid_,v_ in M_.items():
                if pid_ in act.index and v_.get('b') is not None and v_.get('e') is not None and v_.get('s') is not None:
                    _rows.append((int(wk_),v_.get('p'),float(act[pid_]),float(v_['b']),float(v_['o']) if v_.get('o') is not None else np.nan,float(v_['e']),float(v_['s']),float(v_['r']) if v_.get('r') else np.nan))
        if len(_rows)>=100:
            _C=pd.DataFrame(_rows,columns=['wk','pos','a','b','o','e','s','r'])
            def _rk(col,neg=False):
                v_=[spearmanr(-x[col] if neg else x[col],x.a).correlation for _,x in _C[_C[col].notna()].groupby(['wk','pos']) if len(x)>=10]
                return r(float(np.nanmean(v_)),3) if v_ else None
            CMP={'weeks':sorted(int(w_) for w_ in _C.wk.unique()),'n':int(len(_C)),
                 'src':{k_:{'mae':r(float((_C[c_]-_C.a).abs().mean()),2) if k_!='fp' else None,'rank':_rk(c_,k_=='fp')} for k_,c_ in (('bff','b'),('bff_model','o'),('espn','e'),('sleeper','s'),('fp','r'))}}
            print('head to head (weeks',CMP['weeks'],'):',CMP['src'])
except Exception as e_: print('head-to-head grading skipped:',e_)
LIVE={'week':NEXT,'at':datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='minutes'),'src':'official stats','games':LGAMES,'box':LBOX}
_KX={}
for _x in gm[gm.season==SEASON].itertuples():
    _k=datetime.datetime.strptime(f"{_x.gameday} {_x.gametime}","%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo('America/New_York')).isoformat() if isinstance(_x.gametime,str) else (str(_x.gameday) if isinstance(_x.gameday,str) else None)
    _sp=None if pd.isna(_x.spread_line) else float(_x.spread_line); _to=None if pd.isna(_x.total_line) else float(_x.total_line)
    _KX[(int(_x.week),_x.home_team)]=(_k,None if _sp is None else -_sp,_to); _KX[(int(_x.week),_x.away_team)]=(_k,_sp,_to)
SCHED={t:[[int(g.week),g.opp,int(g.home) if g.home==g.home else 0,r(g.it,1),None if pd.isna(g.pts) else int(g.pts)]+list(_KX.get((int(g.week),t),(None,None,None))) for g in SC26[SC26.team==t].sort_values('week').itertuples()] for t in SC26.team.unique()}
# stadium ids learned by the live job (for real stadium photos on every game, any week)
try: VENUES=json.load(open('live.json')).get('venues') or {}
except Exception: VENUES={}
OUT={'asof':{'season':SEASON,'phase':PHASE,'sched':bool(SCHED_KNOWN),'last_week':LAST,'next_week':NEXT,'built':datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d'),'depth':str(dc.dt.max())[:10],'ecr':ECR_DATE,'stk':NSTK},
     'players':players,'cmp':CMP,'live':LIVE,'news':NEWS,'headlines':HEAD,'ph':HS.get(str(NEXT),{}),'acc':ACC,'trendsval':json.load(open('trends_val.json')) if os.path.exists('trends_val.json') else None,'dvp':DVP,'lgpos':{p:r(lg26.get(p,np.nan),1) for p in POS},'sched':SCHED,'byes':byes,'venues':VENUES,'model':{'test':res,'range':RNG,'qs':QS,'posavg':{k:r(v,1) for k,v in POSAVG.items()},'train':[min(TRAIN),max(TRAIN)],'test_season':TEST,'hist':[min(HIST5),max(HIST5)],'ew_h':EW_H,'v':5,'rows':int(len(DH))}}
def clean(o):
    if isinstance(o,float) and (o!=o or abs(o)==float('inf')): return None
    if isinstance(o,(np.floating,)): return clean(float(o))
    if isinstance(o,(np.integer,)): return int(o)
    if isinstance(o,dict): return {str(k):clean(v) for k,v in o.items()}
    if isinstance(o,(list,tuple)): return [clean(v) for v in o]
    return o
json.dump(clean(OUT),open('ff_data.json','w'),separators=(',',':'),allow_nan=False)
print('players',len(players),'| next week',NEXT,'| json KB',os.path.getsize('ff_data.json')//1024,flush=True)
for p in players[:12]: print(f"{p['n']:24s} {p['p']} {p['t']} wk{p['nw']} vs {p['opp']} proj {p['proj']} (fpg {p['fpg']}, xfpg {p['xfpg']}, it {p['it']}, dvp {p['dvp']}) role {p['role']} inj {p['inj']}")
