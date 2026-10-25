# Host The Outlands BO2 Mod

The primary host is a Linux Docker Compose stack running a Plutonium T6
**LAN-mode** dedicated server through Wine and a headless display. Clients use
LAN mode and connect over Tailscale. This path needs no Plutonium account sign-in
or server key; each installation still supplies its own legitimate BO2 files.

The baseline has passed Linux joining, native bot combat and earned rank/weapon
progression retained after a full client/server restart. Native alias assignment,
chat GSC compilation and local RCON transport have passed isolated checks, as
have varied native weapons/classes and cosmetic-level API calls. The complete
Ollama-to-native-speech path has also passed during live human play. The player
confirmed blank clan tags and different cosmetic levels on the scoreboard.
Windows joining remains pending.
See [validation status](../docs/VALIDATION.md).

## Prepare the host

Install Docker Engine with Compose/Buildx support, Python 3 and a working
`/dev/net/tun`. Use a current Compose release supporting additional build
contexts and the override tags in `compose.smoke.yaml`. Allow sufficient disk
space for owned game assets, an approximately 15.5 GB private game image, build
cache and optional model weights.

Obtain the official Plutonium runtime through its
[updater](https://plutonium.pw/docs/install/). You can use an existing runtime or
initialize the source checkout's isolated client runtime. Host preparation
checks the runtime against official updater metadata; it downloads metadata,
not BO2 assets.

From the source checkout:

```sh
python3 hosting/setup_host.py --game-dir "/path/to/owned/BO2" --apply
```

Add `--plutonium-dir "/path/to/Plutonium"` for an existing runtime outside the
default prefix. Without `--apply`, preparation validates existing inputs without
writes, downloads or containers. `--apply` stages the verified runtime in
`hosting/package/` and saves private game build paths in
`hosting/compose.local.json`. The source checkout can be outside the game folder.
It also enables the hosting shell helpers, so the `./manage.sh` commands below
work after setup even when a downloaded source archive lacks executable bits.

Keep those generated files private. The Docker image contains BO2 game assets
and must not be uploaded with the public source.

## Test and start

From `hosting/`:

```sh
./manage.sh check
./manage.sh smoke
./manage.sh up
```

`check` prepares/verifies the private vendor package and Compose configuration;
it starts no containers. `smoke` builds the image and starts a separate LAN
server with network mode `none`, a separate data volume and no host ports. It
waits for script initialization and the game socket, writes private diagnostic
logs, and stops the smoke server. Startup health alone does not verify gameplay.

`up` builds the game image and starts its separate Tailscale sidecar. Complete
the Tailscale login URL to authorize that hosting identity, then let the helper
start the game. It prints the private hosting address; the default game UDP port
is 4977. Every client needs Tailscale access to that node.

```sh
./manage.sh export-invite --output /private/outlands.invite.json
```

This writes a private schema-version-1 invite containing the current hosting
address, game port and join password. The exporter refuses to overwrite an
existing file. Share it privately with trusted players; never commit it. Clients
import it with `bash setup-client-linux.sh --invite PATH` or
`setup-client-windows.cmd --invite PATH`. An invite does not authorize a client
on your tailnet.

## Network and persistent state

No service publishes a host port or uses host networking. The game shares the
Tailscale sidecar's network namespace, containing both the game socket and its
secondary DW socket. The sidecar has its own Tailscale identity and state; it
does not mount the host's Tailscale configuration. The game runs as UID 10001
with capabilities dropped.

The project name is `outlands-t6`. Its volumes are:

| Volume | Contents |
| --- | --- |
| `outlands-t6_t6-state` | Server Wine prefix, Plutonium storage, private host CFG and optional local chat credential |
| `outlands-t6_tailscale-state` | Hosting node's Tailscale identity |
| `outlands-t6_ollama-models` | Optional separately downloaded model weights |

The join password is generated in
`/data/plutonium/storage/t6/outlands_t6.cfg`. Prefer private invite export over
copying it manually. Existing private CFGs survive image updates; source CFG
changes need deliberate application to an existing host. Preserve the join
password when changing gameplay settings.

Client rank and weapon data also depend on each client's profile. Keep stable,
unique LAN player names. This host does not set `use_localStats`, copy saves or
unlock content; a server-volume backup does not replace client-profile backups.

## Native bots and optional Ollama chat

The controller targets 12 total players after a human joins, with one native
addition per two seconds and a limit of three failed additions. It removes only
verified native test clients. Keep `bot_friends 0` and `bot_enemies 0`; configure
`outlands_bot_fill` and `outlands_bot_difficulty` in the persistent host CFG.
The source also gives clients a 600-second initial team/class selection window.

The new `bots.txt` roster requests aliases with empty clan tags. Native custom
alias assignment passed a runtime check, and the player confirmed the default
`BOT` clan tags are gone on the scoreboard. Chat personality metadata changes
conversational voice only.
Optional cosmetic bot levels are bounded by `outlands_bot_level_min` and
`outlands_bot_level_max`, from 1 to 55. Native combat/loadout eligibility remains
unchanged, and no human XP/unlock/stat writes are added. An isolated four-bot
probe observed varied shotgun, LMG, sniper and SMG classes, attachments and
secondaries. Cosmetic native `setrank` calls completed without errors, and the
player confirmed the different rendered levels look correct.

For the optional contained chat setup:

```sh
./manage.sh ai-up
```

This includes `compose.ai.yaml`, builds the chat and Ollama services, enables the
matching game-side chat gate, downloads the base `qwen3:1.7b` model and creates
`outlands-bo2-chat` from `ai/Modelfile`. Model weights are obtained separately
under their own terms. The recipe supplies a prompt and runtime settings; it is
not a newly trained model. To refresh the model on an already-running AI stack:

```sh
./manage.sh ai-model
```

Ollama has no published port. The chat worker reads server state through a
read-only volume and shares the private game network namespace. RCON is enabled
only for this local worker, with a generated private credential and a loopback
source whitelist. The only submitted command updates a bounded response dvar;
GSC verifies the pending request, native bot, slot/name and expiry before speech.
Team/hidden chat is excluded. Live banter and public-chat events reached the
worker; generated replies passed through local RCON, GSC identity checks and
native `sayall`, with multiple successful speech acknowledgements. A cold-model
request used the bounded fallback before Ollama generations succeeded. See
[the chat guide](../ai/README.md) for resource limits, privacy boundaries,
canned fallbacks and protocol details.

## Operations and Dockhand

```sh
./manage.sh status
./manage.sh logs
./manage.sh down
```

`down` preserves volumes. Avoid `docker compose down -v` unless you intend to
discard saved host data and the Tailscale identity. Back up required volumes and
client profiles privately before moving or replacing a host.

`compose.yaml` builds locally. For Dockhand, choose one complete image-only
definition after building locally:

- [`compose.dockhand.yaml`](compose.dockhand.yaml): game and Tailscale, without
  the optional chat services.
- [`compose.dockhand.ai.yaml`](compose.dockhand.ai.yaml): all four services
  (game, Tailscale, Ollama and chat worker). Run `./manage.sh ai-up` first to
  build its images and initialize the model, then import this definition.

Neither definition needs a build context or host game-folder mount.
Retain the `outlands-t6` project name and LAN mode so both methods use the same
volumes. Source/vendor changes require a local rebuild before redeployment.
The base Dockhand definition alone does not enable chat; the AI definition is
a complete stack rather than an override to paste into the base file.

Copy `.env.example` to `.env` for supported host/port overrides. The defaults use
LAN mode and a pinned Tailscale image. Keep actual addresses, credentials,
private build paths and generated logs out of the public repository.

## Optional authenticated online mode

Online hosting is a separate choice. Obtain a dedicated key through
[Plutonium's server-key page](https://platform.plutonium.pw/serverkeys), complete
any account/ownership verification it requests, and run `./manage.sh key` to
enter the key privately. It is stored in the server data volume at
`/data/private/plutonium_server_key`, outside the image and source.

Set `T6_MODE=online` in the local `.env` and in any separately saved Dockhand
configuration, then redeploy with matching authenticated online clients. LAN
startup ignores that key path. The verified Linux baseline described here is
LAN mode; online-mode compatibility is not asserted.

References: [Plutonium server setup](https://plutonium.pw/docs/server/t6/setting-up-a-server/),
[LAN dedicated hosting](https://forum.plutonium.pw/topic/38120/t6-lan-server-not-authenticated-to-plutonium),
[Tailscale containers](https://tailscale.com/docs/features/containers/docker/docker-params),
[Docker port publishing](https://docs.docker.com/engine/network/port-publishing/).
