# Host The Outlands BO2 Mod

The primary host is a Linux Docker Compose stack running a Plutonium T6
**LAN-mode** dedicated server through Wine and a headless display. Clients use
LAN mode and connect over Tailscale. This path needs no Plutonium account sign-in
or server key; each installation still supplies its own legitimate BO2 files.

See the [implementation methodology](../docs/METHODOLOGY.md) for the component
boundaries and the [validation guide](../docs/VALIDATION.md) for isolated startup,
client joining, progression and gameplay checks.

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
Source rotation/core content preflight runs before staging or downloads. For an
existing host with a customized private rotation, run the inventory separately
with `--config /private/outlands_t6.cfg --strict`; setup does not inspect that
private CFG. Supply missing owned assets or remove unavailable maps from the
selected rotation.

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
| `outlands-t6_rival-state` | Optional private fictional-bot career ledger; include in backups |

The join password is generated in
`/data/plutonium/storage/t6/outlands_t6.cfg`. Prefer private invite export over
copying it manually. Existing private CFGs survive image updates; source CFG
changes need deliberate application to an existing host. Preserve the join
password when changing gameplay settings.

### Migrate an existing host to the current defaults

The entrypoint preserves an existing main `outlands_t6.cfg`; rebuilding an image
does not replace its gameplay settings. Back up that private file, then merge
these assignments into `/data/plutonium/storage/t6/outlands_t6.cfg`:

```cfg
sv_maxclients 16
bot_friends 0
bot_enemies 0
bot_difficulty 2
set outlands_bot_fill 16
set outlands_bot_difficulty 2
```

Replace its `sv_maprotation` assignment with the current source assignment in
[`storage/t6/outlands_t6.cfg`](../storage/t6/outlands_t6.cfg) to enable all 15 maps
and eight supported modes. Preserve the existing join password, local RCON
settings and any private access-policy `exec` lines. Rebuild and redeploy the
game image through `./manage.sh up` or `./manage.sh ai-up`, as appropriate.
Startup refreshes the shipped scripts and mode wrappers, including the doubled
limits; the main CFG still needs the explicit merge above. Native difficulty
tuning takes effect during fresh map initialization.

Client rank and weapon data also depend on each client's profile. Keep stable,
unique LAN player names. This host does not set `use_localStats`, copy saves or
unlock content; a server-volume backup does not replace client-profile backups.

## Native bots

The current defaults are native Hard difficulty (`2`), 16 player slots and a
16-player fill target: 8v8 in team modes, or individual players in Free-for-All.
After a human joins, one controller checks the population every two seconds and
adds at most one native bot per check. Three consecutive unsuccessful additions
start a 10-second cooldown; repeated failures increase it to 20, then 30 seconds,
capped at 30. The controller keeps polling during cooldown and retries rather
than stopping permanently. Human-count or target changes reset that cooldown.

Dead players still occupy connection slots and respawn through native rules.
The controller removes only verified native test clients when reducing the
population. Keep `bot_friends 0` and `bot_enemies 0`; configure
`outlands_bot_fill` and `outlands_bot_difficulty` in the persistent host CFG. The
source also gives clients a 600-second initial team/class selection window.

`bots.txt` supplies fictional aliases with empty clan tags. Matching chat
personalities affect conversational voice only. The bot-only identity module
assigns weighted cosmetic levels from 1 to 55 and prestiges from 0 to 10 by
default, bounded by native display limits. These remain stable across respawns.
Human progression and native loadout eligibility stay under the game.

Five connection roles filter valid native class pools: rusher, assault,
objective, support and marksman. Native presets provide a fallback, and native
anti-air class selection remains available. Optional role-specific patrol timing
changes low-priority patrol cadence while preserving native objective, combat,
pathfinding and recovery behavior. Configure the profile switches and ranges in
`storage/t6/outlands_t6.cfg`; enabling hooks requires fresh map initialization.

The optional [objective squads and contracts](../docs/SQUADS-CONTRACTS.md) use
independent `outlands_squads` and `outlands_contracts` switches. Source defaults
enable both; updates introduce these defaults only when the host has no existing
value. Configure bot role caps and contract duration/scale in the private host
CFG. The first contract rewards are match-local commendations and team notices,
with no native XP, unlock or saved-profile writes. Neither module needs Ollama
or a writable persistent ledger. Test in disposable state before promotion;
preserve full game storage, rival-state and a rollback image when updating.

## Map and mode rotation

The source rotation uses 15 maps: the 14 base multiplayer maps plus Nuketown
2025. Each client needs the owned assets for the selected map. Eight modes have
native bot support: Free-for-All (`dm`), Team Deathmatch (`tdm`), Capture the Flag
(`ctf`), Demolition (`dem`), Domination (`dom`), Hardpoint (`koth`), Headquarters
(`hq`) and Kill Confirmed (`conf`). Other DLC maps are not included in this
configured baseline.

Each `gamesettings/outlands_*.cfg` wrapper resets native defaults, loads its
matching mode and applies time/score limits doubled from the earlier Outlands
baseline. Native round, overtime and objective rules still apply; doubling the
timer does not guarantee twice the match duration. See the
[current limits](../README.md#map-and-mode-rotation) and
[validation boundaries](../docs/VALIDATION.md) before treating every mode or
failure-recovery path as playtested.

## Optional Ollama chat

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
startup ignores that key path. Validate online-mode compatibility separately
from the LAN deployment described here.

References: [Plutonium server setup](https://plutonium.pw/docs/server/t6/setting-up-a-server/),
[LAN dedicated hosting](https://forum.plutonium.pw/topic/38120/t6-lan-server-not-authenticated-to-plutonium),
[Tailscale containers](https://tailscale.com/docs/features/containers/docker/docker-params),
[Docker port publishing](https://docs.docker.com/engine/network/port-publishing/).

## Persistent rivals and backend tests

The AI stack enables independent chat and career worker features, with server
state read-only for the worker and a separate private career volume. See the
[rival guide](../docs/RIVALS.md) for career semantics, backup boundaries, owned
content inventory and the network-isolated all-bot verification runner. The
runner installs its probe only into disposable state; the live image payload
contains no backend verification GSC.
