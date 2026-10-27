# Joining and Outlands commands

Launch BO2 Multiplayer in LAN mode with the same stable player name and active
Plutonium profile used for earned progression. With Tailscale connected, open the
game console and enter the host's privately supplied direct connection command:

```text
connect SERVER_ADDRESS:SERVER_PORT
```

This is the canonical join method. The address and port identify the server;
Outlands menu commands do not select a different server. This public repository
contains placeholders, not a deployment's private address. If the host requires
a password, set its privately supplied value locally before connecting.

`exec outlands_join.cfg` is an optional local configuration shortcut used by the
existing launch helpers. It depends on the file being installed in the runtime
and search path the game actually uses. File checks alone do not prove it runs.
Use direct `connect` when joining or troubleshooting; no join CFG is needed.

## Chat and console are different input fields

After connecting, choose a team and class and spawn. Type the left-hand command
in **in-game text chat**. In the **game console**, use `say` before that command.
Do not type a bare `!outlands` into the console.

| Purpose | In-game text chat | Game console |
| --- | --- | --- |
| Open/close Career HUD | `!outlands` | `say !outlands` |
| Help | `!outlands help` | `say !outlands help` |
| Career page | `!outlands career` | `say !outlands career` |
| Team contracts | `!outlands contracts` | `say !outlands contracts` |
| Other HUD page | `!outlands next` | `say !outlands next` |
| Cycle career focus | `!outlands focus` | `say !outlands focus` |
| Close overlays | `!outlands close` | `say !outlands close` |
| Career notification | `!career` | `say !career` |
| Select career focus | `!track assault`, `!track objective`, `!track support` | `say !track assault`, `say !track objective`, `say !track support` |
| Open/close Armory | `!outlands armory` | `say !outlands armory` |
| Select Armory row | `!outlands up`, `!outlands down` | `say !outlands up`, `say !outlands down` |
| Change Armory item | `!outlands left`, `!outlands right` | `say !outlands left`, `say !outlands right` |
| Save draft for next respawn | `!outlands save` | `say !outlands save` |
| Queue saved class | `!outlands equip` | `say !outlands equip` |
| Return to stock class | `!outlands stock` | `say !outlands stock` |

Commands accept letter case and repeated whitespace. Prefix a chat command with
`/` to request Plutonium's hidden-chat form, for example `/!outlands armory` or
console `say /!outlands armory`. Local menu commands accept all/team and hidden
chat because their output is private to the sender. Missing privacy flags never
permit forwarding human text to the chat/model worker. Commands are excluded
from bot reply requests; normal public-chat replies retain their privacy checks.

The host must enable each optional feature. `!outlands help` remains available
when the HUD is disabled. Recognized commands that cannot proceed give a private
disabled/loading/busy notice. Operations and Armory still require a real human
session, current server observations and their own persistence acknowledgements.
An accepted input or open overlay does not mean a class was saved or equipped.

The optional `outlands_ui_keys.cfg` and `outlands_armory_keys.cfg` now bind hidden
`say` commands. They are never executed automatically and replace the keys
listed inside those files. Refresh the optional CFG in your actual client runtime
before opting in again. Existing bare console aliases remain for compatibility;
prefer chat or explicit `say` commands when diagnosing client command forwarding.
Server-side command repairs do not require players to reinstall game files.

The matching [Tailscale browser GUI](PORTAL.md) provides live match, contracts
and fictional rival views with normal mouse/touch navigation.

## Navigate the full-screen in-game menu

After entering the opening command, close the chat box or console and keep BO2
focused. These are native in-game HUD menus, not a separate desktop window and
not a clickable mouse-cursor interface. The open menu reads your existing game
actions on keyboard/mouse or controller; it does not install or replace bindings.

| Existing game action | Career/Contracts | Armory |
| --- | --- | --- |
| Aim down sights | Change page | Previous row |
| Fire | Change page | Next row |
| Use / interact | Cycle career focus | Save draft for next respawn |
| Jump | Open Armory | Queue saved class for next respawn |
| Tactical grenade | Change page | Previous item |
| Lethal grenade | Change page | Next item |
| Melee | Close | Close |

Release held buttons after opening or switching menus. Only navigation repeats
when held; Save/Equip/Close require a new press. The footer shows action prompts.
`!outlands close` in chat or console `say !outlands close` remains a fallback.
The optional F-key CFGs remain available but are not required for navigation.

Opening captures gameplay controls while your character remains vulnerable in
the live match. Melee/command close, damage, death, spawn, team changes, timeout
and feature disable clean up the overlay and release its ownership token.
Native death, prematch, migration and round-end freeze rules retain authority;
menu cleanup must not unfreeze a native round transition. Open only when alive
and in active play. There is no global pause or invulnerability.

## Backend verification and remaining client test

T6 native `sayall` and `sayteam` events can contain two leading transport control
bytes. Removing only one leaves an invisible byte before `!` and prevents exact
command matching. The shared bounded normalizer strips up to two non-printable
leading bytes, preserves printable junk, handles the optional hidden slash and
normalizes case/spacing. Handlers never evaluate command text as code.

The disposable `--ui` assay emits every one of the nineteen supported commands
through the engine's real all/team chat methods, including hidden-form and
mixed-case input. It calls production parsers, checks command/model exclusion,
reproduces the former one-byte parser's failure, tests privacy-flag refusal and
verifies the native bot cannot pass human dispatch gates. The assessor requires
exact ingress evidence in addition to HUD allocation and cleanup evidence.
A separate native control fixture reads all seven overridden game actions while
controls are frozen, checks both menu mappings, verifies focus ownership and
idempotent cleanup, and tests release-to-arm, repeat timing and one-shot saves.
The sender remains a native bot, not an impersonated human client.

```sh
python -B hosting/backend_verify.py --run --case mp_raid:dom --seconds 60 \
  --image outlands-t6:local --worker-image outlands-bo2-chat:local \
  --careers --squads --contracts --chat-context --expansion --ui --armory-editor
```

Real Windows/Linux keyboard input, bare-console alias forwarding, client HUD
rendering, human earned-unlock observations and saved progression remain separate
client checks. Join directly, try chat `!outlands help`, then console
`say !outlands contracts`. Exercise Armory save/next-respawn/equip, reconnect and
normal progression only after the corresponding acknowledgements. Keep raw logs,
profiles and results containing player information private.

Fixed `OUTLANDS_COMMAND_V1` diagnostics contain only the handler, allowlisted
action and accepted/rejected result. They do not contain names, GUIDs, message
text or connection details. These local diagnostics help distinguish delivery
from feature readiness; never publish raw server/client logs.
