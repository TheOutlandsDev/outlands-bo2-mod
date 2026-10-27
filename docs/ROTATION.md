# Installed maps, weighted rotation and idle matches

The map catalog includes all 31 BO2 multiplayer maps: fourteen base maps,
Nuketown 2025, and the sixteen Revolution, Uprising, Vengeance and Apocalypse
maps. The mod distributes no game files. Both host and connecting clients need
their own installed content. Zombies maps belong to a separate game/server and
are not multiplayer rotation entries.

The Linux container's rotation director filters `outlands_rotation.json` against
nonempty main map fastfiles in the private game image. Missing, empty, linked
or zero-weight maps are excluded. Presence is only an eligibility check, not
proof of supporting assets, ownership or runtime loadability. After installing
owned DLC into the game folder, rebuild the private game image and restart the
server. Files added outside the image do not update an already-built image.
Verify a matching client installation before putting new DLC into use.

## Weights and repeat protection

`storage/t6/outlands_rotation.json` contains the public default catalog. All maps
start at weight 1, giving every eligible map one ticket per shuffled deck.
Map and mode weights accept 0-8; zero disables an entry. Higher values add
more tickets, increasing long-run frequency. Mode selection has its own deck;
a map is not permanently tied to one mode. Native gamesettings wrappers reset
the selected mode's normal doubled limits.

The director avoids the last five maps and last two modes when eligible tickets
permit it. If a deck's last tickets are all blocked, it relaxes the oldest recent
exclusion first. No immediate map repeat is allowed when two or more maps are
enabled. That protection takes priority over exact weights in a constrained
small pool. Equal-weight maps all appear once before the next complete deck;
no map can be left out by repeated independent random rolls.

The private persistent file `/data/private/rotation.json` stores only map/mode
history, remaining tickets and the pending next selection. Starting a map consumes
its ticket; preparing a map does not. A process restart keeps the pending choice
and history, so ordinary restarts do not reset the rotation to Raid. Halftime or
reload observations of the same map/mode do not spend another ticket.

Host startup copies the default catalog only when a private catalog is absent.
An operator can edit `/data/plutonium/storage/t6/outlands_rotation.json` inside
the private volume; later image updates preserve these weights. Keep private
state/config backups outside shared source. An invalid catalog/state refuses the
director and retains the existing static CFG fallback rather than overwriting
the state. Restore the backup or correct the configuration before restarting.

The native handoff validates a map-scoped nonce and the host's installed-map and
mode allowlists, writes `sv_maprotationcurrent` and emits a readback ACK. Normal
match-end `map_rotate` still owns the transition. No human, model or chat string
chooses a map command. The director needs neither Ollama nor the chat worker.
Set `outlands_rotation 0` in the private server CFG to use its static rotation.

## Bot matches and chat without humans

`outlands_bot_idle_fill 16` keeps native AI matches running on an empty server.
It is capped by `outlands_bot_fill` and `sv_maxclients`; joining humans replace
bots through the existing native policy. Team balance and cooperative human-team
rules still apply. Set idle fill to zero to drain bots when nobody is connected.
Human XP, unlocks, saves and the separate human Operations ledger are unchanged
by an all-bot match. Fictional bot careers can continue to progress.

When the optional chat worker is enabled, `outlands_chat_without_humans 1` allows
normal bounded bot-to-bot conversations during these matches. Set it to zero to
require a human audience. The feature does not invent human messages or bypass
speaker/session, context freshness, numbered-turn or rate-limit checks. All turns
share the existing six-per-minute maximum, global and per-bot cooldowns. Public
human replies still take priority. Ollama failures can use contextual fallback
lines through the same native delivery path. Overall `outlands_chat_enabled 0`
still stops speech, and `outlands_chat_dialogue 0` stops bot followups.

## Backend verification

```sh
python -B -m unittest discover -s tests -p test_rotation.py -v
python -B tools/validate_system.py
python -B hosting/rotation_verify.py --run --steps 15 \
  --image outlands-t6:rotation-chat-dev --report-dir runtime/rotation-check
python -B hosting/backend_verify.py --run --case mp_raid:dom --seconds 120 \
  --image outlands-t6:rotation-chat-dev --worker-image outlands-bo2-chat:local \
  --ambient-chat --squads --contracts --report-dir runtime/idle-chat-check
```

Choose a fresh private report directory. The rotation assay runs offline with
disposable state, equal map weights and a short TDM-only test override. It waits
for a real normal match end, follows native ACKs through subsequent forced native
`map_rotate` transitions, then restarts the process and checks saved history.
Set steps to the number of installed eligible maps; it cannot test absent DLC.
The production mode weights and doubled limits are not changed by these fixtures.

The ambient chat assay uses production idle fill, a real worker in fallback mode,
native requests and matching native speech ACKs. It does not manually spawn bots
or substitute a direct `sayall` call for transport. Rendering, chat readability,
human joins and the subjective quality of a conversation require real clients.
The older `--chat-context` assay explicitly disables no-audience speech while
testing that optional guard; it cannot combine with `--ambient-chat`.
