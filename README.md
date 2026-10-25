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
with a human playing. The player also confirmed the scoreboard's blank clan
tags and different cosmetic levels look correct. Windows joining still needs
acceptance. See
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

```bat
setup-client-windows.cmd --invite "C:\private\outlands.invite.json"
play-outlands-windows.cmd
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

The original fill controller waits for a human, targets 12 total players and
adds native test clients at bounded intervals. It removes only verified bots
when reducing the population. Native BO2 movement, combat and difficulty logic
remain in control; the mod does not disguise bots as human connections or
fabricate latency.

`storage/t6/bots.txt` defines fictional aliases with empty clan-tag fields, with
random native roster selection enabled. Custom alias assignment has passed a
runtime check. Matching chat personalities give each alias a distinct voice.
Optional random levels from 1 to 55 are cosmetic bot presentation, not earned
bot careers or weapon unlocks. The native calls passed an isolated check, and
the player confirmed visible levels and removal of the default `BOT` clan tags
on the scoreboard. The host continues to disclose native AI opponents. The optional
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
| `outlands_bot_fill` | Total humans plus bots, capped by server capacity |
| `outlands_bot_difficulty` | 0 easy, 1 normal, 2 hard or 3 veteran |
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

The MW2 reference is
[iw4x-bot-warfare-extras](https://github.com/TheOutlandsDev/iw4x-bot-warfare-extras).
Full movement/personality parity, learning heuristics and individual bot careers
remain future work. This is an original native T6 integration, not an IW4
Bot Warfare adapter.

## CI and development releases

Version 0.1.1 is a development preview. The configured GitHub Actions pipeline
checks Linux setup/hosting/chat code, Bash syntax, and Windows PowerShell parsing
with synthetic client fixtures. Packaging waits for both platform jobs, then
produces an allowlisted source ZIP and `SHA256SUMS`. Version-matching `v*` tags
can publish a prerelease after the same checks pass.

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
