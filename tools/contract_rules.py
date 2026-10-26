"""Executable contract specification for synthetic backend fixtures.

GSC remains the runtime owner. This model covers the accounting boundaries that
are difficult to force in native matches: roster changes, resets and duplicate
completion checks. It has no game, network, filesystem or player identity I/O.
"""

import argparse
from dataclasses import dataclass
import json

TEAM_MODES = frozenset({"tdm", "conf", "dom", "koth", "hq", "ctf", "dem"})
TEAMS = ("allies", "axis")
KINDS = ("team_eliminations", "combined_score", "team_points")


def bounded(value: int, minimum: int, maximum: int) -> int:
    return min(max(int(value), minimum), maximum)


def phase_kind(mode: str, phase: int, seed: int = 13) -> str:
    if mode not in TEAM_MODES or phase < 1:
        raise ValueError("Contracts require a supported team mode and phase >= 1")
    kinds = KINDS[:2] if mode == "tdm" else KINDS
    return kinds[(bounded(seed, 0, 9999) + phase - 1) % len(kinds)]


def goal(mode: str, kind: str, scale: int = 100) -> int:
    if mode not in TEAM_MODES or kind not in KINDS or mode == "tdm" and kind == "team_points":
        raise ValueError("Unsupported contract kind or mode")
    value = 12
    if kind == "combined_score":
        value = 1000
    elif kind == "team_points":
        value = 1 if mode in {"ctf", "dem"} else 6 if mode == "conf" else 12
    return max(1, value * bounded(scale, 25, 400) // 100)


@dataclass(frozen=True)
class Sample:
    # Occupant is a short-lived test token, never a name/account identifier.
    occupant: object
    team: str
    kills: int
    score: int


class CounterLedger:
    """Only adjacent valid native observations contribute to team totals."""

    def __init__(self):
        self.players: dict[int, Sample] = {}
        self.points: dict[str, int] = {}
        self.totals = {team: dict.fromkeys(KINDS, 0) for team in TEAMS}
        self.invalid = dict.fromkeys(TEAMS, 0)
        self.rebases = dict.fromkeys(TEAMS, 0)

    def pause(self):
        self.players.clear()
        self.points.clear()

    def observe(self, samples: dict[int, Sample], points: dict[str, int]):
        for slot, sample in samples.items():
            if not 0 <= slot <= 63 or sample.team not in TEAMS:
                continue
            if not 0 <= sample.kills <= 1_000_000 or not -100_000_000 <= sample.score <= 100_000_000:
                self.invalid[sample.team] += 1
                self.players.pop(slot, None)
                continue
            previous = self.players.get(slot)
            if previous and previous.occupant == sample.occupant and previous.team == sample.team:
                kills, score = sample.kills - previous.kills, sample.score - previous.score
                if kills < 0 or score < 0:
                    self.rebases[sample.team] += 1
                if kills > 256 or score > 100_000:
                    self.invalid[sample.team] += 1
                else:
                    self.totals[sample.team]["team_eliminations"] += max(0, kills)
                    self.totals[sample.team]["combined_score"] += max(0, score)
            self.players[slot] = sample
        for team, score in points.items():
            if team not in TEAMS:
                continue
            if not 0 <= score <= 1_000_000:
                self.invalid[team] += 1
                self.points.pop(team, None)
                continue
            if team in self.points:
                delta = score - self.points[team]
                if delta < 0:
                    self.rebases[team] += 1
                if delta > 1000:
                    self.invalid[team] += 1
                elif delta > 0:
                    self.totals[team]["team_points"] += delta
            self.points[team] = score


@dataclass
class Contract:
    baseline: int
    goal: int
    deadline: int
    current: int | None = None
    complete: bool = False
    expired: bool = False
    commendations: int = 0

    def __post_init__(self):
        if self.baseline < 0 or self.goal < 1 or self.deadline < 0:
            raise ValueError("Contracts require nonnegative ledger/deadline and a positive goal")
        if self.current is None:
            self.current = self.baseline

    @property
    def progress(self):
        return self.current - self.baseline

    def update(self, metric: int, now: int) -> str | None:
        if metric < self.baseline:
            raise ValueError("Contract metrics are cumulative validated ledger values")
        if self.expired:
            return None
        # As in the native poller, an observation at/after the deadline cannot
        # complete the old task. The last unsampled interval is not inferred.
        if not self.complete and now >= self.deadline:
            self.expired = True
            return "expired"
        self.current = metric
        if not self.complete and self.progress >= self.goal:
            self.complete = True
            self.commendations += 1
            return "complete"
        return None


def preview(mode: str, seed: int = 13, seconds: int = 90, scale: int = 100, phases: int = 6) -> dict:
    """Preview host contract settings without launching or writing anything."""
    settings = {
        "outlands_contract_seed": bounded(seed, 0, 9999),
        "outlands_contract_seconds": bounded(seconds, 30, 300),
        "outlands_contract_goal_scale": bounded(scale, 25, 400),
    }
    rows = []
    for phase in range(1, bounded(phases, 1, 24) + 1):
        kind = phase_kind(mode, phase, settings["outlands_contract_seed"])
        rows.append({"phase": phase, "kind": kind,
                     "goal": goal(mode, kind, settings["outlands_contract_goal_scale"]),
                     "duration_seconds": settings["outlands_contract_seconds"]})
    return {"mode": mode, "settings": settings, "phases": rows,
            "reward": "one match-local team commendation per completed phase",
            "native_xp_or_score_writes": False,
            "scope": "configuration preview; native runtime verification is separate"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Preview bounded Outlands team contract settings; no game or files changed.")
    parser.add_argument("--mode", choices=sorted(TEAM_MODES), default="dom")
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--seconds", type=int, default=90)
    parser.add_argument("--goal-scale", type=int, default=100, help="percent, clamped to 25–400")
    parser.add_argument("--phases", type=int, default=6, help="preview length, clamped to 1–24")
    args = parser.parse_args(argv)
    print(json.dumps(preview(args.mode, args.seed, args.seconds, args.goal_scale, args.phases), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
