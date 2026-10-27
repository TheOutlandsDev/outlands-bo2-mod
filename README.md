# The Outlands BO2 Mod

Private Black Ops II multiplayer over Tailscale, with native AI opponents and
normal earned rank and weapon progression. Linux and Windows clients use
Plutonium LAN mode and connect directly to the private host. No Plutonium
server key is needed for this LAN path.

The source provides native bot filling, configurable identities and class roles,
optional local Ollama chat, and client setup helpers. See the
[implementation methodology](docs/METHODOLOGY.md) for architecture and
[validation guide](docs/VALIDATION.md) for reproducible checks.

This repository contains original mod source and setup tools. Supply your own
legitimate BO2 installation. Game files, Plutonium binaries, model weights,
private invites, credentials and player saves are not distributed here.

## Join a private game

Install BO2, [Tailscale](https://tailscale.com/download) and the prerequisites
for your platform. Join the host's tailnet or obtain access to its hosting node.
Ask the host for a private invite file; keep it outside the source repository.
LAN joining uses direct connection, without the online server browser or friends
system.

Linux needs Python 3, Steam and an installed Proton runtime. Linux support is
community maintained. From this source checkout, run:

```sh
bash setup-client-linux.sh --invite /private/outlands.invite.json
./play-outlands-linux.sh
```

Without an invite file, start the interactive setup with:

```sh
bash setup-client-linux.sh
```

Starting setup through `bash` also works when a source archive lacks executable
file permissions. Setup enables the Linux launch helpers on its apply path.

Windows needs Windows PowerShell. Open a terminal in this source checkout:

```powershell
.\setup-client-windows.cmd --invite "C:\private\outlands.invite.json"
.\play-outlands-windows.cmd
```

Setup prompts for the owned game folder and a stable, unique player name. It
can download and open the official Plutonium updater; let its downloads finish
and close the launcher when setup asks. Without `--invite`, setup collects the
host address and join password privately in the terminal. A clone can live
outside the game directory.

Use `--game-dir PATH` and `--name "Unique Player"` to supply those choices.
`--dry-run` checks installation inputs without downloads, writes or launches;
`--check` checks a configured client. Run either setup helper with `--help` for
runtime and port overrides. The launch helpers join using the saved settings.

LAN identity depends on the player name. Setup saves it in the active runtime's
`storage/t6/outlands_player_name.txt`; changing it selects a different identity.
Each player must choose a different name and retain it across launches. Private
connection settings are saved separately in `outlands_join.cfg`. Setup does not
copy player saves, unlock content or change the stat source.

### Windows checks and direct joining

Follow the [Windows setup and validation guide](docs/WINDOWS.md) to verify the
release hash, select the exact game/runtime paths, preserve profile storage and
check the client before launching.

For a private host deliberately configured without a game password, the
current Windows source provides an explicit setup option:

```powershell
.\setup-client-windows.cmd --skip-updater --no-password --game-dir "D:\Games\Black Ops II" --plutonium-dir "D:\Tools\Plutonium" --name "Player One"
.\setup-client-windows.cmd --check
.\play-outlands-windows.cmd
```

Replace example paths and names with your own; setup collects the server
address privately. This mode clears any saved password before connecting and
cannot be combined with `--invite`. Protected invite behavior is preserved.
Older tagged releases can use the guide's direct LAN/console fallback.

The guide separates file checks, Tailscale access, joining, combat, after-action
results and restart retention. Private settings, profile data and connection
details stay outside the public source.

## Host a game

The [hosting guide](hosting/README.md) covers the Linux container host, isolated
smoke test, Tailscale registration, private invite export and Dockhand use.
Prepare your owned game files and an official Plutonium runtime, then run:

```sh
python3 hosting/setup_host.py --game-dir "/path/to/owned/BO2" --apply
cd hosting
./manage.sh smoke
./manage.sh up
./manage.sh export-invite --output /private/outlands.invite.json
```

Provide `--plutonium-dir "/path/to/Plutonium"` during host setup when the runtime
is outside the default isolated prefix. Share the invite privately with trusted
players who can reach the host over Tailscale. An invite contains a join
password; it does not grant Tailscale access.

The host publishes no Docker ports. Keep its full-game image private. The game
and Tailscale identity use separate persistent volumes; each player's earned
progress also depends on that client's saved profile.

## Bots and optional chat

The current configuration has 16 player slots and targets 16 total players
(8v8 in team modes), with native Hard difficulty. The original fill controller
waits for a human, then polls throughout the match to refill vacant connection
slots and adds native test clients at bounded intervals. Dead players still
occupy slots and respawn through native rules. After three consecutive failed
adds, the controller waits 10 seconds, then 20 and at most 30 seconds between
retry batches. It keeps polling every two seconds during cooldown and resets
the retry sequence when the human count or target changes. It removes only
verified bots when reducing the population. Native BO2 movement, combat and
difficulty logic remain in control; the mod does not disguise bots as human
connections or fabricate latency. Test mid-match replacement, team allocation
and recovery across the selected maps and modes using the validation guide.

Human team selection and auto-assign keep a group together by default, up to
one team's capacity (eight humans with the shipped settings). Two humans play
with six friendly bots against eight enemy bots. Later joins follow the current
human side, including after native side swaps; spectators can remain spectators.
The controller repairs uneven teams by removing only a bot from the oversized
side and refilling the smaller side. Convergence takes several polls during
joins, departures and native spawn initialization. With spectators, their slots
are reserved and the active population rounds down to an even total; an odd
configured target also rounds down. Free-for-all keeps native assignment.

`storage/t6/bots.txt` defines 48 fictional aliases with empty clan-tag fields, with
random native roster selection enabled. Matching chat personalities give each
alias a distinct voice. The identity module uses weighted levels from 1 to 55
and random prestiges from 0 to 10 by default. These cosmetic choices stay stable
across respawns and use bot-only native display calls. The optional rival ledger
adds persistent cosmetic careers; native bot weapon unlocks remain separate. Hosts should disclose the native AI opponents.

The optional [local chat bridge](ai/README.md) provides occasional banter,
public-chat replies and bounded two-to-four-line bot conversations through Ollama, with
canned fallbacks. Chat uses local RCON, exact bot identity checks and native
`sayall`; it does not control combat or alter stats. Enable it with the hosting
guide's `ai-up` command. Dockhand users can import the complete image-only
[`compose.dockhand.ai.yaml`](hosting/compose.dockhand.ai.yaml) stack.

Customize bots in `storage/t6/outlands_t6.cfg` and the alias roster:

| Setting | Purpose |
| --- | --- |
| `sv_maxclients` | Server capacity; currently 16 |
| `outlands_bot_fill` | Total humans plus bots, capped by server capacity; currently 16 |
| `outlands_coop_teams` | Keep human joins on the same side up to team capacity; default 1, team modes only |
| `outlands_balance_teams` | Repair team population using bot removal/refill; default 1, team modes only |
| `outlands_bot_difficulty` | 0 easy, 1 normal, 2 hard or 3 veteran; currently 2 (Hard) |
| `sv_randomizeBotNames` | Native random roster order; default 1 |
| `outlands_bot_levels` | Enable cosmetic bot levels; 0 keeps native display |
| `outlands_bot_careers` | Host-controlled optional fictional-bot ledger/restore switch |
| `outlands_bot_level_min` / `outlands_bot_level_max` | Inclusive weighted cosmetic level range, bounded to 1–55 |
| `outlands_bot_prestige_min` / `outlands_bot_prestige_max` | Cosmetic prestige range, default 0–10, bounded by the native icon table |
| `outlands_bot_profiles` | Enable connection class roles; default 1, enabling requires fresh map initialization |
| `outlands_bot_marksman_limit` | Maximum marksman roles, default 2; native emergency anti-air selection remains available |
| `outlands_bot_patrol_profiles` | Enable role-specific low-priority patrol timing; default 1 |
| `outlands_bot_air_reaction_ms` | Initial bot air-target reaction delay, default 2500 ms plus up to 50 percent jitter; bounded 0–8000 |
| `outlands_bot_air_response_chance` | Per-bot, per-air-target participation chance, default 80 percent; bounded 0–100 |

Keep stock `bot_friends` and `bot_enemies` at zero so only the Outlands controller
owns filling. The stock generator builds valid randomized unlocked weapons,
attachments, perks and equipment, and native class selection varies between
lives. The mod keeps the native validity rules. Humans use the normal
Create-a-Class menu and earned unlocks;
this source does not grant human equipment or levels.

Air-support response is slightly reduced: each native bot waits 2.5–3.75 seconds
before selecting a new UAV, counter-UAV, helicopter or plane threat, and has an
80 percent participation chance for that target. The decision stays stable for
that bot/target, including across respawns. Native threat filtering, launcher
availability, lock-on, damage and ground combat stay authoritative. Set the delay
to `0` and chance to `100` to restore stock target selection. This feature uses
the bot profile module; disabling profiles also bypasses its air-target gate.

## Custom AI development update

The working source adds five bot class roles: rushers favor SMGs/shotguns,
assault players favor assault rifles, objective players favor rifles/SMGs,
support players favor LMGs/rifles, and marksmen favor sniper rifles. The native
generator still determines valid weapons, attachments, perks and equipment;
profiles filter eligible class choices and fall back to initialized native
presets when needed. Native anti-air threat responses retain their class pool.
Roles last for a bot connection, with at most two marksmen by default.

Optional patrol profiles vary when the native brain considers a new patrol
point: rushers more frequently, support/marksmen less frequently. Native goal
selection, objectives, combat and stuck recovery remain in control. Patrol
cadence changes do not implement new pathfinding or persistent learning; evaluate
movement quality in gameplay separately from hook execution.

Chat schedules bounded numbered exchanges after accepted native deliveries.
Most conversations use two lines; occasional exchanges may use up to four.
Human public-chat replies take priority. All turns share global/per-bot limits
and stop when no humans remain. Verified contract completions create fresh chat
opportunities, and followups need not repeat tactical nouns.
Defaults are a 30-second opener interval, 12-second answer delay and at most
six requested lines per minute. General replies react to the preceding line and fresh own-scoreboard context;
public human messages take priority. `outlands_chat_dialogue 0` disables bot-to-bot
followups while keeping human replies available. See the [chat guide](ai/README.md)
for worker configuration and the [validation guide](docs/VALIDATION.md) for
repeatable checks. These development changes are not part of the frozen v0.1.2
release assets.

## Persistent AI rivals

The optional [rival system](docs/RIVALS.md) restores returning fictional bots with
persistent cosmetic careers, curated class roles and richer personality traits.
Native bot kills and positive score deltas earn separate bot career XP. This
never changes human progression or grants native equipment unlocks.

A private ledger survives worker/server restarts and deduplicates snapshots.
Chat can use each bot's own fresh scoreboard context, career and prior bot-to-bot
familiarity. Familiarity is recorded only after native delivery acknowledgement;
human identities and chat text are excluded from persistent storage. Native
pathfinding and combat remain authoritative. The AI hosting profile enables
careers independently of the chat switch, using a separate private volume.

## Map and mode rotation

The working source also includes optional [objective squads and team
contracts](docs/SQUADS-CONTRACTS.md). Optional [grounded task chat](ai/README.md#grounded-squad-objective-and-contract-chat)
lets bots discuss their current assignment and contract through short model
responses or matching fallbacks, with same-team replies and stale-context checks. Squads divide native bots between objective
assignments in five objective modes. Timed team contracts use actual native
kills or scoreboard deltas and grant match-local commendations. Both modules
have independent off switches; normal XP, unlocks and saved progression remain
native. Evaluate tactical quality and notifications later with human clients.

Use `python3 -B tools/content_inventory.py --game-dir /path/to/owned/BO2 --strict`
to check source rotation assets before hosting. The inventory distinguishes paid
DLC and separately discovered Zombies files without distributing either.

The configured rotation covers 15 multiplayer maps: 14 base maps plus Nuketown
2025. Clients need the owned files for each selected map; this does not include every separately released DLC map.

Eight modes use native bot support: Free-for-All (`dm`), Team Deathmatch (`tdm`),
Capture the Flag (`ctf`), Demolition (`dem`), Domination (`dom`), Hardpoint
(`koth`), Headquarters (`hq`) and Kill Confirmed (`conf`). Each has its own
gamesettings wrapper. Edit `sv_maprotation` in `storage/t6/outlands_t6.cfg` to
choose the order. Difficulty changes take effect through fresh map
initialization, including native combat tuning.

All eight wrappers double the baseline time and score targets:

| Mode | Time limit (minutes) | Score limit |
| --- | ---: | ---: |
| Team Deathmatch (`tdm`) | 20 | 200 |
| Free-for-All (`dm`) | 20 | 60 |
| Kill Confirmed (`conf`) | 20 | 150 |
| Capture the Flag (`ctf`) | 10 | 6 |
| Demolition (`dem`) | 5 | 4 |
| Domination (`dom`) | 10 | 200 |
| Headquarters (`hq`) | 30 | 500 |
| Hardpoint (`koth`) | 20 | 500 |

These limits follow each mode's native timer and round structure. CTF overtime
and Demolition bomb/round rules can end rounds independently of the score cap.
Test gameplay across every configured map and mode before extending the rotation.
These match settings are independent of the optional rival ledger and add no
persistent strategy learning.

The MW2 reference is
[iw4x-bot-warfare-extras](https://github.com/TheOutlandsDev/iw4x-bot-warfare-extras).
Full movement parity, learned tactical policies and native bot weapon careers
remain future work. This is an original native T6 integration, not an IW4
Bot Warfare adapter.

## CI and development releases

Version 0.1.2 is a development preview. The configured GitHub Actions pipeline
checks Linux setup/hosting/chat code, Bash syntax, and Windows PowerShell parsing
with synthetic client fixtures. Packaging waits for both platform jobs, then
produces an allowlisted source ZIP and `SHA256SUMS`. Version-matching `v*` tags
can publish a prerelease after the same checks pass. A manual release run on
`main` can instead run the checks, create the matching tag at the tested commit,
then publish using GitHub's built-in token. Dispatch on an existing matching tag
is also supported.

See the repository's Actions results for each revision and the
[release instructions](docs/RELEASING.md) for packaging. CI does not launch BO2;
follow the separate [gameplay validation guide](docs/VALIDATION.md).

## License and credits

Original Outlands source is covered by the [MIT license](LICENSE). BO2 assets,
Plutonium, Docker, Tailscale, Ollama and model weights retain their own licenses
and terms. No ownership of those components is claimed.

Built against [Plutonium's T6 scripting sources](https://github.com/plutoniummod/t6-scripts),
[mod loading](https://plutonium.pw/docs/modding/loading-mods/#t6),
[native bot/chat support](https://plutonium.pw/docs/changelog/), and the
[Tailscale sidecar pattern](https://tailscale.com/blog/docker-tailscale-guide).


### Outlands Operations development preview

The optional [Operations system](docs/OPERATIONS.md) adds persistent Assault,
Objective and Support milestones alongside normal BO2 progression. Complete the
first milestone in each track for Broken Signal / Field Regular. Use public chat
`!career` to view your private notification and `!track assault`, `!track objective`
or `!track support` to choose a persistent focus. Contract credit requires an
observed personal score contribution during the phase. Rewards are Outlands
commendations, not native equipment unlocks or combat bonuses.

The AI hosting overlays explicitly enable the separate milestone worker path.
Default/source installations leave it off. A private salted ledger retains numeric
progress without names or chat. Native GUID stability and actual human command
delivery require later Windows/Linux gameplay acceptance. Signal Four adds four
featured recurring bot characters; membership is not a forced roster or a new
combat controller. See the guide for identity limits, backups and backend checks.
