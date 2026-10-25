# Validation status

Last updated: 2026-10-25. The tested game runtime is Plutonium T6 r5369.
These results describe the private development acceptance tests; they are not a
claim that every OS, runtime update, map or progression challenge has passed.
Raw logs, private receipts, join details and profile backups stay outside the
public source repository.

## Verified playable baseline

| Check | Result |
| --- | --- |
| Private Linux container startup | Healthy LAN dedicated server, diagnostic GSC initialized and game socket bound |
| Isolated smoke test | Network mode `none`, separate state, no published ports; repeat startup passed |
| Tailscale topology | Separate authorized sidecar, shared game network namespace, no host port publication |
| Linux human connection | LAN client completed connection/map negotiation, selected team/class and spawned |
| Native bot population | One human plus 11 native test clients reached the 12-player target |
| Combat | Native bots moved/fought and human/bot scores increased |
| Ranked flag | Human spawn reported `ranked=1` |
| Earned awards | Player confirmed increased rank XP and weapon progress in the after-action report |
| Live DDL XP | Human rank XP increased from 21,158 to 22,858 during continuing combat |
| Normal quit | Client closed through the in-game quit path; game-profile files changed |
| Full restart persistence | Player confirmed the earned progression remained after client and server restart |

The progression confirmation is the player's observed result. Increasing match
scores alone was not used to infer XP. Specific rank unlocks, attachments and
camo challenges have not all been checked individually.

## Current presentation and chat checks

| Check | Result |
| --- | --- |
| Native custom aliases | Runtime assignment from the source roster verified |
| Native loadout variety | Four bots used distinct shotgun, LMG, sniper and SMG loadouts, varied attachments/secondaries and custom/default classes |
| Cosmetic level API | Assigned levels 18, 17, 10 and 51; guarded native `setrank` calls completed without errors |
| Scoreboard presentation | Player confirmed the default `BOT` clan tags are gone and different cosmetic levels look correct |
| Chat GSC | Isolated r5369 startup healthy; native `sayall` resolves and the adapter initializes |
| Local RCON | Private loopback control path verified |
| Live chat events | Banter and a human public-chat reply event emitted during a 1-human/11-bot match |
| Ollama generation | One cold-model fallback, followed by three successful model generations |
| Native chat delivery | Generated replies passed local RCON, pending-request/native-bot identity validation and `sayall`; at least three GSC delivery acknowledgements |
| Current deployment | Updated game, Tailscale and Ollama services healthy; chat worker running during human play |

Observed aliases included QuietSparks, WinterByte, NightLedger and CometRidge.
Current weapons included `870mcs`, `qbb95`, `dsr50` and `pdw57` with differing
attachments. The assigned cosmetic levels and native calls are verified, and
the player confirmed correct blank clan tags and different rendered levels.
Separately, live
logs now verify the full chat generation-to-native-speech path during human
play. The earlier `say` method failed to resolve on r5369; the adapter now uses
the successfully compiled and invoked native `sayall` method.

## Implemented, awaiting acceptance

- Windows client setup and actual joining/spawning over Tailscale.
- Longer-term loadout variation across respawns. The isolated native
  weapon/class variety check has passed.
- Multiple-human bot replacement, map-change retention and longer-session
  stability across the configured maps.
- Individual earned rank unlock, attachment and camo challenge checks.

The native fill controller already passed live combat acceptance. The new
presentation and chat layer preserves native movement/combat and never
classifies bots as humans or fabricates latency. Cosmetic levels use native
`setrank` only on verified test clients after stock loadout initialization;
they add no human XP/unlock or DDL-stat writes. Native bot loadout unlock
eligibility is unchanged.

## XP diagnostic correction

The first probe watched `pers["rankxp"]`, a connection-time snapshot initialized
by the stock rank script. Normal score events call the engine's `addrankxp`
directly, so an unchanged snapshot did not establish that earned XP had stopped.
The current read-only probe instead calls:

```gsc
self GetDStat("playerstatslist", "RANKXP", "StatValue");
```

It never awards XP or writes DDL stats. The corrected probe compiled and reached
healthy startup in an isolated container test. A live DDL change establishes an
in-session value; the separate quit/restart acceptance establishes retention.
Keep the same saved LAN name when repeating that test, because changing the
name selects a different LAN identity.

Sources: [native score-event XP](https://github.com/plutoniummod/t6-scripts/blob/main/MP/Core/maps/mp/_scoreevents.gsc),
[native rank data](https://github.com/plutoniummod/t6-scripts/blob/main/MP/Core/maps/mp/gametypes/_rank.gsc),
[LAN name-based identity](https://plutonium.pw/docs/changelog/#r5202).

## Repeatable acceptance sequence

1. Prepare the owned game and official runtime, run the isolated smoke test,
   and start the private LAN host without published ports.
2. Import a private invite and join with a stable, unique player name. Select a
   team/class; verify the ranked flag and native fill to the configured target.
3. Fight bots, complete the match and record after-action rank/weapon results.
4. Quit normally, fully restart client and server, then rejoin with the same
   name and compare the earned results.
5. Check named unlock/challenge outcomes, map rotation and a second player on
   Windows. Record each result separately.
6. For the new presentation/chat milestone, inspect alias/tag display and
   confirm one bounded bot reply, no hidden/team-chat forwarding and no response
   to an expired request or a slot reused by a human.

MW2 feature parity, persistent bot careers and additional learning behavior are
future work, not completed acceptance results.
