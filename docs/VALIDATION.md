# Validation status

This document records project coverage and a repeatable acceptance method.
It contains no personal profiles, player identities, connection details, raw
logs or conversation transcript. Historical acceptance applies to the tested
runtime/configuration; source checks do not rerun gameplay.

## Recorded project coverage

The existing Linux gameplay record uses Plutonium T6 r5369. The Windows client
runtime revision was not independently recorded. Preserve that distinction
when comparing a new runtime or release.

| Area | Existing coverage | Remaining work |
| --- | --- | --- |
| Linux host | Isolated smoke startup, LAN socket, private Tailscale sidecar and no published host ports | Repeat for changed runtime/host images |
| Linux client | Map negotiation, team/class selection, spawning and native bot combat | Wider map and mode coverage |
| Earned progression | After-action rank/weapon increases and client/server restart retention were confirmed in the Linux baseline | Individual unlock, attachment and camo checks |
| Windows client | Joining, spawning and native bot combat were confirmed in the existing project acceptance record | Completed-match rank/weapon results and normal quit/relaunch retention |
| Native population controller | Hard difficulty, 16-player filling, 8v8 team assignment, vacancy/refill and a second human replacing a bot | Repeated joins/leaves, later maps and prolonged failed-add recovery |
| Bot presentation | Custom fictional aliases, blank clan tags, varied native loadouts and cosmetic level calls | Longer-term variation across respawns |
| Optional chat | Compilation, generated response, local RCON, request/native-bot identity validation and native speech | Continue expiry, slot-reuse and team/hidden-chat boundary checks |
| Source checks | Synthetic client, hosting, chat and release tests are provided | Inspect CI for the exact source commit being deployed |

Windows joining coverage does not establish Windows progression persistence.
A score increase, an anonymous server XP line or the Linux result cannot
identify a particular Windows client's saved rank/weapon result.

## Windows preparation methodology

The [Windows guide](WINDOWS.md) contains the input checks, backup/hash procedure,
configuration commands and direct-join fallback. Use a stable unique LAN name,
an explicitly selected runtime and the exact owned game directory.

The source now supports deliberate Windows `--no-password` setup. It writes an
empty password command before the locally supplied connection command and uses
the existing saved-settings launcher. Protected invites continue to require
their nonempty password. Synthetic tests cover the generated CFG, command
injection rejection, conflicting setup options and read-only launch checks.
These tests do not establish a live connection for the new setup option.

Keep evidence in separate stages:

| Stage | What it establishes | What it does not establish |
| --- | --- | --- |
| Release hash comparison | Downloaded bytes match the published digest | Runtime compatibility or game ownership |
| File/input preflight | Required paths and supported values are present | A matching vendor hash, server socket or game join |
| Profile backup and copied-file hash comparison | The selected profile tree was preserved | Saved progression after a new match |
| Tailscale peer reply | Reachability to that authorized peer, possibly through a relay | A direct path, UDP game service or completed join |
| Map/team/class/spawn | The client reached playable state | Completed-match awards or restart retention |
| After-action results | The client observed earned rank/weapon outcomes | Persistence after quitting |
| Normal quit, restart and rejoin | The same identity retained those outcomes | Other maps, modes, unlocks or clients |

A timeout or `PLATFORM_DISCONNECTED_FROM_SERVER` is a diagnostic observation.
Investigate runtime, endpoint, server state and authorization without treating
the error alone as a root-cause determination.

## Controller and rotation checks

The current controller uses native Hard difficulty, 16 slots and a 16-player
fill target. Team modes target 8v8; Free-for-All uses individual players. Dead
players retain slots and native respawning. Only verified native test clients
may be removed when the fill target shrinks.

After three failed additions, bounded retry batches use 10/20/30-second
cooldowns while two-second polling continues. Changes to human count or target
reset the retry state. Disabling and reenabling filling must reuse the same
population manager.

Existing acceptance covers team assignment and a mid-match vacancy/refill
without disconnecting the Windows client. Deliberate prolonged failed-add
fault injection, repeated human joins/leaves and map-change retention remain
pending.

All eight gamesettings wrappers are distributed. Time and score targets are
configured at twice the earlier baseline; native round endings still apply.
Check assets, objectives, team allocation and rotation separately in `dm`,
`tdm`, `ctf`, `dem`, `dom`, `koth`, `hq` and `conf`. Configuration or one
map's readback does not establish acceptance across the full rotation.

## Read-only progression diagnostics

The stock rank script initializes `pers["rankxp"]` as a connection-time
snapshot. Score events call the engine's `addrankxp` directly, so an unchanged
snapshot does not establish stalled earned XP. Read the current DDL value:

```gsc
self GetDStat("playerstatslist", "RANKXP", "StatValue");
```

This diagnostic does not award XP or write stats. An in-session change and a
quit/restart retention result are separate observations. Keep the same saved
LAN name throughout the comparison.

Sources: [native score-event XP](https://github.com/plutoniummod/t6-scripts/blob/main/MP/Core/maps/mp/_scoreevents.gsc),
[native rank data](https://github.com/plutoniummod/t6-scripts/blob/main/MP/Core/maps/mp/gametypes/_rank.gsc),
[LAN name-based identity](https://plutonium.pw/docs/changelog/#r5202).

## Repeatable acceptance sequence

1. Verify the source digest, owned game and selected official runtime.
2. Back up the active runtime's full profile storage and compare file hashes.
3. Run preflight, configure the connection locally and check saved settings.
4. Confirm Tailscale access, join, select a team/class and spawn.
5. Verify native combat, bot filling, team assignment and human replacement.
6. Complete a match and compare after-action rank/weapon results privately.
7. Quit normally, restart the client and rejoin with the same name. Compare
   persistence; test server restart retention separately.
8. Repeat required maps, modes and unlock/challenge checks. For chat, verify
   bounded public replies and rejection of expired or reused-slot requests.

Publish only the tested feature, source/runtime version, method and pass/fail
outcome. Keep player names, profile values, timestamps of personal activity,
addresses, credentials, screenshots, raw logs and receipts private.

MW2 feature parity, persistent bot careers and additional learning behavior
remain future work.
