# Outlands full-screen interfaces

The in-game menu and browser portal share the charcoal and amber Outlands theme.
The native menu uses existing game actions. The browser portal supports mouse,
touch, responsive layouts and the browser Full Screen API when available.

## In-game menu

Send `!outlands` in game chat, then close chat and the console. Release held
buttons once. Aim/Fire changes pages, Use changes career focus, Jump opens Armory,
and Melee closes. The Armory uses Aim/Fire for rows, Tactical/Lethal for items,
Use to save, Jump to equip and Melee to close. See [commands](COMMANDS.md).

The full-screen background covers gameplay and the menu owns movement controls.
Players remain vulnerable; damage, death, respawn, team changes, timeouts,
disconnect and match transitions release its ownership. It does not change binds
or grant invulnerability. This is a native HUD controlled with game actions;
Windows/Linux real-player rendering and input still need acceptance testing.

## Browser portal over Tailscale

The optional portal shows aggregate live match counts and scores, current team
contracts, persistent fictional AI careers, and Career/Armory command guides.
It does not display human identities, personal XP, profiles, chat or saved
classes. Personal editing remains in-game, where native identity and unlocks
are verified. Browser writes and arbitrary file routes are refused.

From the source root, with the existing AI stack configured:

1. Add `PORTAL_TAILSCALE_IP=YOUR_SERVER_TAILSCALE_IPV4` to private `hosting/.env`.
   Optionally set `PORTAL_PORT=8085`.
2. Start the optional overlay using the same private stack files:

   ```sh
   cd hosting
   ./docker.sh compose -f compose.yaml -f compose.local.json -f compose.ai.yaml -f compose.portal.yaml build portal
   ./docker.sh compose -f compose.yaml -f compose.local.json -f compose.ai.yaml -f compose.portal.yaml up -d --no-build --no-deps portal-export portal
   ```

3. On a device connected to the same tailnet, open
   `http://YOUR_SERVER_TAILSCALE_IPV4:8085/`.
   The host's existing Tailscale ACLs must permit this TCP port. No host port is
   published, router forwarding is unnecessary, and no tailnet ACL is changed.
4. Keep the game join command `connect SERVER_ADDRESS:SERVER_PORT`. The portal
   displays the actual private endpoint from the host environment.

The browser container mounts only `/public:ro`. A separate offline exporter
reads the game console and fictional AI ledger read-only, projects an explicit
allowlist, and atomically writes `/public/status.json`. It cannot issue RCON or
model requests and has no network. Both run as UID 10001 with read-only roots,
no Linux capabilities and bounded memory/CPU. The web listener refuses wildcard
or LAN binds; only explicit Tailscale IPv4 or loopback is accepted. HTTP travels
inside the existing encrypted tailnet; application-level HTTPS is not provided.
Only trusted tailnet members with network access can view this shared dashboard.

The game emits anonymous aggregate snapshots every five seconds. The exporter
starts at the console's current EOF, preventing stale startup replay. After 20
seconds without a fresh sample the UI clears live scores and contract progress.
Missing files, oversized inputs and malformed records do not become live data.
AI career cards are historical fictional records, not the current roster.

For HTTP pages without clipboard permission, Copy selects the visible command
and prompts the player to use the browser's Copy action. Full Screen gracefully
falls back to the browser's own controls on unsupported mobile browsers.

## Validation and rollback

`python -B -m unittest discover -s tests -p test_portal.py -v` exercises strict
native record parsing, privacy projection, log rotation, startup replay, stale
exports, route restrictions and read-only HTTP behavior. The full source runner
includes these checks on Linux. Native backend cases validate real emitted
snapshots; browser QA separately checks navigation, responsive layout and live
updates. Neither proves real game-client menu input or a second device's access.

Stop only the optional services to roll back the browser:

```sh
cd hosting
./docker.sh compose -f compose.yaml -f compose.local.json -f compose.ai.yaml -f compose.portal.yaml stop portal portal-export
```

Their `portal-public` volume contains only the projected snapshot. It is safe to
rebuild; never remove the game's `t6-state`, `rival-state` or Tailscale volumes.
