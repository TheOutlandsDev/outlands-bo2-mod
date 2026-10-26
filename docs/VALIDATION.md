# Validation guide

Validate source logic, native-engine integration and client gameplay separately.
A source package or healthy container does not establish progression retention,
rendered badges, movement quality or compatibility across every map and runtime.
This guide contains reusable procedures; keep individual playtest records,
identities, addresses, profiles and raw logs outside the public repository.

## Automated source checks

From the project root:

```sh
python3 -B -m unittest discover -s tests -v
python3 -B -m unittest discover -s ai/tests -v
python3 -B ai/bridge.py --check
python3 -B tools/build_release.py
```

GitHub Actions also checks Bash syntax and runs Windows PowerShell 5.1 parsing
and synthetic client fixtures. Inspect the Actions result for the exact commit.
These checks use synthetic inputs and do not launch BO2, download game assets,
contact a model or prove a working Tailscale game connection.

## Isolated native-engine checks

1. Supply owned game files and the official runtime as described in the
   [hosting guide](../hosting/README.md). Back up complete persistent server
   storage before an update and retain a rollback image.
2. Run `./manage.sh check` and `./manage.sh smoke` from `hosting/`. The smoke
   stack uses network mode `none`, separate state and no published ports.
3. Confirm script initialization, a bound game socket and absence of GSC errors.
   Startup alone does not establish bot combat or a working client connection.
4. For custom engine probes, use disposable smoke storage only. Verify native
   test-client identities, role assignment, class-pool and patrol-hook execution,
   bounded level/prestige ranges and a native map restart. Probe scripts must
   remain outside the live mod payload and live server state. Original probe
   source is included for reproducible disposable verification.
5. Stop the isolated server. Promote only the intended source payload, preserving
   private access settings and operator-selected configuration.

## Client preparation and joining

The [Windows guide](WINDOWS.md) includes full-storage backup/hash commands,
explicit runtime paths and the current Windows `--no-password` setup option.
Protected invites retain nonempty passwords; no-password mode cannot be combined
with `--invite`. Test the actual connection separately from synthetic CFG checks.

1. Close BO2 and back up the active Plutonium runtime's complete `storage`
   directory. Include `storage/demonware` and `storage/t6`; verify copied file
   hashes. Keep the same runtime and a stable, unique LAN name across launches.
2. Verify the source ZIP against its published `SHA256SUMS`. Run the platform
   setup helper with `--dry-run` before applying configuration. File presence
   does not establish runtime compatibility or successful game launch.
3. Authorize the client on the host's tailnet, then join in LAN mode using a
   private invite or the documented direct-console path. Tailscale ping checks
   peer reachability; test the actual game connection separately.
4. Select a team and class, spawn and verify native combat. Repeat with two
   clients simultaneously and distinct names. Record each platform separately.
5. If joining fails, inspect bounded private client/server diagnostics. A
   disconnect string or missing UDP query response alone does not identify the
   cause. Avoid publishing raw logs or connection details when reporting a bug.

## Progression and persistence

Record rank, weapon progress and a specific earned unlock before a match. Earn
normal awards, finish the match, and inspect the after-action report. Quit
through the normal game menu, fully relaunch, rejoin with the same saved LAN
name and compare the values. Test a server restart separately from a client
restart. Repeat for each platform and for individual attachments or challenges
that matter to the deployment.

The optional read-only probe uses the current native DDL value:

```gsc
self GetDStat("playerstatslist", "RANKXP", "StatValue");
```

`pers["rankxp"]` is a connection-time snapshot; an unchanged snapshot cannot
establish that earned XP stopped. Increased scores or live DDL XP alone cannot
establish saved progression. The probe does not award XP or write DDL stats.
Keep numeric results and profile backups private.

Sources: [native score events](https://github.com/plutoniummod/t6-scripts/blob/main/MP/Core/maps/mp/_scoreevents.gsc),
[native rank script](https://github.com/plutoniummod/t6-scripts/blob/main/MP/Core/maps/mp/gametypes/_rank.gsc),
[LAN identity behavior](https://plutonium.pw/docs/changelog/#r5202).

## Bot population, classes and movement

| Area | Acceptance check |
| --- | --- |
| Population | Fill to the configured total, counting connected humans and bots; dead players retain slots |
| Team allocation | Verify 8v8 in team modes at the default 16-player target; check spectators and unassigned players separately |
| Mid-match refill | Reduce the target, restore it and confirm only native bots are removed/replaced while clients stay connected |
| Join/leave | Repeat human joins/leaves and map changes; confirm bot replacement and controller recovery |
| Failed additions | In disposable state, exercise repeated native-add failures and the bounded 10/20/30-second retry cooldown |
| Display identity | Inspect fictional aliases, blank clan tags, varied valid levels/prestiges and stability across respawns |
| Classes | Observe all five roles, valid primary/secondary equipment, native fallback and anti-air choices across multiple lives |
| Movement | Assess navigation, objective participation and recovery across maps; hook execution alone cannot establish better movement |

Run the checks across `dm`, `tdm`, `ctf`, `dem`, `dom`, `koth`, `hq` and `conf`.
Confirm clients own every selected map, each mode loads its wrapper, and native
time/score readbacks match the [configured limits](../README.md#map-and-mode-rotation).
Native overtime, bomb and round endings still apply. Longer sessions should
exercise repeated rotations and reconnects.

## Optional chat

1. Run worker tests and configuration checks before enabling chat. Use synthetic
   event fixtures for malformed records, expired requests, reused slots, unsafe
   text, rate limits, queue priority and off switches.
2. On a private test host, verify one banter opener, one answer by a different
   bot, and a public human-chat reply. Confirm native `sayall` delivery in game;
   a worker submission alone does not establish speech delivery.
3. Confirm the exchange ends after two lines, human replies take priority,
   shared budgets apply to both turns, and no ambient chat occurs without a
   human. Test disconnects and slot reuse before delivery.
4. Test both a cold/unavailable model's canned fallback and a warm-model reply.
   Confirm the dialogue switch disables followups and the global switch clears
   queued speech. Do not forward team or hidden chat.

The [chat guide](../ai/README.md) specifies the protocol and bounded context.
Keep player text, generated conversations, private credentials and raw console
logs out of public test reports. Publish only technical outcomes and limitations.

## Unattended rival integration

The [rival guide](RIVALS.md) documents the disposable all-bot runner. It exercises
normal native match startup with zero prematch periods, guarded bot profile
restores, native counters, round restart and private-ledger worker/server
restarts. No real or fabricated human client is required. Inspect generated
private reports for the exact image and selected map/mode pairs.

The source tests cover private atomic ledger writes, replay/counter-reset
handling, roster restrictions, current-context freshness and delivery ACKs.
No-human runs keep production chat's human-presence guard intact. Synthetic
chat fixtures and a native function call are separate from a full human-chat
interaction acceptance result.

## Squads and contracts

Follow the [squad and contract guide](SQUADS-CONTRACTS.md) for configuration and
isolated native checks. Require actual native objective-goal acknowledgements,
valid role caps, real counter progress and completed contracts. Metadata or
nonzero counters carried from an earlier round are insufficient. Exercise off
switches, unsupported modes and round/server restarts independently.

Later, verify human-facing notifications, tactical balance and normal earned
progression with real clients. An all-bot backend run cannot establish those.

## Scope limits

Native pathfinding and combat remain authoritative. Random cosmetic ranks are separate
from the optional fictional-bot career ledger. Persistent learning, player-strategy imitation,
custom route training and MW2 feature parity are future work. Evaluate new
presentation, movement and dialogue changes in human gameplay before describing
them as accepted.
