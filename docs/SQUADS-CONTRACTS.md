# Objective squads and match contracts

These optional server modules add team assignments and timed challenges to the
native bot game. They do not replace BO2 pathfinding, combat, weapon validity,
rank XP, unlocks or player saves. No extra client assets or model weights are
required. Both modules start through the single Outlands native-bot controller.

## Objective squads

Squads coordinate verified native bots in Domination, Capture the Flag,
Hardpoint, Headquarters and Demolition. A bounded team allocation divides bots
between attacking and defending available native objectives, with remaining
bots retaining native behavior. Assignments are periodically reassessed against
current team membership and objective state.

Native combat and recovery run ahead of the objective callback. The adapter
uses the game's objective and goal APIs, retaining danger, carrier and
interaction priority.
Unknown helpers, conflicting detours, unavailable objectives and unsupported
modes fall back to native behavior. No human entity receives a squad override.
An assignment is a tactical hint, not a replacement navigation mesh or a promise
that a bot reaches or captures its goal.

## Team contracts

Each supported team receives a rotating match-local contract with a deadline.
The first version uses three explicit measurements:

| Contract | Measurement |
| --- | --- |
| Team eliminations | New native player kills accumulated by the team |
| Combined score | New native individual scoreboard points accumulated by the team |
| Team points | New native team scoreboard points in objective modes |

Combined score includes combat awards and must not be described as captures.
Team points follow the selected mode's own scoring rules. Free-for-All has no
team contract. Rosters and counter resets establish new baselines rather than
granting progress for a joining player's previous score.

Counters are sampled every two seconds. Decreases rebase each metric
independently: a score penalty gives no score credit while valid new kills can
still count. Observations at or after a deadline cannot finish the expired
contract; the last unsampled interval is conservatively excluded.

Completion grants a match-local Outlands commendation and a team notification.
This is an additional challenge layer, with no native XP, equipment, unlock or
persistent player reward. Deadlines, failure, completion and the next contract
remain separate states. Human-facing notifications are limited to actual human
team members; no synthetic human connection or bot chat is needed for testing.

## Configuration

Edit the host's private `storage/t6/outlands_t6.cfg`. Existing operator values
are retained when new source settings are introduced. Initialize a fresh map
after enabling a module so its native hooks can be installed.

| Setting | Default | Bound |
| --- | ---: | --- |
| `outlands_squads` | 1 | 0 disables squad steering |
| `outlands_squad_reassess_seconds` | 8 | 3-30 seconds |
| `outlands_squad_attackers` | 4 | 1-6 bots per team |
| `outlands_squad_defenders` | 2 | 0-3 bots per team |
| `outlands_squad_goal_seconds` | 3 | 1-8 seconds |
| `outlands_contracts` | 1 | 0 disables contracts |
| `outlands_contract_seconds` | 90 | 30-300 seconds |
| `outlands_contract_seed` | 13 | 0-9999 |
| `outlands_contract_goal_scale` | 100 | 25-400 percent |

Keep the two switches independent from cosmetic careers and optional chat. The
modules need no RCON privilege or persistent ledger. Runtime goals, counter
baselines and commendations reset with a new map/server process.

Preview contract settings without launching the game:

```sh
python3 -B tools/contract_rules.py --help
```

## Backend verification

The isolated runner stages its probe only into labelled disposable storage,
uses native test clients, publishes no ports and uses network mode `none`.
Run from the project root after privately building the current images:

```sh
python3 -B hosting/backend_verify.py --squads --contracts --careers --restart --process-restart
python3 -B hosting/backend_verify.py --run --image outlands-t6:squads-dev --worker-image outlands-bo2-chat:rivals-dev --squads --contracts --careers --restart --process-restart --case mp_raid:dom --seconds 90
```

The probe observes actual native bot population, combat, score, squad assignment,
accepted objective-goal calls, contract progress and completion. Low contract
thresholds used by the test belong only to disposable configuration. Negative
runs check off switches and nonobjective fallback. Restart runs must show new
native activity and fresh match-local contract state while retaining independent
fictional-bot careers.

Keep raw console logs, runtime state, addresses, profile data and private image
contents outside GitHub. Publish source, methodology and aggregate outcomes.
Backend evidence cannot establish better human-perceived movement, readable HUD
notifications, balance or human save retention. Those require later client
playtests, with contracts/squads enabled and disabled for comparison.
