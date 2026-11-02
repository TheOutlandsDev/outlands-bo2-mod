# Seeded rival match tendencies

This opt-in candidate layers stable fictional preferences over the existing
native bot controller, class pools and objective squads. It does not replace
navigation, aim, combat, native class generation, human progression or saves.

## Persistent characters and match variation

`ai/rival_profiles.json` defines the existing 48 fictional aliases, their role,
favorite primary references, aggression, teamwork, preferred approach and tier.
Six familiar aliases have a shot-caller or flanker specialty. Native names and
teams remain engine-owned: this version plans around the **observed** roster.
It cannot guarantee a particular rival appears, exactly one specialist on both
teams, or a fixed skill-tier composition. At most one eligible specialty per
team receives the extra attack-assignment influence. Other specialists retain
their ordinary role. Team counts remain the existing fill controller's job.

The seed varies bounded aggression/teamwork tendencies, approach preference and
12–20 second role commitment. Experienced characters have less variation and
longer commitments. Tiers describe tactical consistency; they do not change
native aim difficulty or derive power from cosmetic level/prestige. The separate
[humanization candidate](BOT-HUMANIZATION.md) optionally adds real combat-tier
variation; it defaults off. The fixed
catalog persists character identity without touching the private career ledger.
Unknown aliases fall back to the existing profile behavior.

`outlands_rival_seed 0` draws a fresh seed once per map. An explicit seed from
1 through 65520 allows the portable planner to replay decisions given the same
observed roster, map/mode, class pools and decision counters. It never reseeds
the engine RNG. The native roster, combat, movement and outcomes are not a
deterministic replay. Seeds and native decision receipts remain private runtime
diagnostics; public releases contain only code, fictional profiles and methods.

## Native classes and squad jobs

The class adapter weights only members of the existing native-derived role pool.
Favorite weapons are ranked preferences when present in the valid pool;
attachment suffixes are normalized before matching or counting duplicates. Already
selected teammate primaries reduce duplicate-choice weights. Missing favorites
leave the valid pool available. Existing marksman caps, native preset fallback,
unlock/class generation and emergency anti-air decisions remain authoritative.
The adapter never constructs arbitrary attachments or writes a human class.
A bot-only spawn wrapper waits at most two seconds for native loadout
initialization, validates the chosen native slot and stages its mapped class
then uses the native class-grant helper during the initial 500 ms of each spawn.
Actual carried-primary receipts independently confirm first-life and later-respawn
grants. Missing readiness/validity falls back to the original callback. There is
no mid-life weapon swap. Native emergency air-response choices retain authority. The wrapper composes with the human Armory callback.

Squads rank eligible bots for attack and defend duties using role suitability,
aggression/teamwork and active specialty. A bounded incumbent preference and
commitment reduce reassignment. Invalid objectives, team changes and urgent
native interactions still release custom duty. Existing accepted-goal context
continues to ground tactical chat. Approach metadata alone is not advertised as
an executed flank, arrival or capture.

## Separate positioning experiment

`outlands_rival_movement 1` enables a deliberately small experiment on Raid,
Hijacked and Carrier in Domination/Hardpoint. It applies only where the existing
squad module already selects a defender's objective-perimeter node. At most six
candidates are tested with native `findpath`; distance, nearby friendly players
and their unexpired reserved positions,
preferred perimeter depth and the bot's own last two death locations affect cost.
Personal danger expires after 45 seconds. It stores no enemy positions or human
identity and grants no knowledge of hidden opponents.

Selected positions are bound to the current objective assignment and held for
the character's bounded commitment period;
native combat, carrier/plant/defuse priorities and recovery remain in place.
No reachable experimental candidate returns to the existing selection path.
The same module-owned goal is used; no second navigation controller is started.
This is defensive positioning, not new map meshes, learned full-map flanks,
automatic path repair, Guardian recognition or proof of improved movement feel.

## Isolated comparison and acceptance

All new switches default off. Existing private host choices are preserved during
configuration migration. Use an isolated candidate image and a fresh private
report directory for every run:

```sh
python3 -B -m unittest discover -s ai/tests -p test_rivals.py
python3 -B ai/rivals.py --seed 17 --map mp_raid --mode dom
python3 -B hosting/backend_verify.py --run --image outlands-t6:rival-planner-dev --rival-metrics --squads --contracts --case mp_raid:dom --seconds 90
python3 -B hosting/backend_verify.py --run --image outlands-t6:rival-planner-dev --rivals --rival-seed 17 --squads --contracts --case mp_raid:dom --seconds 90
python3 -B hosting/backend_verify.py --run --image outlands-t6:rival-planner-dev --rivals --rival-movement --rival-seed 17 --squads --contracts --case mp_raid:dom --seconds 90
```

Repeat baseline and candidate observations on the three trial maps and multiple
seeds. The runner uses labelled disposable volumes, network `none`, no published
ports and actual native test clients. Production saves and services are unused.
Native profile fields and weighted class draws must independently match Python
rules. Position receipts must report reachable candidates and replayable costs.
Disabled features must produce no plan/class/position receipts. Enabled cases
require at least eight valid first-life grants and four valid later-respawn
grants per stage, independently checked against the weapons actually carried.

Aggregate metrics include actual carried-primary variety (normalized across
attachments and including preset classes), movement between samples, distant-goal
travel intent, stationary travel candidates, teammate proximity, goal/duty
changes and measurement timing. Respawns reset movement baselines; defenders and
combat are excluded from the stationary-travel heuristic. These counters are
diagnostics, not proof of path failure or human-like navigation. Contract/native
score observations independently establish gameplay activity.

Retain failed receipts, check native errors, map reload/worker compatibility and
off behavior, then compare distributions rather than selecting a favorable seed.
Human movement feel, fairness, class readability and full client acceptance
remain playtest gates. Live deployment requires a separately agreed match boundary.
