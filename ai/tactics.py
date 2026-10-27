"""Bounded ephemeral native task context; never persistent player memory."""
from dataclasses import dataclass, asdict
import random
import re

TOPICS = frozenset(('none', 'squad', 'objective', 'contract'))
STATES = frozenset(('none', 'friendly', 'enemy', 'neutral', 'active', 'home', 'away'))
CONTRACTS = frozenset(('none', 'team_eliminations', 'combined_score', 'team_points'))
MODES = frozenset(('dom', 'ctf', 'koth', 'hq', 'dem', 'tdm', 'conf', 'dm'))


@dataclass(frozen=True)
class Tactical:
    topic: str
    team: str
    role: str
    target: int
    state: str
    contract: str
    phase: int
    progress: int
    goal: int
    complete: int
    remaining: int

    @classmethod
    def parse(cls, fields, mode):
        if len(fields) != 11 or mode not in MODES:
            return None
        topic, team, role, target, state, contract, phase, progress, goal, complete, remaining = fields
        if topic not in TOPICS or team not in ('none', 'allies', 'axis') or role not in ('none', 'attack', 'defend', 'support') or state not in STATES or contract not in CONTRACTS:
            return None
        if not re.fullmatch(r'-1|[0-9]{1,2}', target) or not -1 <= int(target) <= 31:
            return None
        if not all(re.fullmatch(r'[0-9]{1,8}', x) for x in (phase, progress, goal, complete, remaining)):
            return None
        phase, progress, goal, complete, remaining = map(int, (phase, progress, goal, complete, remaining))
        if complete not in (0, 1) or remaining > 300 or phase > 1_000_000 or progress > 10_000_000 or goal > 100_000:
            return None
        target = int(target)
        if team == 'none' and (role != 'none' or contract != 'none' or topic != 'none'):
            return None
        if role in ('none', 'support') and (target != -1 or state != 'none'):
            return None
        if role in ('attack', 'defend') and (target < 0 or state == 'none' or mode not in ('dom','ctf','koth','hq','dem')):
            return None
        if role in ('attack', 'defend'):
            expected_states = {'friendly', 'enemy', 'neutral'} if mode == 'dom' else {'home', 'away'} if mode == 'ctf' else {'active'}
            if state not in expected_states:
                return None
        if contract == 'none':
            if any((phase, progress, goal, complete, remaining)):
                return None
        elif mode == 'dm' or phase < 1 or goal < 1 or remaining < 1 or bool(complete) != (progress >= goal):
            return None
        if topic in ('squad', 'objective') and role not in ('attack', 'defend') or topic == 'contract' and contract == 'none':
            return None
        return cls(topic, team, role, target, state, contract, phase, progress, goal, complete, remaining)

    def directive(self, mode):
        """A short trusted task instruction made only from validated enums."""
        if self.topic == 'none':
            return ''
        if self.topic == 'contract':
            if self.complete:
                task = 'Your current team contract is complete. Acknowledge that contract.'
            else:
                task = {'team_eliminations': 'Your team is working on a kill contract.',
                        'combined_score': 'Your team is working on a score contract.',
                        'team_points': 'Your team is working on a match points contract.'}[self.contract]
                task += ' It is still incomplete. Mention working toward that contract.'
        else:
            action = 'watch and defend' if self.role == 'defend' else 'push toward'
            task = f'Your own current assignment is to {action} the {objective_name(mode, self.role)}.'
            task += ' Describe that intent briefly, without claiming arrival or capture.'
        return ' Current response focus: ' + task + ' Output one casual chat line, not general round banter.'

    def context(self, mode):
        result = asdict(self)
        result['objective_name'] = objective_name(mode, self.role)
        result['meaning'] = 'Current task intent only; not proof of arrival, capture or a future result.'
        return result


def objective_name(mode, role):
    # Native objective indices are not assumed to map to A/B/C display labels.
    if mode == 'ctf':
        return 'home flag' if role == 'defend' else 'enemy flag'
    return {'dom':'flag', 'koth':'hill', 'hq':'HQ', 'dem':'bomb site'}.get(mode, 'objective')


def fallback(tactical, mode, final=False, history=(), responding=False):
    if tactical is None or tactical.topic == 'none':
        return None
    name = objective_name(mode, tactical.role)
    if tactical.topic == 'contract':
        if tactical.complete:
            choices = ['Nice, that contract is done.', 'Contract done. Good work.', 'Got that contract, nice.', 'That task is wrapped up.']
        elif tactical.contract == 'team_eliminations':
            choices = ['Working on kills for this contract.', 'Still working on that kill contract.', 'Keeping at this kill contract.', 'A few clean picks should help that contract.']
        elif tactical.contract == 'combined_score':
            choices = ['Keeping the score moving for that contract.', 'Still chasing score for that contract.', 'Still working on those contract points.', 'That score contract gives us something to chase.']
        else:
            choices = ['We need match points for this contract.', 'Playing the objective for those contract points.', 'Still chasing the team points contract.', 'Keep the match points coming for that contract.']
    elif tactical.role == 'defend':
        choices = [f"I'll watch the {name}.", f"Planning to hold the {name}.", f"I've got guard duty at the {name}.", f"I'll cover the {name} for now."]
    else:
        choices = [f"Heading for the {name}.", f"Going to push the {name}.", f"I'll make a run at the {name}.", f"Let's pressure the {name}."]
    if responding:
        choices = ["Fair, let's stick with it.", "Yeah, worth a try.", "I'm with you on that.", "Alright, no overthinking it.", "That sounds more like it.", "Let's see how that goes."]
    elif final:
        choices = ['Yeah, '+x[0].lower()+x[1:] for x in choices]
    def normalized(line):
        return re.sub(r'^yeah,\s*', '', line.casefold())
    recent = {normalized(x) for x in history[-4:]}
    return random.choice([x for x in choices if normalized(x) not in recent] or choices)


def usable(tactical, mode, reply, responding=False):
    if tactical is None or tactical.topic == 'none':
        return True
    text = reply.lower()
    # Intent snapshots cannot support invented named flags, counts, arrivals,
    # captures, enemy locations or native progression rewards.
    if re.search(r'\d|\b[BC]\b|\b(?:flag|site|point) [ABC]\b', reply):
        return False
    if re.search(r'\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|dozen|hundred|thousand|victory|win|winning|wins)\b', text):
        return False
    if re.search(r'\b(?:captured|secured|won|leveled|unlocked|prestiged|xp|enemies|enemy at|enemy behind|enemy near)\b', text):
        return False
    if re.search(r"\b(?:arrived|arriving|secured|capturing|captured)\b|\b(?:close to|closing in|nearly there|in position|made it|i'm at|we're at|we are at|i am at)\b", text):
        return False
    expected_noun = {'dom': 'flag', 'ctf': 'flag', 'koth': 'hill', 'hq': 'hq', 'dem': 'site'}.get(mode)
    if any(re.search(r'\b'+noun+r'\b', text) for noun in ('flag', 'hill', 'hq', 'site') if noun != expected_noun):
        return False
    if mode == 'ctf' and ((tactical.role == 'defend' and 'enemy flag' in text) or (tactical.role == 'attack' and 'home flag' in text)):
        return False
    if tactical.topic == 'contract':
        if not responding and not re.search(r'\b(?:contract|task)\b', text):
            return False
        if not tactical.complete and re.search(r'\b(?:done|complete|completed|finished|wrapped|nailed)|\bgot (?:that|the|this) (?:contract|task)\b\b', text):
            return False
    else:
        if not responding and not re.search(r'\b(?:flag|hill|hq|site|objective)\b', text):
            return False
        if not responding and tactical.role == 'defend' and not re.search(r'\b(?:watch|watching|hold|holding|cover|covering|guard|guarding|defend|defending|protect|protecting)\b', text):
            return False
        if not responding and tactical.role == 'attack' and not re.search(r'\b(?:push|pushing|pressure|pressuring|head|heading|going|moving|run|attack|attacking|rush|rushing)\b', text):
            return False
        if tactical.role == 'defend' and re.search(r'\b(?:pushing|push|rushing|rush|attacking|attack)\b', text):
            return False
        if tactical.role == 'attack' and re.search(r'\b(?:holding|hold|defending|defend|guarding|guard)\b', text):
            return False
    return True
