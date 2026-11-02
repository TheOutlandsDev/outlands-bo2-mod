# Outlands AI Director: first development candidate

This opt-in candidate responds to player reports of static objective guards and
snappy, uniformly skilled combat. It is independent of the earlier three-map
rival positioning experiment. All new switches default off.


The design is inspired by [SAIN's configurable AI architecture](https://github.com/Solarint/SAIN): separate combat, movement, personality and squad modules with reproducible tuning. This is original BO2 code using native engine hooks. SAIN is built for a different game and its navigation, perception and editor are not ported here.

For the supported checkpoint, use the [stable gameplay baseline](STABLE-BASELINE.md):
native Hard combat, humanization off and both positioning experiments off.
Preset availability does not imply a preset improves gameplay.

## Portable presets and module controls

`ai/bot_settings.json` defines validated `relaxed`, `mixed` and `competitive` presets. Each contains bounded shared engine controls, four real combat tiers and guard dwell/travel limits. Cosmetic level and prestige remain separate. The native catalog is generated from that source and must match before packaging:

```sh
python3 -B ai/bot_settings.py
python3 -B ai/bot_settings.py --export-preset mixed > my-preset.json
# After editing the source and validating bounds:
python3 -B ai/bot_settings.py --generate
```

Select `set outlands_ai_preset mixed` in the private server configuration. It is resolved once per map; changes take effect next map. Unknown native selections fall back to the configured default. The verifier rejects unknown presets. Enable modules before loading the map. Combat, objective roaming, streak support, squads and chat retain independent switches. No unsupported vision/hearing controls or live admin GUI are claimed. A BO2-themed administrator editor can build on this schema later.

## Headquarters correction

The squad patrol selector previously overrode native `true` to `false` for attack
roles even when a friendly HQ was safely owned. Native HQ code then kept those
bots at the radio. The selector now preserves the native decision. Neutral,
enemy-owned and contested HQ decisions still belong to the native mode script.

## Combat variation

`set outlands_bot_humanize 1` enables guarded native helper detours for known
fictional rivals only. Developing, regular, experienced and standout profiles
use easy, normal, hard and hard native behavior respectively. Veteran is unused;
cosmetic rank and prestige do not determine skill. Native convergence time,
correction rate and aim error remain bounded by the catalog's combat tier.

In the mixed preset, accepted native combat look targets are filtered over 220–360 ms before being
passed back to the native look helper. New targets start from the bot's current
view direction. No player angles are forced and no new enemy query is made.
The native controller still selects targets, gates fire and navigates.

In the mixed preset, native bot yaw speed is set to 0.85 and the shared native reaction window to
650–1000 ms. These engine settings are global to bots; per-rival variation comes
from the native difficulty and combat helpers, not independent engine reaction
dvars. Missing or already-owned helpers leave native combat intact. Disabling
the feature restores owned global settings and native thinking/FOV fields.
Human inputs, saves, unlocks and XP are never written.

## Short guard holds

`set outlands_bot_objective_roam 1` trials reachable alternate perimeter posts
for Domination and Hardpoint defenders. After arrival they hold for 3–6 seconds
before looking for a different nearby reachable post. Lightweight distance ranking precedes at most twelve native path probes, so random offsets cannot choose a long commute ahead of a nearby alternative. Reassessment can extend the
observed hold slightly. Unfinished travel keeps its post for up to 15 seconds;
combat, remote control and native emergency interactions retain priority. Guard duty yields to the current native threat, rather than a last-attacker history field that persists after a fight.
Role commitment is separate from post selection, so the bot retains its job.
The existing `outlands_squad` goal channel remains the sole custom movement owner.
Invalid choices return to the existing native fallback.

Trial this separately from `outlands_rival_movement`; the verification CLI rejects
enabling both position experiments together. No new navigation mesh, teleport,
learned route model or automatic full-map flanking is implemented.

## Earned streak and package support

`set outlands_bot_streaks 1` starts owner-only listeners for native package landing notifications. A bot can travel to its own reachable package, yielding to combat, bomb interactions, remote control and flag carrying. The native use-radius, use-button hold and reward logic still control collection. Retrieval expires after a bounded `outlands_bot_package_timeout_ms` (default 25000). Bots do not scan the whole map for other players' packages or receive free streaks from this module.

The native care-package deployment helper only attempts a throw within five seconds of spawning. The optional adapter permits an already-owned, charged supply marker to be thrown later in a life when local ground and sky traces allow it. Other native streak helpers and engine use rules stay in control. Remote piloted streaks that stock bots do not support remain outside this first pass. The opt-in `--streaks` backend fixture uses the native quantity-grant path in disposable state, then requires charge consumption after the five-second spawn window, a landed package, an owner retrieval goal beyond the native use radius, and native owner capture. It does not fabricate score or XP. This functional fixture is not proof of organic scorestreak earning or every-map package delivery.

## Native gun and attachment variety

`set outlands_bot_loadout_variety 1` filters repeated primaries while the native bot constructor builds its five custom classes. Every candidate comes from the native unlocked item list, and the original constructor still owns Pick-10 allocation, perks, attachment compatibility and class validity. If the unlocked pool is exhausted, selection falls back to that native pool.

`set outlands_bot_explore_percent 35` permits occasional exploration of other valid assault/SMG/LMG/shotgun classes. It is bounded to 0–60 percent; marksmen retain their capped specialty. Rival favorites and team duplicate penalties still influence the weighted class draw. A bot avoids its previous successfully equipped weapon/attachment setup when another valid choice exists. No class is rebuilt while the bot is fighting, and no unsupported attachment stack is granted. Native construction supplies random compatible attachments; using more of those distinct valid classes makes them visible in combat.

The `--loadouts` verifier independently replays construction against the observed native item pools, compares the full requested and actually carried attachment sets, and requires multiple guns, attached variants and real respawn grants. Cosmetic levels do not grant human unlocks.

## Active contextual conversations

The scheduler retries a due opener without waiting another full interval after a busy mailbox. Player replies and ongoing exchanges have priority. Ambient openings alternate native squads/objectives/contracts with casual Outlands lobby topics about next-spawn classes and another match. Four-turn exchanges occur more often, but share the existing six-message-per-minute cap and per-bot cooldown. Bot replies refer to the preceding delivered line; changing tactical state still invalidates stale claims. Casual lobby exchanges carry no task fields, so unrelated assignment or contract changes no longer cancel them. No invented server announcements, admin authority or player impersonation is added. The server continues to identify the cast as AI.

## Backend verification

Use private images and fresh disposable state. The examples do not change a live
server or publish ports:

```sh
python3 -B hosting/backend_verify.py --run --image outlands-t6:humanize-baseline --rivals --human-metrics --squads --contracts --case mp_raid:dom --seconds 120
python3 -B hosting/backend_verify.py --run --image outlands-t6:humanize-candidate --rivals --humanize --objective-roam --squads --contracts --case mp_raid:dom --seconds 120
python3 -B hosting/backend_verify.py --run --image outlands-t6:humanize-candidate --rivals --humanize --squads --contracts --case mp_dockside:hq --seconds 180
python3 -B hosting/backend_verify.py --run --image outlands-t6:humanize-candidate --rivals --humanize --streaks --case mp_raid:tdm --seconds 150
python3 -B hosting/backend_verify.py --run --image outlands-t6:humanize-candidate --rivals --humanize --loadouts --case mp_raid:tdm --seconds 150
```

Always pin a matching current worker explicitly with `--worker-image` when
adding careers, Armory or chat fixtures. An older development worker can lack
new mailbox methods even when the game image is correct.

Acceptance independently validates native profile parameters, real helper use,
bounded filtered combat steps, accepted guard repositioning after an arrived
hold, and preserved native HQ patrol decisions. Off cases must emit no custom
combat or guard decisions. Existing class validity, objective scores, bot fill
and crash checks remain gates.

`set outlands_human_metrics 1` enables private diagnostic receipts. Half-second
objective holds and yaw changes are descriptive counters. They do not identify
path failures or prove visually smooth aiming. Compare baseline and candidate
across maps/seeds, then playtest aim, movement, fairness and objective competence.
Preserve a rollback and apply only at an agreed match boundary.


## Performance and gameplay regression gates

Combat presets remain experimental. Keep `outlands_bot_humanize 0` when the
native combat baseline plays better. The off switch delegates the existing
helpers back to native behavior and restores owned engine controls and bot
thinking/FOV fields; it leaves weapon variety, careers and chat independent.
A preset that merely compiles, moves bots or produces kills has not demonstrated
an improvement in combat or objective play.

The optional `--ai-quality` verification probe records real bot weapon discharge
and damage events, first-observed shot/damage latencies, alignment toward a
native visible target, movement, objective-zone presence, crowded movement,
stationary travel candidates and goal changes. It runs only in disposable,
loopback-bound native tests and is never installed into the live mod payload.
No targets, damage, score, positions or player identities are manufactured.

```sh
python3 -B hosting/backend_verify.py --run --image YOUR_TEST_IMAGE --case mp_raid:conf --seconds 150 --rivals --loadouts --human-metrics --ai-quality
python3 -B hosting/backend_verify.py --run --image YOUR_TEST_IMAGE --case mp_raid:conf --seconds 150 --rivals --loadouts --humanize --ai-quality
```

Compare combat with objective roaming disabled, then compare roaming separately
with combat held fixed. Retain raw receipts, image/source identities, loadout and
roster composition, map/mode, observation lengths, CPU/memory measurements and
all partial or failed cases. Repeat across seeds/maps before promoting new
behavior. The planner seed does not reproduce the entire engine simulation.

Damage-event counts per discharge are not literal accuracy: pellets and
penetration can produce multiple damage events. First-event latencies exclude
uncompleted encounters and are affected by observation cadence and survival;
they must be read alongside firing/damage activity, never alone. Objective-zone
time is not capture credit. A stationary travel candidate is not proof of being
stuck. More movement or more accepted post changes does not establish better
navigation. Actual client feedback remains a separate acceptance gate.
