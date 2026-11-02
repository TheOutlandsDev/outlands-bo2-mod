"""Parse read-only all-bot quality observations; never equate telemetry with feel."""
from __future__ import annotations
import math,re

FIELDS=('alive_ms','moving_ms','threat_ms','visible_ms','on_target_ms','objective_ms','idle_travel_ms','shots','hits','damage','first_shots','shot_latency_sum','first_hits','hit_latency_sum','distance_units','crowded_ms','goal_changes','kills','deaths')
ANSI=re.compile(r'\x1b\[[0-9;]*[A-Za-z]')

def percentile(values, fraction):
    if not values:return None
    values=sorted(values);return values[max(0,math.ceil(len(values)*fraction)-1)]

def assess_quality(text):
    latest={};latencies={'shot':[],'hit':[]};traces={};bad=0;rows=0
    for raw in ANSI.sub('',text).splitlines():
        f=raw.strip().split('|')
        if f[0]=='OUTLANDS_QUALITY_V1':
            if len(f)!=24 or any(not re.fullmatch(r'[0-9]{1,10}',v) for v in f[1:]):bad+=1;continue
            stage,tick,slot,elapsed,*values=map(int,f[1:]);key=(stage,slot)
            if stage not in (0,1) or not 0<=slot<18 or tick<1 or elapsed<1:bad+=1;continue
            d=dict(zip(FIELDS,values));previous=latest.get(key)
            if any(d[k]>d['alive_ms'] for k in ('moving_ms','threat_ms','objective_ms','idle_travel_ms','crowded_ms')) or d['visible_ms']>d['threat_ms'] or d['on_target_ms']>d['visible_ms'] or d['alive_ms']>elapsed or d['first_shots']>d['shots'] or d['first_hits']>d['hits']:bad+=1;continue
            if previous and (tick<=previous['tick'] or elapsed<=previous['elapsed'] or any(d[k]<previous[k] for k in FIELDS)):bad+=1;continue
            latest[key]=dict(d,tick=tick,elapsed=elapsed);rows+=1
        elif f[0]=='OUTLANDS_QUALITY_LATENCY_V1':
            if len(f)!=6 or f[1] not in ('0','1') or not re.fullmatch(r'[0-9]{1,2}',f[2]) or int(f[2])>17 or f[3] not in latencies or not re.fullmatch(r'[0-9]{1,7}',f[4]) or not re.fullmatch(r'[1-9][0-9]{0,6}',f[5]):bad+=1;continue
            key=(int(f[1]),int(f[2]),f[3]);sequence=int(f[5]);bucket=traces.setdefault(key,{})
            if sequence in bucket:bad+=1;continue
            bucket[sequence]=int(f[4])
    for (stage,slot),sample in latest.items():
        for kind,count,total in (('shot','first_shots','shot_latency_sum'),('hit','first_hits','hit_latency_sum')):
            bucket=traces.get((stage,slot,kind),{})
            wanted=sample[count]
            if wanted>100000 or any(n not in bucket for n in range(1,wanted+1)):bad+=1;continue
            selected=[bucket[n] for n in range(1,wanted+1)]
            if sum(selected)!=sample[total]:bad+=1;continue
            latencies[kind].extend(selected)
    totals={k:sum(v[k] for v in latest.values()) for k in FIELDS};alive=totals['alive_ms'];visible=totals['visible_ms'];reasons=[]
    if bad:reasons.append('Malformed, non-monotonic or impossible AI quality evidence')
    if len(latest)<12 or rows<60 or max((v['elapsed'] for v in latest.values()),default=0)<60000:reasons.append('Insufficient bot quality observation window')
    if totals['shots']<20 or totals['hits']<10 or visible<1000:reasons.append('Insufficient observed native bullet combat')
    for kind,count in (('shot','first_shots'),('hit','first_hits')):
        if len(latencies[kind])<totals[count]:reasons.append('Missing independently recorded first-event latencies')
    def ratio(a,b):return round(a/b,4) if b else None
    return {'passed':not reasons,'reasons':reasons,'bots_observed':len(latest),'records':rows,'totals':totals,
            'moving_alive_fraction':ratio(totals['moving_ms'],alive),'objective_zone_alive_fraction':ratio(totals['objective_ms'],alive),
            'stationary_travel_candidate_fraction':ratio(totals['idle_travel_ms'],alive),'crowded_moving_fraction':ratio(totals['crowded_ms'],totals['moving_ms']),
            'aim_aligned_visible_fraction':ratio(totals['on_target_ms'],visible),
            'bullet_hit_events_per_discharge':ratio(totals['hits'],totals['shots']),
            'first_observed_shot_latency_ms':{'samples':len(latencies['shot']),'median':percentile(latencies['shot'],.5),'p90':percentile(latencies['shot'],.9)},
            'first_observed_damage_latency_ms':{'samples':len(latencies['hit']),'median':percentile(latencies['hit'],.5),'p90':percentile(latencies['hit'],.9)},
            'human_gameplay_accepted':False,'hit_ratio_is_accuracy':False,'objective_zone_is_capture_credit':False,'stationary_candidate_is_proven_stuck':False,
            'latency_is_true_reaction_time':False,'latency_note':'First-event samples are censored by observer cadence, target switching and survival; compare with activity and never alone.'}
