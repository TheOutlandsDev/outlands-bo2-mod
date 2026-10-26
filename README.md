# The Outlands BO2 Mod

Private Black Ops II multiplayer over Tailscale, with native AI opponents and
normal earned rank and weapon progression. Linux and Windows clients use
Plutonium LAN mode and connect directly to the private host. No Plutonium
server key is needed for this LAN path.

The playable baseline has been verified on Linux: one human plus 11 native
bots, combat, after-action rank XP and weapon progress, and retention after a
full client/server restart. Isolated checks also verified custom aliases,
varied native weapons/classes and cosmetic-level API calls. The complete live
Ollama request, generation, local RCON and native bot speech path has now passed
during live play. Scoreboard checks confirmed blank clan tags and distinct
cosmetic levels. Windows joining, spawning
and bot combat have since been confirmed; Windows quit/relaunch progression
retention remains pending. See
[validation status](docs/VALIDATION.md).

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
connections or fabricate latency. Live checks on Raid / Domination verified
eight assigned players per team, a mid-match 16 → 15 → 16 vacancy/refill, and
Windows staying connected. Full rotation and prolonged failed-add recovery
acceptance remain pending.

`storage/t6/bots.txt` defines fictional aliases with empty clan-tag fields, with
random native roster selection enabled. Custom alias assignment has passed a
runtime check. Matching chat personalities give each alias a distinct voice.
Optional random levels from 1 to 55 are cosmetic bot presentation, not earned
bot careers or weapon unlocks. The native calls passed an isolated check, and
scoreboard checks confirmed visible levels and removal of the default `BOT`
clan tags. The host continues to disclose native AI opponents. The optional
[local chat bridge](ai/README.md)
provides occasional banter and public-chat replies through Ollama, with canned
fallbacks. Live logs verified generated replies passing through local RCON,
GSC identity validation and native `sayall`, with multiple successful delivery
acknowledgements during a human match. Chat does not control combat or alter
stats. Enable it with the hosting guide's `ai-up` command. Dockhand users can
then import the complete image-only
[`compose.dockhand.ai.yaml`](hosting/compose.dockhand.ai.yaml) stack.

Customize bots in `storage/t6/outlands_t6.cfg` and the alias roster:

| Setting | Purpose |
| --- | --- |
| `sv_maxclients` | Server capacity; currently 16 |
| `outlands_bot_fill` | Total humans plus bots, capped by server capacity; currently 16 |
| `outlands_bot_difficulty` | 0 easy, 1 normal, 2 hard or 3 veteran; currently 2 (Hard) |
| `sv_randomizeBotNames` | Native random roster order; default 1 |
| `outlands_bot_levels` | Enable cosmetic bot levels; 0 keeps native display |
| `outlands_bot_level_min` / `outlands_bot_level_max` | Inclusive cosmetic level range, bounded to 1–55 |

Keep stock `bot_friends` and `bot_enemies` at zero so only the Outlands controller
owns filling. The stock generator builds valid randomized unlocked weapons,
attachments, perks and equipment, and native class selection varies between
lives. An isolated four-bot probe observed distinct shotgun, LMG, sniper and SMG
loadouts with different attachments and secondaries. The mod keeps the native
validity rules. Humans use the normal Create-a-Class menu and earned unlocks;
this source does not grant human equipment or levels.

## Map and mode rotation

The configured rotation now covers the 15 multiplayer maps installed for the
host baseline: 14 base maps plus Nuketown 2025. Clients need the owned files for
each selected map; this does not include every separately released DLC map.

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
The Hard/16-player/expanded-rotation update, doubled limits and revised filling
are configured and loaded. Raid / Domination fill and team allocation passed;
full gameplay acceptance across the rotation remains pending. They add no
persistent learning or bot careers.

The MW2 reference is
[iw4x-bot-warfare-extras](https://github.com/TheOutlandsDev/iw4x-bot-warfare-extras).
Full movement/personality parity, learning heuristics and individual bot careers
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

This describes the configured pipeline, not a report that its checks have run.
See the repository's Actions results and [release instructions](docs/RELEASING.md).
CI does not launch BO2 or prove Windows gameplay; the existing
[gameplay acceptance record](docs/VALIDATION.md) remains separate.

## License and credits

Original Outlands source is covered by the [MIT license](LICENSE). BO2 assets,
Plutonium, Docker, Tailscale, Ollama and model weights retain their own licenses
and terms. No ownership of those components is claimed.

Built against [Plutonium's T6 scripting sources](https://github.com/plutoniummod/t6-scripts),
[mod loading](https://plutonium.pw/docs/modding/loading-mods/#t6),
[native bot/chat support](https://plutonium.pw/docs/changelog/), and the
[Tailscale sidecar pattern](https://tailscale.com/blog/docker-tailscale-guide).
