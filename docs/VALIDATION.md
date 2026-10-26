# Validation status

Last updated: 2026-10-25. The Linux host runtime is Plutonium T6 r5369.
The Windows preparation record does not independently establish its runtime revision.
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

## Windows preparation, 2026-10-25

The following checks were performed on a Windows client using the v0.1.1
source release before the later successful joining test. The table records that
earlier preparation snapshot; local identities,
network addresses, connection settings, profiles and raw logs remain private.

| Check | Result |
| --- | --- |
| Release integrity | Downloaded source ZIP matched the SHA-256 digest published with the GitHub release |
| Owned BO2 multiplayer inputs | Executable and required multiplayer core fastfiles present |
| Existing Plutonium inputs | Expected bootstrapper and multiplayer runtime executable present; file presence is not a runtime-version or vendor-hash verification |
| Windows PowerShell preflight | Setup `--dry-run --skip-updater` passed with explicit game/runtime paths and a valid player name; no game launched |
| Local no-password launcher | Prepared privately; its read-only file/name checks passed, without proving launch or joining |
| Profile preservation | Existing active `storage/t6` tree copied before setup; every copied file matched its source SHA-256 |
| Tailscale | Local service running; the hosting peer replied through a relay, without establishing a direct path |
| Game UDP query | `getinfo` and `getstatus` probes received no reply within the bounded check; this does not prove the game port reachable or the cause of a timeout |
| Client log review | A bounded review found `PLATFORM_DISCONNECTED_FROM_SERVER`; cause remains unresolved |
| Joining, team/class selection and spawning | Pending at preparation; subsequently confirmed by the player and host |
| Bot combat and completed match | Bot combat subsequently confirmed; completed-match progression results remain pending |
| Rank/weapon results and quit/relaunch retention | Pending Windows acceptance |

The no-password path uses a local CFG that clears `password` before `connect`.
It was prepared for a host-requested password change; that host change and a
successful passwordless connection were not independently verified in the
preparation session. Subsequent host checks verified empty runtime game-password
configuration and a successful Windows join with native bot combat.
v0.1.1's stock Windows setup/join validator still requires a nonempty password;
the [Windows joining instructions](../README.md#windows-checks-and-direct-joining)
describe the direct LAN launch and console alternative.

Preparation checks and a profile backup do not complete Windows gameplay
acceptance. Finish the repeatable sequence below with the same LAN name, record
after-action rank and weapon progress, quit normally, then rejoin after a full
client restart. Server restart persistence is a separate check.

## Implemented, awaiting acceptance

The maintenance update configures native Hard difficulty (`bot_difficulty 2`
and `outlands_bot_difficulty 2`), 16 slots with a 16-player fill target, and a
15-installed-map rotation across eight native bot modes. Team modes are
configured for 8v8; Free-for-All uses individual players. The game container
has been restarted for this configuration. Live checks on Raid / Domination
confirmed native Hard tuning (reaction 400–700 ms, FOV 100, fire timing
400–600 ms), both difficulty values at 2, capacity/fill at 16, and two humans
plus 14 native bots with increasing scores. The Windows client rejoined.
The game, Tailscale and Ollama services were healthy and the chat worker was
running, with no published host ports. The verified 12-player baseline above
remains the earlier evidence.

The follow-up update replaces permanent shutdown after three unsuccessful
native additions with bounded retry batches and 10/20/30-second cooldowns.
The same controller continues polling and resets its retry state when the
human count or fill target changes. Disabling the controller pauses it, so
reenabling it can resume without creating a second population manager.
Read-only population diagnostics distinguish connected players from assigned
teams; dead players retain their slots and native respawning.

On Raid / Domination, live diagnostics confirmed one human plus 15 bots with
eight players assigned to each team and no spectators or unassigned players.
During ongoing combat, temporarily reducing the target to 15 removed only a
verified test client. Restoring 16 produced a replacement bot: the observed
population went 16 → 15 → 16 while the Windows player remained connected and
combat scores increased. A second human subsequently joined; the roster
settled at two humans plus 14 bots, still eight assigned players per team.
No new script compile/runtime errors were observed. The prolonged failed-add
cooldown path has not been deliberately fault-injected on the live server.

All eight deployed gamesettings wrappers match the image payload and use twice
the earlier time and score limits, including TDM and Free-for-All. Raid's
authoritative `getgametypesetting("scorelimit")` readback was 200. Other native
round rules remain in effect; doubled score limits alone do not override CTF
overtime or Demolition bomb/round endings. The README lists each configured
time and score value. Full gameplay acceptance across all eight modes remains
pending.

Pending maintenance checks are the player's assessment of harder behavior,
team allocation across later maps/rounds, client assets for every selected map, and
objective behavior/rotation in `dm`, `tdm`, `ctf`, `dem`, `dom`, `koth`, `hq` and
`conf`. No new progression or persistent-learning result is inferred.

- Windows rank/weapon progression retention after a normal client restart.
  Windows joining, spawning and bot combat were confirmed by the player and
  the server; anonymous server XP lines alone do not identify Windows gains.
- Longer-term loadout variation across respawns. The isolated native
  weapon/class variety check has passed.
- Bot replacement over repeated human joins/leaves, map-change retention and
  longer-session stability across the configured maps.
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
