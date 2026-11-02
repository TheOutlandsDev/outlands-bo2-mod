"""Independent validation of private native humanization receipts; no client claims."""
import re
from ai.bot_settings import selected_preset
from ai.rivals import aim_blend, combat_tuning, load_profiles

ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
METRICS = ('stage','tick','bots','tuned','difficulty_calls','aim_calls','look_calls',
           'repositions','arrivals','objective_holds','yaw_samples','large_yaw_changes','peak_yaw_degrees')


def assess_humanization(text, enabled, roaming, mode, preset="mixed"):
    settings = selected_preset(preset)
    engine = settings["engine"]
    controls = [str(round(engine["yaw_speed"] * 100)), str(engine["reaction_min_ms"]), str(engine["reaction_max_ms"])]
    catalog = load_profiles()
    metrics, profiles, traces, relocations, native = [], {}, [], [], []
    bad, hq_patrol = 0, 0
    for line in ANSI.sub('',text).splitlines():
        f=line.strip().split('|')
        if f[0] == 'OUTLANDS_HUMAN_PROFILE_V1':
            try:
                if len(f)!=9 or f[1] not in ('0','1') or not re.fullmatch(r'[0-9]{1,2}',f[2]) or int(f[2])>17 or f[3] not in catalog:
                    raise ValueError('Invalid profile')
                expected=combat_tuning(catalog[f[3]]['tier'],preset)
                if f[4]!=expected['difficulty'] or list(map(int,f[5:]))!=[expected[k] for k in ('converge_ms','correction_rate','aim_error','smooth_ms')]:
                    raise ValueError('Native combat parameters differ')
                profiles[(int(f[1]),int(f[2]))]=expected
            except (ValueError,TypeError): bad+=1
        elif f[0] == 'OUTLANDS_HUMAN_METRICS_V1':
            if len(f)!=14 or not all(re.fullmatch(r'[0-9]{1,9}',x) for x in f[1:]):bad+=1;continue
            m=dict(zip(METRICS,map(int,f[1:])))
            if m['stage'] not in (0,1) or any(m[k]>18 for k in ('bots','tuned','objective_holds','yaw_samples','large_yaw_changes')) or m['peak_yaw_degrees']>180 or m['large_yaw_changes']>m['yaw_samples']:
                bad+=1;continue
            metrics.append(m)
        elif f[0] == 'OUTLANDS_HUMAN_AIM_V1':
            try:
                if len(f)!=8 or not all(re.fullmatch(r'[0-9]{1,10}',x) for x in f[1:]):raise ValueError('Invalid aim trace')
                stage,slot,elapsed,smooth,blend,raw,filtered=map(int,f[1:])
                wanted=aim_blend(elapsed,smooth)
                if stage not in (0,1) or slot>17 or abs(blend-int(wanted*1000))>1 or raw<=100 or not 0<=filtered<raw or abs(filtered-raw*wanted*wanted)>max(4,raw*0.005):
                    raise ValueError('Filtered step differs')
                traces.append((stage,slot,smooth))
            except ValueError:bad+=1
        elif f[0] == 'OUTLANDS_HUMAN_NATIVE_V1':
            if len(f)!=5 or f[1] not in ('0','1') or f[2:]!=controls:bad+=1;continue
            native.append(int(f[1]))
        elif f[0] == 'OUTLANDS_HUMAN_ROAM_V1':
            try:
                if len(f)!=6 or not all(re.fullmatch(r'[0-9]{1,9}',x) for x in f[1:]):raise ValueError('Invalid relocation')
                slot,travel,target,cause,dwell=map(int,f[1:])
                if slot>17 or not settings['guard']['min_step_units']**2<=travel<=100000000 or target>2359296 or cause not in (0,1,2) or (cause==1 and dwell<settings['guard']['hold_min_ms']):raise ValueError('Invalid relocation bounds')
                relocations.append({'cause':cause,'dwell_ms':dwell})
            except ValueError:bad+=1
        elif f[0] == 'OUTLANDS_HQ_PATROL_V1':
            if len(f)!=4 or not re.fullmatch(r'[0-9]{1,2}',f[1]) or int(f[1])>17 or f[2:]!=['1','1']:bad+=1;continue
            hq_patrol+=1
    reasons=[]
    if bad:reasons.append('Malformed or non-replayable humanization evidence')
    last_tick={}
    for m in metrics:
        if m['tick']<=last_tick.get(m['stage'],-1):bad+=1
        last_tick[m['stage']]=m['tick']
    if bad and not reasons:reasons.append('Malformed or non-replayable humanization evidence')
    settled=[m for m in metrics if m['bots']==16 and m['tick']>=20]
    if len(settled)<10:reasons.append('Incomplete native humanization observation')
    if enabled:
        stages={m['stage'] for m in settled}
        for stage in stages:
            rows=[m for m in settled if m['stage']==stage]
            if sum(s==stage for s,_ in profiles)<12 or any(m['tuned']!=16 for m in rows):reasons.append('Incomplete native combat profiles')
            if stage not in native or any(max(m[k] for m in rows)==0 for k in ('difficulty_calls','aim_calls','look_calls')):reasons.append('Native combat hooks or controls not exercised')
            if len({slot for s,slot,_ in traces if s==stage})<4:reasons.append('Too few actual filtered native combat steps')
        if any((stage,slot) not in profiles or smooth!=profiles[(stage,slot)]['smooth_ms'] for stage,slot,smooth in traces):reasons.append('Aim traces not bound to observed profile')
        if len({p['converge_ms'] for p in profiles.values()})<2:reasons.append('No observed combat skill variation')
        if mode=='hq' and not hq_patrol:reasons.append('Owned HQ attacker patrol preservation not observed')
    elif profiles or native or traces or any(m['tuned'] or m['difficulty_calls'] or m['aim_calls'] or m['look_calls'] for m in metrics):
        reasons.append('Disabled humanization changed native combat')
    if roaming:
        if not any(x['cause']==1 for x in relocations):reasons.append('No accepted guard reposition after an arrived hold')
    elif relocations or any(m['repositions'] or m['arrivals'] for m in metrics):reasons.append('Disabled guard roaming changed positions')
    return {'passed':not reasons,'reasons':reasons,'native_profiles':len(profiles),'filtered_native_steps':len(traces),
            'arrived_guard_repositions':sum(x['cause']==1 for x in relocations),'hq_native_patrol_proofs':hq_patrol,
            'metrics':metrics,'visual_aim_smoothness_accepted':False,'human_navigation_quality_accepted':False}


def assess_streaks(text):
    """A charged synthetic fixture proves native deployment/retrieval, not earning."""
    grants=[];landed=[];captured=[];supplies=[];routes=[];radii=[];bad=0
    for line in ANSI.sub('',text).splitlines():
        f=line.strip().split('|')
        try:
            if f[0]=='OUTLANDS_STREAK_FIXTURE_V1':
                if len(f)!=3 or f[1] not in ('grant','landed','captured') or not re.fullmatch(r'[0-9]{1,2}',f[2]):raise ValueError('Bad fixture')
                value=int(f[2])
                if f[1]=='captured':
                    if value not in (0,1):raise ValueError('Bad owner result')
                    captured.append(value)
                else:
                    if value>17:raise ValueError('Bad slot')
                    (grants if f[1]=='grant' else landed).append(value)
            elif f[0]=='OUTLANDS_STREAK_SUPPLY_V1':
                if len(f)!=5 or not all(re.fullmatch(r'[0-9]{1,9}',x) for x in f[1:]):raise ValueError('Bad supply proof')
                slot,before,after,age=map(int,f[1:])
                if slot>17 or not 0<=after<=before<=99:raise ValueError('Invalid charge delta')
                supplies.append((slot,before,after,age))
            elif f[0]=='OUTLANDS_STREAK_RETRIEVE_V1':
                if len(f)!=3 or not all(re.fullmatch(r'[0-9]{1,9}',x) for x in f[1:]):raise ValueError('Bad route')
                slot,distance=map(int,f[1:])
                if slot>17 or distance>100000000:raise ValueError('Bad route bounds')
                routes.append((slot,distance))
            elif f[0]=='OUTLANDS_STREAK_USE_RADIUS_V1':
                if len(f)!=2 or not re.fullmatch(r'[0-9]{1,6}',f[1]) or not 256<=int(f[1])<=65536:raise ValueError('Invalid native use radius')
                radii.append(int(f[1]))
        except ValueError:bad+=1
    reasons=[]
    if bad:reasons.append('Malformed streak evidence')
    if len(grants)!=1 or landed!=grants or captured!=[1]:reasons.append('Native package landing and owner capture not observed')
    slot=grants[0] if len(grants)==1 else -1
    if not any(s==slot and before>after and age>5000 for s,before,after,age in supplies):reasons.append('No charged marker consumed after the native spawn-only window')
    if len(radii)!=1 or not any(s==slot and distance>radii[0] for s,distance in routes):reasons.append('Owner retrieval goal beyond native use range not observed')
    return {'passed':not reasons,'reasons':reasons,'synthetic_inventory_fixture':True,'organic_earning_accepted':False,'native_owner_capture':captured==[1]}


def assess_loadouts(text):
    """Replay native pool diversity and compare requested/actually carried variants."""
    histories={};built=set();equipped=set();bases=set();variants=set();attached=set();respawns=0;bad=0
    enum=re.compile(r'[A-Z0-9_]{1,64}\Z');weapon=re.compile(r'[a-z0-9_]+(?:\+[a-z0-9_]+){0,8}\Z')
    allowed={'custom'+str(i) for i in range(5)}|{'class_'+x for x in ('assault','smg','lmg','cqb','sniper')}
    for line in ANSI.sub('',text).splitlines():
        f=line.strip().split('|')
        try:
            if f[0]=='OUTLANDS_LOADOUT_BUILD_V1':
                if len(f)!=6 or f[1] not in ('0','1') or not f[2].isascii() or not f[2].isdecimal() or int(f[2])>17 or f[3] not in ('0','1','2','3','4') or not enum.fullmatch(f[4]):raise ValueError('Invalid generator receipt')
                pool=f[5].split(',');slot=(int(f[1]),int(f[2]));class_id=int(f[3]);history=histories.setdefault(slot,{})
                if not 1<=len(pool)<=128 or len(set(pool))!=len(pool) or any(not enum.fullmatch(x) for x in pool):raise ValueError('Invalid native primary pool')
                fresh=[x for x in pool if x not in history or history[x]==class_id]
                if f[4] not in (fresh or pool):raise ValueError('Native construction repeated a primary despite available alternatives')
                history[f[4]]=class_id;built.add(slot)
            elif f[0]=='OUTLANDS_LOADOUT_EQUIP_V1':
                # The complete line is marker plus seven fields.
                if len(f)!=8 or f[1] not in ('0','1') or not all(re.fullmatch(r'[0-9]{1,6}',f[i]) for i in (2,3)) or int(f[2])>17 or f[4] not in allowed or f[7]!='1':raise ValueError('Invalid equip receipt')
                expected,actual=f[5],f[6]
                if len(expected)>128 or len(actual)>128 or not weapon.fullmatch(expected) or not weapon.fullmatch(actual):raise ValueError('Invalid native weapon')
                a=expected.split('+');b=actual.split('+')
                if a[0]!=b[0] or set(a[1:])!=set(b[1:]) or len(set(a))!=len(a) or len(set(b))!=len(b):raise ValueError('Carried attachments differ from native class')
                equipped.add((int(f[1]),int(f[2])));bases.add(b[0]);key=b[0]+'+'+'+'.join(sorted(b[1:]));variants.add(key)
                if len(b)>1:attached.add(key)
                if int(f[3])>0:respawns+=1
        except ValueError:bad+=1
    reasons=[]
    if bad:reasons.append('Malformed or non-replayable native loadout evidence')
    if len(built)<8 or len(equipped)<12 or respawns<8:reasons.append('Insufficient native class generation or actual respawn equipment')
    if len(bases)<8 or len(variants)<10 or len(attached)<6:reasons.append('Insufficient carried gun and attachment variety')
    return {'passed':not reasons,'reasons':reasons,'native_bots_constructed':len(built),'native_bots_equipped':len(equipped),'respawn_equip_receipts':respawns,'distinct_carried_guns':len(bases),'distinct_carried_variants':len(variants),'distinct_attached_variants':len(attached),'human_unlocks_modified':False}
