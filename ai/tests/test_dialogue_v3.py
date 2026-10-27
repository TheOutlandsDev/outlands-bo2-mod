"""Numbered conversations remain bounded and grounded without repeated nouns."""
from dataclasses import replace
import io
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bridge
from tactics import Tactical, usable

TASK=Tactical('contract','allies','none',-1,'none','combined_score',1,1000,1000,1,40)

def event(turn=1,limit=4,bot='NightLedger',speaker='match',text='A verified completed contract.',tactical=TASK):
    request='chain' if turn==1 else 'chain_r'+str(turn)
    return bridge.Event(request,turn,bot,'banter' if turn==1 else 'bot_reply','mp_raid','dom',speaker,text,100+turn*12,tactical,turn,limit)


def wire(e):
    t=e.tactical
    fields=[e.request_id,e.slot,e.bot_name,e.kind,e.map_name,e.gametype,e.speaker,e.text,t.topic,t.team,t.role,t.target,t.state,t.contract,t.phase,t.progress,t.goal,t.complete,t.remaining,e.turn,e.turn_limit]
    return 'OUTLANDS_CHAT_V3|'+'|'.join(map(str,fields))


class DialogueV3Tests(unittest.TestCase):
    def test_four_turns_require_each_exact_previous_message_and_stop(self):
        guard=bridge.DialogueGuard();current=event()
        self.assertEqual(bridge.Event.parse(wire(current),112),current)
        for turn,bot,line in ((2,'CopperWren','That went alright.'),(3,'StaticBloom','You sound surprised.'),(4,'RiftRunner','A little, yeah.')):
            previous_line='Nice, that contract is done.' if turn==2 else current_line
            guard.record(current,previous_line,100+turn*12)
            child=event(turn,bot=bot,speaker=current.bot_name,text=previous_line)
            self.assertTrue(guard.accept(child,101+turn*12))
            self.assertFalse(guard.accept(child,102+turn*12))
            current,current_line=child,line
        guard.record(current,current_line,160)
        self.assertEqual(guard.openers,{})
        self.assertIsNone(bridge.Event.parse(wire(event(5)),170))

    def test_skips_changed_limits_wrong_team_and_forged_inputs_do_not_consume_parent(self):
        first=event();line='Nice, that contract is done.'
        guard=bridge.DialogueGuard();guard.record(first,line,100)
        child=event(2,bot='CopperWren',speaker=first.bot_name,text=line)
        for bad in (replace(child,turn=3,request_id='chain_r3'),replace(child,turn_limit=3),replace(child,text='Invented line.'),replace(child,tactical=replace(TASK,team='axis')),replace(child,tactical=replace(TASK,phase=2))):
            self.assertFalse(guard.accept(bad,112))
        self.assertTrue(guard.accept(child,112))
        for bad in (wire(child)+'|extra',wire(child).replace('chain_r2','chain_r2_r2'),wire(child).replace('|2|4','|2|9')):
            self.assertIsNone(bridge.Event.parse(bad,112))

    def test_followups_can_acknowledge_without_repeating_task_but_not_invent_events(self):
        for line in ('Fair, same here.',"Yeah, worth a try.",'You sound surprised.'):
            self.assertTrue(usable(TASK,'dom',line,responding=True))
        unfinished=replace(TASK,complete=0,progress=1)
        self.assertFalse(usable(unfinished,'dom','Contract complete!',responding=True))
        defend=replace(TASK,topic='squad',role='defend',target=0,state='friendly')
        self.assertFalse(usable(defend,'dom','Pushing the flag.',responding=True))
        self.assertFalse(usable(TASK,'dom','Captured B.',responding=True))
        self.assertFalse(usable(TASK,'dom','Need 2 kills.',responding=True))

    def test_rough_scoreboard_banter_rejects_unrelated_model_scene(self):
        e=replace(event(),tactical=None)
        context={"own_public_scoreboard":{"kills":1,"deaths":6,"score":100}}
        self.assertFalse(bridge.scoreboard_reply_usable(e,context,"Brewed some tea. Let's outlast the rest."))
        self.assertTrue(bridge.scoreboard_reply_usable(e,context,"My aim took the scenic route."))
        self.assertTrue(bridge.scoreboard_reply_usable(replace(e,kind="reply"),context,"Appreciate it."))

    def test_middle_turn_can_ask_question_but_final_turn_closes(self):
        middle=event(2,bot='CopperWren',speaker='NightLedger',text='Nice, that contract is done.')
        self.assertTrue(bridge.model_reply_usable(middle,'You sound surprised?'))
        self.assertFalse(bridge.model_reply_usable(replace(middle,turn=4),'You sound surprised?'))
        self.assertTrue(bridge.model_reply_usable(replace(middle,turn=4),'A little, yeah.'))

    def test_payload_keeps_personality_and_features_without_claiming_current_squad(self):
        generator=bridge.Generator(bridge.Config(),bridge.Personalities(Path(bridge.__file__).parent/'personalities.json'))
        payloads=[]
        class Opener:
            def open(self,request,timeout):
                payloads.append(json.loads(request.data));return io.BytesIO(b'{"message":{"content":"Fair, same here."}}')
        generator.opener=Opener()
        e=event(2,bot='CopperWren',speaker='NightLedger',text='Nice, that contract is done.')
        self.assertEqual(generator.generate(e,[]),('Fair, same here.','ollama'))
        context=json.loads(payloads[0]['messages'][1]['content'])
        self.assertFalse(context['final_turn']);self.assertEqual(context['conversation_turn'],2)
        self.assertEqual(context['featured_character']['roster'],'Signal Four')
        self.assertNotIn('bot_context',context)
        self.assertIn('personality_traits',context)
        self.assertNotIn('Current response focus:',payloads[0]['messages'][0]['content'])
        self.assertIn('not a request to repeat',context['current_response_focus'])


if __name__=='__main__':unittest.main()
