#!/usr/bin/env python3
"""Generate synthetic numbered conversations, never connecting to a game or RCON."""
from dataclasses import replace
from pathlib import Path
import argparse
import json
import time
from bridge import Config, Event, Generator, Personalities, sanitize_reply, model_reply_usable
from tactics import Tactical, usable


def run(generator):
    aliases=('NightLedger','CopperWren','StaticBloom','RiftRunner')
    cases=(('completed',Tactical('contract','allies','none',-1,'none','combined_score',1,1000,1000,1,100),'React to your verified team contract completion.'),
           ('in_progress',Tactical('contract','allies','none',-1,'none','team_points',2,2,12,0,100),'A short comment about your ongoing team contract.'),
           ('rough_game',None,'A casual comment about your own rough scoreboard.'))
    results=[]
    for index,(name,tactical,hint) in enumerate(cases):
        history=[];previous='match';text=hint;guard=[]
        for turn,alias in enumerate(aliases,1):
            e=Event('fixture'+str(index)+('' if turn==1 else '_r'+str(turn)),turn,alias,'banter' if turn==1 else 'bot_reply','mp_raid','dom',previous,text,time.monotonic(),tactical,turn,4)
            context={'own_public_scoreboard':{'kills':1,'deaths':6,'score':100}}
            began=time.monotonic();line,source=generator.generate(e,history,context)
            safe=bool(line) and sanitize_reply(line)==line and model_reply_usable(e,line) and usable(tactical,'dom',line,responding=turn>1) and line.casefold() not in {x.casefold() for x in history[-4:]}
            guard.append(safe)
            results.append({'case':name,'turn':turn,'alias':alias,'text':line,'source':source,'seconds':round(time.monotonic()-began,2),'passed':safe})
            history.append(line);previous,text=alias,line
    return {'passed':all(x['passed'] for x in results),'synthetic_only':True,'posted_to_game':False,'model_lines':sum(x['source']=='ollama' for x in results),'results':results}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--mode',choices=('ollama','fallback'),default='fallback');args=parser.parse_args()
    base=Path(__file__).resolve().parent
    config=replace(Config.load(base/'config.example.json'),enabled=True,mode=args.mode)
    report=run(Generator(config,Personalities(base/'personalities.json')))
    print(json.dumps(report,indent=2));return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
