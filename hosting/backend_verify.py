#!/usr/bin/env python3
"""Run native all-bot integration checks in disposable, network-isolated Docker state.

Default mode prints the test plan. --run creates only tool-labelled resources;
no live container, game profile, tailnet or published port is used. Reports and
raw logs remain private under hosting/logs unless an explicit destination is set.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, asdict
import json
from pathlib import Path
import re
import subprocess
import time
import uuid
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ai'))
from tactics import Tactical
from bridge import Event, ChatAck
LABEL = "org.outlands.backend-verification"
MODES = frozenset(("dm", "tdm", "ctf", "dem", "dom", "koth", "hq", "conf"))
CASE = re.compile(r"(mp_[a-z0-9_]{1,40}):(dm|tdm|ctf|dem|dom|koth|hq|conf)\Z")
FAILURE = re.compile(r"(?:terminal\s+)?script(?:\s+(?:compile|runtime))?\s+error|could not resolve function|unresolved external|unknown function|error compiling", re.I)
NATIVE_FAILURE = re.compile(r"A critical exception occu(?:r|rr)ed!|Exception Code: 0x[0-9a-f]+|Oops! Plutonium ran into a problem", re.I)
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
SCORE_LIMITS = {"tdm": 200, "dm": 60, "conf": 150, "ctf": 6, "dem": 4, "dom": 200, "hq": 500, "koth": 500}
FIELDS = ("stage", "bots", "humans", "alive", "playing", "identities", "roles", "careers", "kills", "deaths", "score", "moved", "prematch", "invalid", "pools", "patrols", "scorelimit")
OBJECTIVE_MODES = frozenset(("ctf", "dem", "dom", "koth", "hq"))
CONTRACT_MODES = MODES - {"dm"}
# V1 is retained for private evidence from earlier versions. Feature acceptance
# requires V2, which binds the extra observations to the same native sample.
FEATURE_FIELDS = ("sequence", "squads_enabled", "squad_assigned", "squad_attack", "squad_defend", "squad_support", "squad_targeted", "squad_goal_calls", "squad_goal_distinct", "squad_invalid", "contracts_enabled", "contract_active", "contract_completed", "contract_commendations", "contract_kill_progress", "contract_score_progress", "contract_objective_progress", "contract_invalid", "allies_bots", "axis_bots")
COUNT_FIELDS = frozenset(("bots", "humans", "alive", "playing", "identities", "roles", "careers", "moved", "invalid", "pools", "patrols", "squad_assigned", "squad_attack", "squad_defend", "squad_support", "squad_targeted", "contract_active", "allies_bots", "axis_bots"))


@dataclass(frozen=True)
class Case:
    map_name: str
    mode: str

    @classmethod
    def parse(cls, text: str) -> "Case":
        match = CASE.fullmatch(text)
        if not match:
            raise ValueError("Case must be a safe mp_map:native_mode pair")
        return cls(*match.groups())


def parse_samples(text: str) -> list[dict]:
    samples = []
    for line in text.splitlines():
        line = ANSI.sub("", line).strip()
        # Never match player/chat text that happens to contain the marker.
        if not line.startswith(("OUTLANDS_VERIFY_V1|", "OUTLANDS_VERIFY_V2|")):
            continue
        fields = line.split("|")
        names = FIELDS + FEATURE_FIELDS if fields[0] == "OUTLANDS_VERIFY_V2" else FIELDS
        if len(fields) != 4 + len(names) or fields[1] not in ("sample", "complete"):
            continue
        if not re.fullmatch(r"mp_[a-z0-9_]{1,40}", fields[2]) or fields[3] not in MODES:
            continue
        if not all(re.fullmatch(r"-?[0-9]{1,9}", value) for value in fields[4:]):
            continue
        record = {"kind": fields[1], "map": fields[2], "mode": fields[3]}
        record.update(zip(names, map(int, fields[4:])))
        record["version"] = int(fields[0][-1])
        if any(not 0 <= record[name] <= 16 for name in COUNT_FIELDS if name in record):
            continue
        if record["stage"] not in (0, 1) or record["prematch"] not in (-1, 0, 1):
            continue
        if record["kills"] < 0 or record["deaths"] < 0 or record["scorelimit"] < 0:
            continue
        if record["version"] == 2 and (record["sequence"] < 1 or any(record[name] not in (0, 1) for name in ("squads_enabled", "contracts_enabled")) or any(record[name] < 0 for name in FEATURE_FIELDS)):
            continue
        samples.append(record)
    return samples


def assess(samples: list[dict], case: Case, restart: bool, careers: bool = False,
           squads: bool = False, contracts: bool = False) -> dict:
    expected = (0, 1) if restart else (0,)
    reasons = []
    matching = [s for s in samples if (s["map"], s["mode"]) == (case.map_name, case.mode)]
    for stage in expected:
        stage_samples = [s for s in matching if s["stage"] == stage]
        complete = [s for s in stage_samples if s["kind"] == "complete"]
        if not complete:
            reasons.append(f"stage {stage}: no completed native match observation")
            continue
        final = complete[-1]
        if any(s["humans"] != 0 for s in stage_samples):
            reasons.append(f"stage {stage}: unexpected human connection")
        if final["bots"] != 16 or final["identities"] != 16 or final["roles"] != 16:
            reasons.append(f"stage {stage}: bot population/identity/role incomplete")
        if final["scorelimit"] != SCORE_LIMITS[case.mode]:
            reasons.append(f"stage {stage}: native score limit differs from the shipped mode wrapper")
        if final["prematch"] != 0:
            reasons.append(f"stage {stage}: native match remained in prematch")
        pairs = list(zip(stage_samples, stage_samples[1:]))
        if not any(later["kills"] > earlier["kills"] for earlier, later in pairs) or not any(later["score"] > earlier["score"] for earlier, later in pairs):
            reasons.append(f"stage {stage}: native combat counters did not increase within this stage")
        if max(s["pools"] for s in stage_samples) < 1 or max(s["patrols"] for s in stage_samples) < 1:
            reasons.append(f"stage {stage}: class/patrol hooks were not observed")
        if max(s["moved"] for s in stage_samples) < 8:
            reasons.append(f"stage {stage}: too few bots changed position")
        if any(s["invalid"] != 0 for s in stage_samples):
            reasons.append(f"stage {stage}: cosmetic level outside native range")
        if careers and final["careers"] != 16:
            reasons.append(f"stage {stage}: career restore incomplete")
        reasons.extend(assess_features(stage_samples, final, stage, case, squads, contracts))
    return {"case": asdict(case), "passed": not reasons, "reasons": reasons, "samples": matching}


def assess_features(samples, final, stage, case, squads, contracts):
    reasons = []
    extended = [sample for sample in samples if sample.get("version") == 2]
    if not extended:
        return [f"stage {stage}: feature acceptance requires V2 native metadata"] if squads or contracts else []
    if len(extended) != len(samples) or any(later["sequence"] <= earlier["sequence"] for earlier, later in zip(extended, extended[1:])):
        return [f"stage {stage}: mixed, duplicate or reordered native feature samples"]
    if case.mode in CONTRACT_MODES and (final["allies_bots"], final["axis_bots"]) != (8, 8):
        reasons.append(f"stage {stage}: native teams did not contain eight bots each")
    expected_squads = squads and case.mode in OBJECTIVE_MODES
    if any(sample["squads_enabled"] != int(expected_squads) for sample in extended):
        reasons.append(f"stage {stage}: squad enabled state differs from the isolated feature configuration")
    squad_fields = ("squad_assigned", "squad_attack", "squad_defend", "squad_support", "squad_targeted", "squad_goal_calls", "squad_goal_distinct", "squad_invalid")
    if not expected_squads:
        if any(sample[name] for sample in extended for name in squad_fields):
            reasons.append(f"stage {stage}: disabled or unsupported squad mode mutated metadata")
    else:
        if final["squad_assigned"] != 16 or sum(final[name] for name in ("squad_attack", "squad_defend", "squad_support")) != 16 or not 1 <= final["squad_attack"] <= 8 or not 0 <= final["squad_defend"] <= 4 or final["squad_support"] < 4:
            reasons.append(f"stage {stage}: eight-player teams did not receive bounded attack/defend/support allocation")
        if max(sample["squad_targeted"] for sample in extended) < 1 or any(sample["squad_targeted"] > sample["squad_attack"] + sample["squad_defend"] for sample in extended):
            reasons.append(f"stage {stage}: squad targets were absent or exceeded eligible roles")
        if final["squad_goal_calls"] < 1 or final["squad_goal_distinct"] < (2 if case.mode == "dom" else 1):
            reasons.append(f"stage {stage}: distinct acknowledged native objective goals were not observed")
        if not any(later["squad_goal_calls"] > earlier["squad_goal_calls"] for earlier, later in zip(extended, extended[1:])) or any(later[name] < earlier[name] for name in ("squad_goal_calls", "squad_goal_distinct") for earlier, later in zip(extended, extended[1:])):
            reasons.append(f"stage {stage}: native squad goal evidence did not increase monotonically within this stage")
        if any(sample["squad_invalid"] for sample in extended):
            reasons.append(f"stage {stage}: invalid native squad target or goal metadata")
    expected_contracts = contracts and case.mode in CONTRACT_MODES
    if any(sample["contracts_enabled"] != int(expected_contracts) for sample in extended):
        reasons.append(f"stage {stage}: contract enabled state differs from the isolated feature configuration")
    contract_fields = ("contract_active", "contract_completed", "contract_commendations", "contract_kill_progress", "contract_score_progress", "contract_objective_progress", "contract_invalid")
    if not expected_contracts:
        if any(sample[name] for sample in extended for name in contract_fields):
            reasons.append(f"stage {stage}: disabled contracts mutated metadata")
    else:
        if final["contract_active"] != 2 or final["contract_completed"] < 1:
            reasons.append(f"stage {stage}: native team contract boards did not complete a contract")
        if final["contract_commendations"] != final["contract_completed"]:
            reasons.append(f"stage {stage}: duplicate or missing match-local contract commendation")
        if not any(later["contract_completed"] > earlier["contract_completed"] for earlier, later in zip(extended, extended[1:])):
            reasons.append(f"stage {stage}: contract completion did not increase inside the observation window")
        if final["contract_kill_progress"] < 1 or final["contract_score_progress"] < 1:
            reasons.append(f"stage {stage}: contract progress did not consume native combat counter changes")
        for name in ("contract_completed", "contract_commendations", "contract_kill_progress", "contract_score_progress", "contract_objective_progress"):
            if any(later[name] < earlier[name] for earlier, later in zip(extended, extended[1:])):
                reasons.append(f"stage {stage}: cumulative contract evidence decreased within one native stage")
                break
        if any(sample["contract_invalid"] for sample in extended):
            reasons.append(f"stage {stage}: invalid contract source or progress metadata")
    return reasons


class Docker:
    def __init__(self, wrapper: Path):
        self.wrapper = wrapper

    def call(self, *args: str, input_text: str | None = None, check: bool = True) -> str:
        log_stream = bool(args and args[0] == "logs")
        result = subprocess.run([str(self.wrapper), *args], input=input_text, text=True,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT if log_stream else subprocess.PIPE)
        if check and result.returncode:
            # Raw diagnostics could contain a private path or credentials.
            raise RuntimeError("Docker operation failed; inspect the private verification log")
        if log_stream:
            # Docker routes the container's stderr to the caller's stderr.
            # Include it for private diagnostics, without contaminating JSON
            # returned by inspect or ordinary exec operations.
            # Merge while reading, rather than concatenating two streams after
            # exit: restart evidence relies on the historical log prefix.
            return result.stdout
        return result.stdout.strip()


def assess_switches(text):
    """Require a real pause/resume, including native goals and frozen accounting."""
    fields = ("kills", "roles", "owned_goals", "active", "contract_kills", "contract_score", "completed", "goal_calls")
    records = []
    for line in ANSI.sub("", text).splitlines():
        parts = line.strip().split("|")
        if len(parts) != 10 or parts[0] != "OUTLANDS_SWITCH_V1" or not all(re.fullmatch(r"[0-9]{1,9}", x) for x in parts[2:]):
            continue
        records.append(dict(phase=parts[1], **dict(zip(fields, map(int, parts[2:])))))
    reasons = []
    if [x["phase"] for x in records] != ["disabled_start", "disabled_end", "resumed"]:
        return {"passed": False, "reasons": ["missing, duplicate or reordered native switch observations"], "samples": records}
    first, last, resumed = records
    if any(x["roles"] or x["owned_goals"] or x["active"] for x in (first, last)):
        reasons.append("disabled modules retained assignments, owned native goals or an active contract")
    if any(first[k] != last[k] for k in ("contract_kills", "contract_score", "completed", "goal_calls")):
        reasons.append("disabled modules continued accounting or native goal submissions")
    if last["kills"] <= first["kills"]:
        reasons.append("native combat did not continue while modules were disabled")
    if resumed["roles"] != 16 or resumed["active"] != 1 or resumed["goal_calls"] <= last["goal_calls"]:
        reasons.append("squads and contracts did not resume with new native goals")
    return {"passed": not reasons, "reasons": reasons, "samples": records}


def assess_chat_context(text, case):
    topics=set();records=0;invalid=0
    clean=ANSI.sub('',text)
    for line in clean.splitlines():
        if not line.strip().startswith('OUTLANDS_CONTEXT_V1|'):continue
        fields=line.strip().split('|')
        if len(fields)!=16 or fields[3:5]!=[case.map_name,case.mode] or not re.fullmatch(r'[0-9]{1,2}',fields[1]) or not 0<=int(fields[1])<18 or not re.fullmatch(r'[A-Za-z0-9 ._~-]{1,24}',fields[2]):
            invalid+=1;continue
        context=Tactical.parse(fields[5:],case.mode)
        if context is None:invalid+=1;continue
        topics.add(context.topic);records+=1
    expected={'contract'} if case.mode in CONTRACT_MODES else set()
    if case.mode in OBJECTIVE_MODES:expected.update(('squad','objective'))
    markers=set(line.strip() for line in clean.splitlines())
    reasons=[]
    if not expected<=topics or invalid:reasons.append('native task context was missing or malformed')
    if 'OUTLANDS_CHAT_GUARD_V1|rejected' not in markers or 'OUTLANDS_CHAT_GUARD_V1|context_disabled' not in markers or 'OUTLANDS_CHAT_GUARD_V1|team_binding' not in markers or 'OUTLANDS_CHAT_GUARD_V1|failed' in markers:
        reasons.append('zero-human refusal or context off switch was not verified')
    if case.mode in OBJECTIVE_MODES and 'OUTLANDS_CHAT_GUARD_V1|stale_assignment' not in markers:
        reasons.append('stale squad assignment was not rejected by native steering and task context')
    if 'OUTLANDS_CHAT_ACK_V1|' in clean:reasons.append('production chat spoke without humans')
    if 'OUTLANDS_CHAT_PRIMITIVE_V1|sayall' not in markers:reasons.append('isolated native speech primitive was not exercised')
    return {'passed':not reasons,'reasons':reasons,'records':records,'topics':sorted(topics),'production_speech':False,'native_primitive_only':True}


def assess_ambient_chat(text):
    """Require real native ACKs tied to production requests and a different bot.

    This proves worker/native speech transport, not rendering or subjective
    conversational quality. No direct sayall fixture can satisfy the evidence.
    """
    events = {}
    accepted = []
    for raw in ANSI.sub('', text).splitlines():
        line = raw.strip()
        event = Event.parse(line, 0)
        if event:
            events[event.request_id] = event
        ack = ChatAck.parse(line)
        if ack:
            request = events.get(ack.request_id)
            if request and (ack.slot, ack.alias, ack.kind) == (request.slot, request.bot_name, request.kind):
                accepted.append(request)
    reasons = []
    pairs = [e for e in accepted if e.kind == 'bot_reply' and e.speaker != e.bot_name]
    if len(accepted) < 2 or not pairs:
        reasons.append('production native bot conversation was not acknowledged through the worker')
    samples = parse_samples(text)
    if not samples or any(s['humans'] for s in samples):
        reasons.append('ambient conversation must be observed with zero humans')
    if not any(s['bots'] == 16 and s['playing'] >= 14 for s in samples):
        reasons.append('production controller did not fill an idle native match')
    return {'passed': not reasons, 'reasons': reasons, 'native_deliveries': len(accepted),
            'bot_reply_deliveries': len(pairs), 'topics': sorted({e.tactical.topic for e in accepted if e.tactical}),
            'production_transport': True, 'model_mode': 'fallback', 'actual_client_rendering': False}


def assess_lobby(text):
    rows = []
    markers = [line.strip() for line in ANSI.sub('', text).splitlines()]
    malformed = False
    for line in markers:
        if not line.startswith('OUTLANDS_LOBBY_V1|'):
            continue
        parts = line.split('|')
        if len(parts) != 6 or not all(re.fullmatch(r'[0-9]{1,2}', value) for value in parts[2:]):
            malformed = True
            continue
        rows.append((parts[1], tuple(map(int, parts[2:]))))
    phases = ['baseline', 'deficit', 'refilled', 'imbalanced', 'rebalanced', 'disabled', 'resumed']
    expected = [(0,16,8,8), None, (0,16,8,8), (0,16,9,7), (0,16,8,8), (0,16,9,7), (0,16,8,8)]
    reasons = []
    if malformed or [phase for phase, _ in rows] != phases or any(
        values not in ((0,15,7,8), (0,15,8,7)) if wanted is None else values != wanted
        for (_, values), wanted in zip(rows, expected)
    ):
        reasons.append('native refill, imbalance repair or disabled-state evidence missing')
    if markers.count('OUTLANDS_PARTY_POLICY_V1|pass') != 1 or 'OUTLANDS_PARTY_POLICY_V1|failed' in markers:
        reasons.append('cooperative capacity/side policy did not pass native table checks')
    if markers.count('OUTLANDS_BALANCE_RESTORE_V1|pass') != 1 or 'OUTLANDS_BALANCE_RESTORE_V1|failed' in markers:
        reasons.append('stock balance policy was not restored when native-bot ownership was disabled')
    return {'passed': not reasons, 'reasons': reasons, 'observations': dict(rows),
            'actual_humans': False, 'human_join_acceptance': False}


def assess_air_response(text):
    markers = [line.strip() for line in ANSI.sub('', text).splitlines()]
    passed = markers.count('OUTLANDS_AIR_POLICY_V1|pass') == 1 and 'OUTLANDS_AIR_POLICY_V1|failed' not in markers
    return {'passed': passed, 'reasons': [] if passed else ['native air-response timer/filter policy did not pass'],
            'script_entity_fixture': True, 'actual_aircraft_combat': False}


def assess_expansion(text):
    markers = [line.strip() for line in ANSI.sub('', text).splitlines()]
    fixtures = [Event.parse(line.removeprefix('OUTLANDS_DIALOGUE_FIXTURE_V1|'), 0) for line in markers if line.startswith('OUTLANDS_DIALOGUE_FIXTURE_V1|')]
    turns = [item.turn for item in fixtures if item is not None]
    passed = markers.count('OUTLANDS_EXPANSION_V1|pass') >= 1 and 'OUTLANDS_EXPANSION_V1|failed' not in markers and len(fixtures) == len(turns) and turns == [1,2,3,4] * markers.count('OUTLANDS_EXPANSION_V1|pass')
    return {'passed': passed, 'native_formatted_turns':turns, 'reasons': [] if passed else ['native operation helper/bot exclusion checks missing or failed'],
            'actual_human_progression': False, 'actual_human_commands': False}


def assess_ui(text, restart=False):
    markers = [line.strip() for line in ANSI.sub('', text).splitlines() if line.strip().startswith('OUTLANDS_UI_V1|')]
    expected = ['OUTLANDS_UI_V1|pass|29|6|16|0'] * (2 if restart else 1)
    ingress = [line.strip() for line in ANSI.sub('', text).splitlines() if line.strip().startswith('OUTLANDS_COMMAND_INGRESS_V1|')]
    ingress_expected = ['OUTLANDS_COMMAND_INGRESS_V1|pass|19|19|19|19|1|1|0'] * (2 if restart else 1)
    passed = markers == expected and ingress == ingress_expected
    return {'passed': passed, 'reasons': [] if passed else ['native UI or command ingress/render/cleanup evidence missing or failed'],
            'native_sayall_sayteam_command_events': ingress == ingress_expected,
            'actual_human_commands': False, 'actual_client_rendering': False, 'native_bot_hud_fixture': True}


def service_armory_mailboxes(docker, worker, text, sent):
    # Only a fixed fixture response in disposable state; no fake human request.
    matches = re.findall(r'(?m)^OUTLANDS_ARMORY_MAILBOX_V1\|([A-Za-z0-9_]{1,48})\|([0-9]{1,2})\|([a-z0-9_,]{1,350})$', ANSI.sub('', text))
    for nonce, slot, refs in matches:
        if nonce in sent or int(slot)>17 or len(refs.split(','))!=7 or any(not re.fullmatch(r'[a-z][a-z0-9_]{0,47}',x) for x in refs.split(',')):
            continue
        value=nonce+'|'+slot+'|cancelled|1|'+refs
        script="from bridge import RconSink;from pathlib import Path;import sys;RconSink('127.0.0.1',14977,Path('/data/private/outlands_rcon_password')).send_armory(sys.stdin.read())"
        docker.call('exec','-i',worker,'python3','-c',script,input_text=value)
        sent.add(nonce)
    return sent


def assess_armory_editor(text, restart=False):
    markers = [line.strip() for line in ANSI.sub('', text).splitlines() if line.strip().startswith('OUTLANDS_ARMORY_EDITOR_V2|')]
    passed = markers == ['OUTLANDS_ARMORY_EDITOR_V2|pass|7|25|6|2|0'] * (2 if restart else 1)
    return {'passed': passed, 'reasons': [] if passed else ['native Armory custom grant/editor fixture missing or failed'],
            'actual_human_unlocks': False, 'actual_human_worker_transport': False, 'actual_client_rendering': False,
            'native_base_class_grant_fixture': True}


def assess_armory(text, restart=False):
    markers = [line.strip() for line in ANSI.sub('', text).splitlines() if line.strip().startswith('OUTLANDS_ARMORY_V1|')]
    expected_count = 2 if restart else 1
    passed = len(markers) == expected_count and all(re.fullmatch(r'OUTLANDS_ARMORY_V1\|pass\|[1-5]\|1\|1\|1\|1\|1', line) for line in markers)
    return {'passed': passed, 'reasons': [] if passed else ['native class-reference staging/spawn evidence missing or failed'],
            'native_class_reference_fixture': True, 'actual_human_unlocks': False,
            'custom_class_materialization': False, 'actual_client_editor': False}


def config_for(case: Case, seconds: int, restart: bool, careers: bool,
               squads: bool = False, contracts: bool = False, switches: bool = False, chat_context: bool = False, lobby_balance: bool = False, air_response: bool = False, expansion: bool = False, ui: bool = False, armory: bool = False, armory_editor: bool = False, ambient_chat: bool = False) -> str:
    cfg = (ROOT / "storage/t6/outlands_t6.cfg").read_text()
    cfg = re.sub(r'^sv_maprotation .*$', f'sv_maprotation "gametype {case.mode} execgts outlands_{case.mode}.cfg map {case.map_name}"', cfg, flags=re.M)
    return cfg + (f'\nset outlands_backend_verification 1\nset outlands_verify_seconds {seconds}\n'
                  f'set outlands_verify_restart {int(restart)}\nset outlands_verify_restarted 0\n'
                  f'set outlands_rotation 0\nset outlands_bot_idle_fill {16 if ambient_chat else 0}\n'
                  f'set outlands_chat_without_humans {int(ambient_chat)}\nset outlands_verify_ambient_chat {int(ambient_chat)}\n'
                  f'set outlands_bot_careers {int(careers)}\n'
                  f'set outlands_squads {int(squads)}\nset outlands_squad_attackers 4\nset outlands_squad_defenders 2\n'
                  f'set outlands_contracts {int(contracts)}\n' +
                  # Short thresholds are confined to disposable verification
                  # state; the probe never fabricates events, humans or XP.
                  ('set outlands_contract_seconds 30\nset outlands_contract_seed 0\nset outlands_contract_goal_scale 25\n' if contracts else '') +
                  ('set outlands_verify_switches 1\n' if switches else '')+
                  ('set outlands_verify_chat_context 1\nset outlands_chat_tactical 1\n' if chat_context else '')+
                  ('set outlands_verify_lobby 1\nset outlands_coop_teams 1\nset outlands_balance_teams 1\nset scr_teambalance 1\n' if lobby_balance else '')+
                  ('set outlands_verify_air 1\n' if air_response else '')+
                  ('set outlands_verify_expansion 1\n' if expansion else '')+
                  ('set outlands_ui 1\nset outlands_verify_ui 1\n' if ui else '')+
                  ('set outlands_verify_armory 1\n' if armory else '')+
                  ('set outlands_verify_armory_editor 1\n' if armory_editor else ''))


def career_summary(docker: Docker, worker: str) -> dict:
    script = ("import json,pathlib; p=pathlib.Path('/rivals/careers.json'); "
              "d=json.loads(p.read_text()); c=d['careers']; "
              "print(json.dumps({'bots':len(c),'earned_xp':sum(x['earned_xp'] for x in c.values()),"
              "'kills':sum(x['kills'] for x in c.values()),'xp':{k:v['xp'] for k,v in c.items()}}))")
    return json.loads(docker.call("exec", worker, "python3", "-c", script))


def require_map_asset(docker: Docker, image: str, case: Case):
    """Reject absent map IDs before creating any persistent test resources."""
    script = ("import json;from pathlib import Path;p=Path('/opt/t6/game/zone/all')/"+
              repr(case.map_name+'.ff')+";print(json.dumps(p.is_file() and p.stat().st_size>0))")
    available = json.loads(docker.call('run', '--rm', '--network', 'none', '--cap-drop', 'ALL',
                                      '--entrypoint', 'python3', image, '-c', script))
    if available is not True:
        raise ValueError('Requested map main fastfile is missing from the private image: '+case.map_name)


def run_case(docker: Docker, image: str, case: Case, seconds: int, restart: bool, directory: Path,
             careers: bool = False, worker_image: str = "outlands-bo2-chat:rivals-dev",
             process_restart: bool = False, squads: bool = False, contracts: bool = False, switches: bool = False, chat_context: bool = False, lobby_balance: bool = False, air_response: bool = False, expansion: bool = False, ui: bool = False, armory: bool = False, armory_editor: bool = False, ambient_chat: bool = False) -> dict:
    require_map_asset(docker, image, case)
    resource = "outlands-backend-" + uuid.uuid4().hex
    volume = resource + "-state"
    container = ""
    worker = ""
    rivals_volume = resource + "-rivals"
    rivals_created = False
    worker_restarted = False
    ledger_before = None
    created = False
    all_logs = ""
    started = time.monotonic()
    try:
        docker.call("volume", "create", "--label", LABEL + "=1", volume)
        created = True
        seed = ("import json,pathlib,sys\n"
                "p=pathlib.Path('/data/plutonium/storage/t6');p.mkdir(parents=True,exist_ok=True)\n"
                "x=json.load(sys.stdin);(p/'scripts/mp').mkdir(parents=True,exist_ok=True)\n"
                "(p/'outlands_t6.cfg').write_text(x['cfg'])\n"
                "(p/'scripts/mp/outlands_backend_verification.gsc').write_text(x['gsc'])\n")
        payload = json.dumps({"cfg": config_for(case, seconds, restart, careers, squads, contracts, switches, chat_context, lobby_balance, air_response, expansion, ui, armory, armory_editor, ambient_chat),
                              "gsc": (ROOT / "hosting/verification.gsc").read_text()})
        docker.call("run", "--rm", "-i", "--network", "none", "--cap-drop", "ALL",
                    "--security-opt", "no-new-privileges:true", "-v", volume + ":/data",
                    "--entrypoint", "python3", image, "-c", seed, input_text=payload)
        container = docker.call("run", "-d", "--name", resource, "--label", LABEL + "=1",
                                "--network", "none", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
                                "-e", "T6_MODE=lan", "-e", "T6_BIND_IP=127.0.0.1", "-e", "T6_PORT=14977",
                                "-e", "T6_ARMORY_ENABLED="+str(int(armory_editor)), "-e", "T6_OPERATIONS_ENABLED="+str(int(expansion)), "-e", "T6_CHAT_ENABLED="+str(int(chat_context or ambient_chat)), "-e", "T6_CAREERS_ENABLED=" + str(int(careers)), "-v", volume + ":/data", image)
        if not re.fullmatch(r"[a-f0-9]{64}", container):
            raise RuntimeError("Docker did not return an expected verification container ID")
        details = json.loads(docker.call("inspect", container))[0]
        if details["HostConfig"]["NetworkMode"] != "none" or details["HostConfig"].get("PortBindings"):
            raise RuntimeError("Verification container isolation did not match its required configuration")
        if careers or armory_editor or ambient_chat:
            docker.call("volume", "create", "--label", LABEL + "=1", rivals_volume)
            rivals_created = True
            worker = docker.call("run", "-d", "--name", resource + "-worker", "--label", LABEL + "=1",
                                 "--network", "container:" + container, "--read-only", "--cap-drop", "ALL",
                                 "--security-opt", "no-new-privileges:true", "-e", "T6_CHAT_ENABLED="+str(int(ambient_chat)), "-e", "T6_CHAT_MODE=fallback",
                                 "-e", "T6_CAREERS_ENABLED="+str(int(careers)), "-e", "T6_ARMORY_ENABLED="+str(int(armory_editor)), "-e", "T6_CHAT_RCON_PORT=14977",
                                 "-v", volume + ":/data:ro", "-v", rivals_volume + ":/rivals", worker_image)
            if not re.fullmatch(r"[a-f0-9]{64}", worker):
                raise RuntimeError("Docker did not return an expected verification worker ID")
        timeout = 180 + seconds * (2 if restart else 1)
        observed = False
        armory_mailboxes = set()
        while time.monotonic() - started < timeout:
            all_logs = docker.call("logs", container, check=False)
            if armory_editor and worker:
                armory_mailboxes = service_armory_mailboxes(docker, worker, all_logs, armory_mailboxes)
            samples = parse_samples(all_logs)
            if FAILURE.search(all_logs) or NATIVE_FAILURE.search(all_logs):
                break
            stages = {s["stage"] for s in samples if s["kind"] == "complete"}
            if careers and 0 in stages and not worker_restarted:
                ledger_before = career_summary(docker, worker)
                docker.call("restart", "-t", "5", worker)
                worker_restarted = True
            if (1 if restart else 0) in stages:
                observed = True
                break
            state = docker.call("inspect", "--format", "{{.State.Status}}", container)
            if state in ("exited", "dead"):
                break
            time.sleep(0.1 if armory_editor else 2)
        samples = parse_samples(all_logs)
        if switches:
            samples = [s for s in samples if s.get("squads_enabled") and s.get("contracts_enabled")]
        report = assess(samples, case, restart, careers, squads, contracts)
        if ambient_chat:
            report['ambient_chat'] = assess_ambient_chat(all_logs)
            if not report['ambient_chat']['passed']:
                report['passed'] = False
                report['reasons'].extend(report['ambient_chat']['reasons'])
        if armory_editor:
            report["armory_editor"] = assess_armory_editor(all_logs, restart)
            report["armory_editor"]["loopback_mailbox_sends"] = len(armory_mailboxes)
            worker_logs = docker.call("logs", worker, check=False)
            private_store = docker.call("exec", worker, "python3", "-c", "from pathlib import Path;print(Path('/rivals/armory.json').exists())").strip()
            transport_ok = len(armory_mailboxes) == (2 if restart else 1) and 'Armory persistence ready; native identity requests only' in worker_logs and 'Armory worker stopped' not in worker_logs and private_store == 'False'
            report["armory_editor"]["worker_ready_and_human_store_absent"] = transport_ok
            if not transport_ok:
                report["armory_editor"]["passed"] = False
                report["armory_editor"]["reasons"].append('Armory worker/mailbox/isolation checks failed')
            if not report["armory_editor"]["passed"]:
                report["passed"] = False
                report["reasons"].extend(report["armory_editor"]["reasons"])
        if armory:
            report["armory"] = assess_armory(all_logs, restart)
            if not report["armory"]["passed"]:
                report["passed"] = False
                report["reasons"].extend(report["armory"]["reasons"])
        if ui:
            report["ui"] = assess_ui(all_logs, restart)
            if not report["ui"]["passed"]:
                report["passed"] = False
                report["reasons"].extend(report["ui"]["reasons"])
        if expansion:
            report["expansion"] = assess_expansion(all_logs)
            if not report["expansion"]["passed"]:
                report["passed"] = False
                report["reasons"].extend(report["expansion"]["reasons"])
        if air_response:
            report['air_response'] = assess_air_response(all_logs)
            if not report['air_response']['passed']:
                report['passed'] = False
                report['reasons'].extend(report['air_response']['reasons'])
        if lobby_balance:
            report['lobby_balance']=assess_lobby(all_logs)
            if not report['lobby_balance']['passed']:
                report['passed']=False;report['reasons'].extend(report['lobby_balance']['reasons'])
        if chat_context:
            report['chat_context']=assess_chat_context(all_logs,case)
            if not report['chat_context']['passed']:
                report['passed']=False;report['reasons'].extend(report['chat_context']['reasons'])
        if switches:
            report["runtime_switches"] = assess_switches(all_logs)
            if not report["runtime_switches"]["passed"]:
                report["passed"] = False
                report["reasons"].extend(report["runtime_switches"]["reasons"])
        report.update({"elapsed_seconds": round(time.monotonic() - started, 2),
                       "observation_completed": observed, "script_error": bool(FAILURE.search(all_logs)),
                       "native_crash": bool(NATIVE_FAILURE.search(all_logs)),
                       "network_mode": "none", "published_ports": False,
                       "game_image": details["Image"],
                       "worker_image": json.loads(docker.call("inspect", worker))[0]["Image"] if worker else None})
        if careers:
            after = career_summary(docker, worker)
            preserved = ledger_before is not None and all(after["xp"].get(name, -1) >= xp for name, xp in ledger_before["xp"].items())
            if process_restart and observed and not NATIVE_FAILURE.search(all_logs):
                # Restart the actual server process with its same disposable state.
                # Keep the worker alive while the game shuts down to consume final events.
                docker.call("stop", "-t", "15", container)
                docker.call("stop", "-t", "5", worker)
                previous = docker.call("logs", container, check=False)
                update = ("from pathlib import Path; import re; p=Path('/data/plutonium/storage/t6/outlands_t6.cfg'); "
                          "s=p.read_text(); p.write_text(re.sub(r'(?m)^set outlands_verify_restart [01]$', "
                          "'set outlands_verify_restart 0', s))")
                docker.call("run", "--rm", "--network", "none", "--cap-drop", "ALL",
                            "--security-opt", "no-new-privileges:true", "-v", volume + ":/data",
                            "--entrypoint", "python3", image, "-c", update)
                docker.call("start", container)
                docker.call("start", worker)
                phase_started = time.monotonic()
                current = ""
                while time.monotonic() - phase_started < 180 + seconds:
                    all_logs = docker.call("logs", container, check=False)
                    if not all_logs.startswith(previous):
                        raise RuntimeError("Verification log prefix changed across process restart")
                    current = all_logs[len(previous):]
                    if FAILURE.search(current) or NATIVE_FAILURE.search(current) or any(x["kind"] == "complete" for x in parse_samples(current)):
                        break
                    if docker.call("inspect", "--format", "{{.State.Status}}", container) in ("exited", "dead"):
                        break
                    time.sleep(2)
                process_result = assess(parse_samples(current), case, False, True, squads, contracts)
                if chat_context:
                    process_result['chat_context'] = assess_chat_context(current, case)
                    if not process_result['chat_context']['passed']:
                        process_result['passed'] = False
                        process_result['reasons'].extend(process_result['chat_context']['reasons'])
                after_process = career_summary(docker, worker)
                process_preserved = all(after_process["xp"].get(name, -1) >= xp for name, xp in after["xp"].items())
                report["server_process_restart"] = {"passed": process_result["passed"] and process_preserved and not FAILURE.search(current) and not NATIVE_FAILURE.search(current),
                                                     "aggregate_preserved": process_preserved, "samples": process_result["samples"],
                                                     "reasons": process_result["reasons"],
                                                     "chat_context": process_result.get("chat_context")}
                if not report["server_process_restart"]["passed"]:
                    report["passed"] = False
                    report["reasons"].append("server process restart did not preserve career state or native gameplay")
                after = after_process
            report["career_state"] = {"worker_restarted": worker_restarted, "aggregate_preserved": preserved,
                                      "bots": after["bots"], "earned_xp": after["earned_xp"], "kills": after["kills"]}
            if not preserved or after["earned_xp"] < 1:
                report["passed"] = False
                report["reasons"].append("career aggregate did not survive worker restart or earn native score deltas")
        if report["native_crash"]:
            report["passed"] = False
            report["reasons"].append("native Plutonium exception detected; no automatic acceptance after recovery")
        if report["script_error"]:
            report["passed"] = False
            report["reasons"].append("native script error detected")
        report["elapsed_seconds"] = round(time.monotonic() - started, 2)
        return report
    finally:
        volumes = ([rivals_volume] if rivals_created else []) + ([volume] if created else [])
        cleanup_resources(docker, case, directory, all_logs, container, worker, volumes)


def cleanup_resources(docker, case, directory, all_logs, container, worker, volumes):
    # Log IO must never prevent attempts to stop every created resource.
    cleanup_errors = []
    try:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{case.map_name}-{case.mode}.log").write_text(all_logs)
        if worker and re.fullmatch(r"[a-f0-9]{64}", worker):
            (directory / f"{case.map_name}-{case.mode}-worker.log").write_text(docker.call("logs", worker, check=False))
    except (OSError, RuntimeError):
        cleanup_errors.append("private log write")
    operations = []
    if worker and re.fullmatch(r"[a-f0-9]{64}", worker):
        operations += [("stop", "-t", "5", worker), ("rm", worker)]
    if container and re.fullmatch(r"[a-f0-9]{64}", container):
        operations += [("stop", "-t", "15", container), ("rm", container)]
    for volume in volumes:
        operations.append(("volume", "rm", volume))
    for operation in operations:
        try:
            docker.call(*operation)
        except (OSError, RuntimeError):
            cleanup_errors.append("resource " + operation[0])
    if cleanup_errors:
        raise RuntimeError("Verification cleanup incomplete: " + ", ".join(cleanup_errors))

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--image", default="outlands-t6:local")
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--restart", action="store_true")
    parser.add_argument("--careers", action="store_true", help="verify private career worker/restore and worker restart")
    parser.add_argument("--squads", action="store_true", help="verify native coordinated squad roles/goals; unsupported modes must remain native")
    parser.add_argument("--contracts", action="store_true", help="verify team contracts from native counters using disposable short thresholds")
    parser.add_argument("--switches", action="store_true", help="also disable and resume both modules during one isolated objective match")
    parser.add_argument('--air-response', action='store_true', help='verify bot-only air target gate with private script entities, not actual aircraft combat')
    parser.add_argument('--lobby-balance',action='store_true',help='verify native bot refill, imbalance repair and count-only cooperative side policy; no humans fabricated')
    parser.add_argument('--chat-context',action='store_true',help='capture native task snapshots and verify human-presence/context guards; native speech primitive is tested separately')
    parser.add_argument('--ambient-chat',action='store_true',help='verify production idle fill, real worker fallback transport and native bot-to-bot delivery with no humans')
    parser.add_argument("--armory-editor", action="store_true", help="native base-class grant, HUD and lifecycle fixture with bots; human transport/rendering remain pending")
    parser.add_argument("--armory", action="store_true", help="native all-bot class-reference selection and next-spawn feasibility; no arbitrary edits or human unlock acceptance")
    parser.add_argument("--ui", action="store_true", help="verify actual native HUD creation, presenters and cleanup with bots; real client rendering/input remain pending")
    parser.add_argument("--expansion", action="store_true", help="verify native milestone helpers and bot exclusion; human commands require later client acceptance")
    parser.add_argument("--worker-image", default="outlands-bo2-chat:rivals-dev")
    parser.add_argument("--process-restart", action="store_true", help="also restart the actual game/worker containers with their same disposable volumes")
    parser.add_argument("--report-dir", type=Path)
    args = parser.parse_args(argv)
    try:
        cases = [Case.parse(text) for text in args.case] or [Case("mp_raid", "dom"), Case("mp_slums", "conf")]
        if not 30 <= args.seconds <= 300:
            raise ValueError("Observation seconds must be between 30 and 300")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./:-]{0,180}", args.image):
            raise ValueError("Expected a local Docker image name")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./:-]{0,180}", args.worker_image):
            raise ValueError("Expected a local Docker worker image name")
        if args.process_restart and not args.careers:
            raise ValueError("Process restart acceptance requires --careers")
        if args.ambient_chat and (args.chat_context or args.process_restart or args.lobby_balance or args.seconds < 90):
            raise ValueError('Ambient chat needs at least 90 seconds and cannot combine with guard, process-restart or lobby fixtures')
        if args.switches and (not args.squads or not args.contracts or len(cases) != 1 or cases[0].mode not in OBJECTIVE_MODES or args.seconds < 90 or args.restart or args.process_restart):
            raise ValueError("Switch acceptance requires both modules, one objective case, at least 90 seconds and no restart flags")
        if args.chat_context and (not args.contracts or any(c.mode in OBJECTIVE_MODES for c in cases) and not args.squads):
            raise ValueError('Chat context acceptance needs contracts and objective squads where supported')
        if args.air_response and (args.seconds < 60 or args.restart or args.process_restart):
            raise ValueError('Air-response fixture requires at least 60 seconds and no restart flags')
        if args.lobby_balance and (any(c.mode=='dm' for c in cases) or args.seconds<90 or args.switches or args.process_restart or args.restart):
            raise ValueError('Lobby verification needs team modes, at least 90 seconds and no restart/switch flags')
        plan = {"server_process_restart": args.process_restart, "careers": args.careers, "squads": args.squads, "contracts": args.contracts, "contract_test_thresholds": args.contracts, "cases": [asdict(case) for case in cases], "seconds": args.seconds,
                "native_restart": args.restart, "native_restart_method": "same_map_reload" if args.restart else None, "runtime_switches": args.switches, "chat_context":args.chat_context, "lobby_balance":args.lobby_balance, "air_response":args.air_response, "expansion":args.expansion, "ui":args.ui, "armory":args.armory, "armory_editor":args.armory_editor, "network_mode": "none", "published_ports": False,
                "human_clients": False, "live_state": False, "ambient_chat": args.ambient_chat}
        if not args.run:
            print(json.dumps(plan, indent=2))
            return 0
        directory = args.report_dir or ROOT / "hosting/logs" / ("backend-" + uuid.uuid4().hex)
        directory = directory.absolute()
        if directory.exists() or any(p.is_symlink() for p in [directory, *directory.parents]):
            raise ValueError("Choose a fresh report directory without symlink parents")
        directory.mkdir(parents=True, mode=0o700)
        docker = Docker(ROOT / "hosting/docker.sh")
        reports = []
        for case in cases:
            report = run_case(docker, args.image, case, args.seconds, args.restart, directory, args.careers, args.worker_image, args.process_restart, args.squads, args.contracts, args.switches,args.chat_context,args.lobby_balance,args.air_response,args.expansion,args.ui,args.armory,args.armory_editor,args.ambient_chat)
            reports.append(report)
            (directory / "report.json").write_text(json.dumps({"plan": plan, "results": reports}, indent=2) + "\n")
            print(f"{'PASS' if report['passed'] else 'FAIL'}: {case.map_name}/{case.mode}", flush=True)
        return 0 if all(x["passed"] for x in reports) else 1
    except (OSError, ValueError, RuntimeError) as error:
        print("Backend verification failed: " + str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
