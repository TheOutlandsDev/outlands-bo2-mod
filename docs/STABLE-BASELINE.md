# Stable gameplay baseline

Version 0.1.3 is a reproducible gameplay checkpoint before further content or AI
experiments. The source remains a development preview: account linking, native
HUDs and advanced Armory editing have their own acceptance requirements.

## Hosting profile

The public configuration keeps optional modules disabled until the host has
their worker and runtime ready. To reproduce this gameplay profile, retain the
host's private configuration and apply these nonsecret settings before the next
map load. Never copy another host's configuration, credentials or player state.

```text
set outlands_bot_fill 16
set outlands_bot_idle_fill 16
set outlands_coop_teams 1
set outlands_balance_teams 1
set outlands_bot_difficulty 2
set outlands_rivals 1
set outlands_rival_seed 0
set outlands_rival_movement 0
set outlands_bot_humanize 0
set outlands_bot_objective_roam 0
set outlands_human_metrics 0
set outlands_bot_loadout_variety 1
set outlands_bot_explore_percent 35
set outlands_bot_streaks 1
set outlands_squads 1
set outlands_contracts 1
set outlands_bot_air_reaction_ms 2500
set outlands_bot_air_response_chance 80
set outlands_bot_ground_support 1
set outlands_chat_interval 20
set outlands_chat_max_per_minute 6
```

The total-player target includes humans and bots. Cooperative team assignment
keeps human teammates together and replaces bots to balance team modes. Native
Hard combat remains authoritative; cosmetic levels and prestige do not increase
aim skill. Humanization and both experimental positioning controls remain off.
The Headquarters patrol correction, class variety, squad jobs and streak helpers
remain independent of those experiments.

Chat and persistent fictional careers require the matching optional
[AI worker stack](../ai/README.md). Container hosting enables its fixed local
mailboxes through `T6_CHAT_ENABLED`, `T6_CAREERS_ENABLED` and
`T6_OPERATIONS_ENABLED`; the worker and game must use the same source revision.
The scheduler's twenty-second interval is an opportunity to speak, not a promise
of one delivered message every twenty seconds. Conversations share cooldowns,
context validation and the six-message-per-minute budget.

Account and Armory enablement remain separate host choices. Native human BO2
progression is stored by the game; an Outlands account does not transfer or merge
BO2 saves between machines or servers.

## Native match limits

Each of the eight mode wrappers loads the built-in default and matching mode
configuration without time or score overrides. Native readback gives:

| Mode | Time setting in minutes | Score setting |
| --- | ---: | ---: |
| Team Deathmatch | 10 | 75 |
| Free-for-All | 10 | 30 |
| Kill Confirmed | 10 | 75 |
| Capture the Flag | 5 | 3 |
| Demolition | 2.5 | 2 |
| Domination | 5 | 200 |
| Headquarters | 15 | 250 |
| Hardpoint | 10 | 250 |

These are engine settings, not a universal whole-match duration or total-score
formula. Each mode retains native rounds, overtime and objective rules. After
map initialization, `OUTLANDS_MATCH_LIMITS_V1` records the map, mode, time and score
readbacks without player identifiers. Config changes take effect at map load;
the active round does not need to be interrupted.

For container hosting, updating persistent CFG files or changing a Compose image
reference alone does not update an already-created container. On its next start,
the entrypoint copies mode wrappers and scripts from that container's immutable
image into persistent storage. An older image can therefore restore older limits.
After validating a candidate, recreate only the game service at an agreed idle or
match boundary using the pinned image. Confirm the running image ID, installed
wrapper hashes and fresh native limit receipts. Include a disposable process
restart in acceptance so a one-time volume patch cannot pass as a durable fix.

## Update and rollback

1. Use a versioned source archive and verify `SHA256SUMS`. Preserve the previous
   archive, complete private volumes, settings and working game/worker images.
   Keep the immutable release tags unchanged.
2. Build candidate game and worker images from the same source. Use isolated
   state for the [backend checks](VALIDATION.md), and keep experiments off when
   checking this baseline. Public CI checks source and synthetic fixtures; owned
   game assets and native gameplay checks run separately.
3. Compare every intended installed mod payload with the candidate, preserving
   private settings, native saves, account keys and fictional career storage.
   The file installer refuses differing existing files; do not bypass conflicts
   without reviewing them and preserving a complete backup.
4. Apply a live update at an agreed match boundary. Confirm native initialization,
   the expected limits, bot refill/team counts, worker acknowledgments and absence
   of native/script failures. Recheck joining, earned progression and persistence
   with real clients when the runtime or relevant gameplay code changes.
5. If the update fails, restore the previous game/worker images and matching mod
   payload together. Preserve newer saves and private databases unless a reviewed
   schema change requires restoration from a consistent backup. A source rollback
   alone does not undo files already copied into persistent server storage.

## Further development

Develop new maps, combat presets and movement systems on separate branches and
disposable servers. Compare native metrics across maps and seeds, monitor CPU
and memory, then obtain client gameplay acceptance before promotion. Compilation,
kills, movement counters or an HTTP health response alone do not demonstrate an
improvement. Preserve this version as the rollback checkpoint.

The [native armory expansion draft](ARMORY-EXPANSION-DRAFT.md) records proposed
weapons, camo mastery, repeatable careers and native-menu integration. It is not
implemented content. See [DLC readiness](DLC-READINESS.md) before adding maps.
