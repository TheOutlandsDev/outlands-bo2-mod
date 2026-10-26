# Persistent AI rivals

The optional rival system gives the fictional native-bot roster returning
careers, consistent class roles and richer local chat context. Native combat,
pathfinding, objectives, human XP and human unlocks remain under BO2.

## Careers and personalities

A private worker ledger records only allowlisted fictional bots. Each alias has
a stable seeded cosmetic level/prestige and a curated role, motivation,
temperament and speech style. Native bot scoreboard deltas then award a separate
fictional career currency: 100 career XP per kill plus positive native score
deltas. Each 5,000 career XP advances one cosmetic level; level 55 rolls into
the next prestige, capped at prestige 10 / level 55. This does not write native
player DDL or unlock weapons for humans or bots.

One connection token identifies a bot occupant. A hello establishes its baseline;
increasing snapshot sequences award only new deltas. Repeated hellos restore the
same profile without rebasing or awarding again. Decreasing counters rebase the
sample without rewards. Implausible deltas are discarded. Atomic private writes
commit before a profile response is sent, so a retry after worker restart cannot
award the same snapshot twice. Bounded session and retired-token caches prevent
unbounded growth; console following starts at EOF instead of replaying old logs.

A fixed profile mailbox returns only request ID, slot, alias, level, prestige and
one of five roles. GSC checks the exact pending native bot, connection token,
alias, slot, expiry and native ranges. Responses can update cosmetic display
and bot class-role metadata; they cannot write human progression or issue
arbitrary game commands. Marksman limits and native anti-air choices still apply.

## Contextual conversation

The local model receives validated personality traits, the bot's own aggregate
career and a fresh observed scoreboard sample when available. Persisted old
sessions alone cannot appear as current scoreboard context after restart.
Bot-to-bot familiarity stores only bounded exchange counts between fictional
aliases. It increases only after the game acknowledges native speech delivery,
not when the worker submits an RCON packet. Human identities and chat text do
not enter the persistent career ledger.

The existing short public-chat context remains ephemeral. Native chat requires
a human in the match; bot-only backend tests do not bypass that rule. Human
replies retain priority, conversations end after two lines, and all rate limits,
identity checks and off switches remain active. A model outage uses canned chat.
The model does not control combat or learn a new pathfinder.

## Hosting and backup

Build the current game and worker images before applying the AI Compose profile.
The AI profile explicitly enables `T6_CHAT_ENABLED=1` and
`T6_CAREERS_ENABLED=1`. The switches are independent: a career-only worker can
run with chat disabled and needs no model generation. Ordinary source/default
hosting leaves both features disabled until enabled by its operator.

The worker mounts server state read-only at `/data`. A separate `rival-state`
volume is writable at `/rivals`; its `careers.json` is owned by UID 10001 with
mode 600 inside a mode-700 directory. Include this volume in private server
backups. Close/stop the worker before copying its state and retain rollback
images. Corrupt, public or symlinked state fails closed instead of being silently
replaced. Keep runtime state and raw console logs outside the public repository.

The shipped canonical roster has 48 fictional aliases. If customizing it, update
`bots.txt`, personality profiles and the GSC career allowlist together. Unknown
aliases are ignored by career persistence; friend-name bot mode is disabled.

## Backend verification

Audit the owned content without reading or distributing asset contents:

```sh
python3 -B tools/content_inventory.py --game-dir /path/to/owned/BO2 --strict
```

The inventory distinguishes base maps, Nuketown, paid DLC main fastfiles,
configured native-bot modes and separately discovered Zombies files. File
presence is not full integrity, ownership or runtime compatibility verification.
Missing commercial assets must be supplied separately by their owner. Zombies
is a different game mode/runtime and is not implemented by these MP scripts.

Inspect the isolated test plan before running it:

```sh
python3 -B hosting/backend_verify.py --careers --restart
python3 -B hosting/backend_verify.py --run --image outlands-t6:rivals-dev --worker-image outlands-bo2-chat:rivals-dev --careers --restart --process-restart
```

The runner creates labelled disposable volumes and a game container with network
mode `none`, no published ports and only native test clients. Its optional
career worker shares that isolated namespace and mounts game state read-only.
The probe sets native prematch/preround periods to zero before gametype startup;
it does not fabricate human players or match-start notifications. It observes
native kills, scores, role/identity coverage and position changes, and can
exercise a native round restart, worker restart and optional actual server-process
restart with the same disposable volumes. Position changes alone
do not establish navigation quality.

A separate synthetic chat check generates fixtures without RCON or a game
connection. Offline fallback mode is suitable for CI; Ollama mode explicitly
contacts the configured local model and reports which lines came from it:

```sh
python3 -B ai/benchmark.py --mode fallback
python3 -B ai/benchmark.py --mode ollama
```

These lines are never posted into the game. Review tone and grounding separately
from character/transport validation.

Private reports go under `hosting/logs`. The verification GSC is installed only
into disposable test state, never into the live mod payload. Synthetic tests
cover source/privacy boundaries; native tests establish engine behavior. Client
badge rendering, movement feel, public human-chat interaction and human save
retention still require later client playtests.

## Further distinctive features

The working source includes [objective squads and match contracts](SQUADS-CONTRACTS.md).
Further additions include tag reservations, custom match rules and curated events.
Persistent player-strategy imitation,
route learning, a Zombies integration and complete DLC compatibility need
separate implementation and acceptance. Supplying original assets is separate
from shipping original mod code.
