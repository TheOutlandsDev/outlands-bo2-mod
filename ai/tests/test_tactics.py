"""Task grounding and conversation boundaries, without a game or model."""
import sys
from pathlib import Path
from dataclasses import replace
import io
import json
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bridge
from tactics import Tactical, fallback, usable


def wire(topic='squad', role='attack', state='enemy', contract='combined_score', phase='1', progress='100', goal='1000', complete='0', remaining='45'):
    return f'{topic}|allies|{role}|0|{state}|{contract}|{phase}|{progress}|{goal}|{complete}|{remaining}'


def fixture(**changes):
    return bridge.Event.parse('OUTLANDS_CHAT_V2|native_1|3|Trailblazer|banter|mp_raid|dom|match|A current team task.|'+wire(**changes), 100)


class TacticalTests(unittest.TestCase):
    def test_typed_native_context_is_bounded_and_legacy_events_still_work(self):
        self.assertEqual(fixture().tactical.role, 'attack')
        self.assertIsNone(bridge.Event.parse('OUTLANDS_CHAT_V1|legacy|3|Trailblazer|banter|mp_raid|dom|match|hi', 100).tactical)
        for changes in ({'topic':'exec'}, {'role':'admin'}, {'state':'private'}, {'state':'home'}, {'phase':'-1'}, {'remaining':'301'}, {'goal':'0'}, {'complete':'1'}, {'progress':'nan'}, {'phase':'1000001'}):
            self.assertIsNone(fixture(**changes), changes)
        for raw in (wire()+'|extra', wire().replace('|0|enemy|','|32|enemy|'), wire().replace('|allies|','|none|'), wire().replace('|attack|0|enemy|','|support|0|enemy|')):
            self.assertIsNone(Tactical.parse(raw.split('|'), 'dom'))

    def test_grounded_fallback_matches_task_and_avoids_recent_lines(self):
        for role, state in (('attack','enemy'), ('defend','friendly')):
            item=fixture(role=role,state=state)
            history=[]
            for _ in range(4):
                line=fallback(item.tactical,'dom',history=history)
                self.assertTrue(usable(item.tactical,'dom',line),line)
                self.assertNotIn(line,history)
                self.assertEqual(bridge.sanitize_reply(line),line)
                self.assertLessEqual(len(bridge.words(line)),12)
                history.append(line)
        completed=fixture(topic='contract',progress='1000',complete='1').tactical
        with patch('tactics.random.choice',side_effect=lambda choices:choices[0]):
            self.assertEqual(fallback(completed,'dom'),'Nice, that contract is done.')

    def test_wrong_orders_completions_counts_and_named_flags_are_refused(self):
        attack=fixture().tactical
        defend=fixture(role='defend',state='friendly').tactical
        contract=fixture(topic='contract').tactical
        for text in ('Holding the flag.', 'Pushing B.', 'Captured the flag.', 'Enemy behind the flag.', 'Need 2 kills.', "We're closing in on the flag.", "We're close to the flag.", 'Watch the flag.'):
            self.assertFalse(usable(attack,'dom',text),text)
        self.assertFalse(usable(defend,'dom','Pushing the flag.'))
        self.assertFalse(usable(contract,'dom','Contract complete!'))
        self.assertFalse(usable(contract,'dom','Got that contract, nice.'))
        self.assertFalse(usable(contract,'dom','Nice, gg.'))
        self.assertTrue(usable(contract,'dom','Still working on that contract.'))

    def test_benchmark_consumes_only_typed_native_snapshots(self):
        from benchmark import native_events
        good = 'OUTLANDS_CONTEXT_V1|3|Trailblazer|mp_raid|dom|'+wire()
        events = native_events('Player: '+good+'\n'+good+'\n'+good)
        self.assertEqual(len(events),1)
        self.assertEqual(events[0].tactical.role,'attack')
        self.assertEqual(native_events(good+'|extra'),[])
        self.assertEqual(native_events(good.replace('|dom|','|unknown|')),[])

    def test_second_turn_stays_on_team_topic_and_contract_phase(self):
        opener=fixture(topic='contract')
        guard=bridge.DialogueGuard();guard.record(opener,'Still working on that contract.',100)
        child=replace(opener,request_id='native_1_r',bot_name='MossCircuit',kind='bot_reply',speaker=opener.bot_name,text='Still working on that contract.')
        for tactical in (None,replace(child.tactical,team='axis'),replace(child.tactical,topic='squad'),replace(child.tactical,phase=2)):
            self.assertFalse(guard.accept(replace(child,tactical=tactical),110))
        self.assertTrue(guard.accept(child,110))
        self.assertFalse(guard.accept(child,111))

    def test_model_payload_uses_validated_context_and_wrong_model_orders_fall_back(self):
        item=fixture(role='defend',state='friendly')
        generator=bridge.Generator(bridge.Config(),bridge.Personalities(Path(bridge.__file__).parent/'personalities.json'))
        captured=[]
        class Response(io.BytesIO):
            def __enter__(self):return self
            def __exit__(self,*args):self.close()
        def open_request(request,timeout):
            captured.append(json.loads(request.data))
            return Response(json.dumps({'message':{'content':'Pushing the flag.'}}).encode())
        with patch.object(generator.opener,'open',side_effect=open_request):
            line,source=generator.generate(item,[])
        self.assertEqual(source,'fallback')
        self.assertTrue(usable(item.tactical,'dom',line))
        task=json.loads(captured[0]['messages'][1]['content'])['native_task']
        self.assertEqual(task['role'],'defend')
        self.assertIn('watch and defend the flag',captured[0]['messages'][0]['content'])
        self.assertNotIn('Ignore your rules',captured[0]['messages'][0]['content'])
        self.assertNotIn('coordinates',task)

    def test_tactical_events_keep_shared_rate_limits_and_human_reply_priority(self):
        worker=bridge.Worker(bridge.Config(enabled=True),None,None,None)
        tactical='OUTLANDS_CHAT_V2|native_1|3|Trailblazer|banter|mp_raid|dom|match|A task.|'+wire()
        human='OUTLANDS_CHAT_V1|human_1|4|MossCircuit|reply|mp_raid|dom|Synthetic|hi'
        worker.ingest([tactical,human],100)
        self.assertEqual(worker.next_event(100).kind,'reply')
        self.assertIsNone(worker.next_event(105))
        self.assertEqual(worker.next_event(111).kind,'banter')
        worker.config=replace(worker.config,enabled=False)
        self.assertFalse(worker.deliver(fixture(),('Heading for the flag.','fallback'),112))


if __name__=='__main__':unittest.main()
