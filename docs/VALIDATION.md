# Validation guide

Validate source logic, native-engine integration and client gameplay separately.
A source package or healthy container does not establish progression retention,
rendered badges, movement quality or compatibility across every map and runtime.
This guide contains reusable procedures; keep individual playtest records,
identities, addresses, profiles and raw logs outside the public repository.

Account mailbox delivery must pass the combined native fixture with the same
script and worker protocol intended for the host. Its production retry queue
must recover a deliberately dropped datagram and dropped consumption ACK while
Armory/career responses are active. A single successful UDP send is insufficient.
Receipts contain only the opaque request nonce, never its pairing code. The
readable private code, real player ownership and observed rank after reconnect
remain separate client acceptance checks; never fabricate a human native profile.

## Automated source checks

From the project root:

```sh
python3 -B tools/validate_system.py
```

This writes a source-bound private report and runs the checks below plus both
fallback chat benchmarks and Linux Bash parsing. It leaves native/UI/client
acceptance explicit. See [UI development gates](UI-VALIDATION.md) for the screen,
input and future mid-match class-editor acceptance requirements.

Individual checks remain available:

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
3. Confirm each numbered exchange stops at its explicit two-to-four-line limit,
   human replies take priority,
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
The older `--chat-context` run explicitly tests the optional human-audience
guard with no-audience chat disabled. The new `--ambient-chat` run enables
production idle fill and requires matching native deliveries through a real
worker, including a different bot's answer. It uses fallback mode in offline
containers; see [rotation and idle-match testing](ROTATION.md). Synthetic
fixtures and direct `sayall` calls cannot satisfy that transport acceptance.
Actual human-chat interaction and rendering still need real clients.

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

## Grounded task chat

Unit checks validate V2 context, objective-state enums, task-specific fallback
wording, conflicting orders, unsupported proximity/completion claims, same-team
and contract-phase reply pairing, legacy V1 input, shared rate limits and human
reply priority. Host migration tests retain an explicit task-context off switch.

The native runner's `--chat-context` option captures each real bot's current
assignment and team board through the production formatter. Its map preflight
requires a nonempty main fastfile before creating test state; supporting assets
still need actual engine loading. Require valid squad/objective/contract topics
where supported, the zero-human request refusal, the context off switch and no
production speech acknowledgements. A direct native speech primitive in the
isolated probe is a separate check, not full production-chat acceptance.

Feed those private snapshots to the model benchmark without RCON or a game
connection. Report accepted model versus fallback lines and bounded output.
Human client acceptance remains necessary for visible dialogue, naturalness,
frequency, same-team exchanges and stale task rejection during actual play.
Do not publish raw snapshots, generated chat logs or runtime diagnostics.

## Cooperative lobby placement and repair

Run the isolated `--lobby-balance` checks described in the squad/contract guide
for selected team modes. Require ordered native observations of 8v8 baseline,
15 connected bots after departure, refill to 8v8, 9v7 imbalance, repair, disabled
9v7 and resumed 8v8. Missing, duplicate or reordered evidence fails acceptance.
The native count-policy fixtures cover initial side choice, later joins, side
swaps and overflow at capacity. They are not actual human joins.

With two real clients later, join using auto-assign and explicit opposite-side
selection. Both should land on the same side with six friendly bots against
eight opponents after the fill settles. Disconnect/reconnect one client, test
spectating and a native halftime swap, and confirm no human is kicked by repair.
Check FFA separately and verify earned player/weapon progression after restart.
Chat visibility and naturalness still require human client acceptance.

## Mild anti-air tuning

Add `--air-response` to a disposable native run lasting at least 60 seconds,
without restart flags. The probe uses real native bots and private script-origin
entities tagged as UAV/counter-UAV to exercise the actual threat-filter detour.
Require the initial timer to block selection, eventual eligibility, stable
deadlines across interleaved targets, 0/100 percent participation boundaries,
stock override and native-ignore precedence. Player and ground classification
must remain excluded. These are script-entity policy checks, not flight combat.

Later call in an earned UAV, counter-UAV and attack helicopter from real clients.
Compare time to first bot rocket and streak survival with default tuning versus
0 ms / 100 percent. Confirm bots still counter aircraft and keep their normal
ground combat. Adjust these small values based on playtest feedback.


## Ground-streak EMP support

Run a private native image containing the candidate source with:

```sh
python3 -B hosting/backend_verify.py --run --image your-private-candidate \
  --case mp_raid:dom --seconds 90 --ground-response \
  --report-dir hosting/logs/ground-response-check
```

Use a fresh report directory. The harness creates disposable, network-isolated
state with no published ports, human identities or saves. Selected native bot
subjects receive a temporary damage guard during timed equipment checks. Stock
ignore deadlines and an owned hold goal isolate one subject from player combat;
the previous damage handler, ignore entries and goal are restored afterward.
These are controlled engine fixtures, not normal match or lane-movement proof.

The fixture needs a team mode, ninety seconds and no restart, air, UI, Armory,
lobby, account or ambient-chat fixture. Require native hostile/friendly/unowned/
inactive/carried/destroyed/sentry/player classification, stable reaction timing,
natural item unlock eligibility, one adapted specialist and a one-for-one
tactical replacement. Require an actual native EMP `grenade_fire` entity and
consumed ammunition, cooldown refusal, no refill after use, stale-target expiry
and the off switch. Verify stale input ownership, normal release and cleanup
after a real bot suicide. No input diagnostic can substitute for the production
responder's projectile. Missing, malformed or duplicate receipts fail acceptance.

The turret entity has a native model and metadata; its earned Guardian beam is
not activated. Streak destruction and native beam avoidance remain unverified
by this fixture. Re-run `--air-response` separately for aircraft timing policy.
The harness invokes its shell wrapper through Bash, including source archives
that do not retain executable bits.

Real-client acceptance remains necessary: earn and place a Guardian on a busy
lane, observe the next eligible bot spawn and approach, verify its EMP effect
and native Guardian survival/destruction, and try repeated Guardians and sentries.
Check that objectives, natural movement and the existing mild anti-air tuning
remain comfortable. Confirm bot responders cannot refill tacticals in one life
and that player loadouts and saved progression remain unchanged.


## Outlands Operations acceptance

Run the regression suites and `ai/conversation_benchmark.py --mode fallback`
without a game/model. Optional `--mode ollama` uses synthetic conversations only;
review relevance and tone in addition to transport/grounding gates. Never inject
synthetic human observations into live game state.

Use `hosting/backend_verify.py --run --expansion --chat-context --squads --contracts`
with private candidate images and disposable state. It waits for actual native
bots before checking exclusion and formats all four dialogue turns using the
production serializer. Synthetic milestone tests cover commit/retry/restart and
selection independently from that native integration.

With real Windows and Linux clients later, use public `!career` and `!track
objective`. Earn personal kills and contribute score to a team-points or
combined-score contract before completion. Check the private notification, then
reconnect, rotate maps and restart the client/server while retaining profile and
private ledger. Confirm native BO2 XP/unlocks remain unchanged by the Operations
path. Check duplicate-name/identity behavior deliberately in private test profiles.
Public documentation must not contain raw identity values, chat or state files.
