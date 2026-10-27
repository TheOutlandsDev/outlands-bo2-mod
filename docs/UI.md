# Outlands native HUD preview

The first functional frontend is a server-rendered Career and Contracts HUD
using original charcoal panels, amber selection rails and BO2's native HUD
fonts. It reads real Operations responses and the current team's contract.
The browser design remains a visual target, not a screenshot of this engine
implementation. The separate [native Armory preview](ARMORY.md) supplies a base-
class editor. Rivals, mouse hit targets and native LUI menus remain future work.

## Enable and open

The prototype is off by default. After isolated checks, set `outlands_ui 1` in
the private host configuration. Set it back to `0` to close every open overlay
within one polling interval. Enable Operations and its worker separately for
careers, and contracts for team progress. The HUD does not enable either feature
or contact Ollama.

Use public chat `!outlands`, `!outlands career`, `!outlands contracts`,
`!outlands focus` or `!outlands close`. Hidden `/!outlands` commands are also
accepted. Console commands are `outlands` (toggle), `outlands_next` (other page),
`outlands_focus` (cycle career focus) and `outlands_close`.

Optional `exec outlands_ui_keys.cfg` binds F6-F9 to those four commands.
This overwrites existing F6-F9 bindings; record yours before opting in.
Installers copy the file but never execute it or rebind controls automatically.
Console/chat commands work without those bindings. Controller mapping and all
actual client input still require acceptance; there is no built-in mouse menu.

The overlay does not pause a multiplayer match or freeze controls. Open it
when safe. It closes after forty seconds without menu input, on death, spawn,
disconnect, map end or feature disable. Each open owns a bounded set of native
client HUD objects. Opening does not create another controller/listener.

## Data and mutation boundaries

Career totals come from an acknowledged, current human Operations session.
Unrestored, stale, future-dated and malformed data display loading/unavailable
states with hidden values, never zero earned progress. Numeric HUD values use
native `setvalue`; static labels change only when necessary, avoiding a new
config string for every counter/countdown tick. The next goal is shown for each
track; Field Regular appears after all three first milestones.

Only the existing human focus selection is mutable. It uses the same validated,
rate-limited operation queue as chat. Pending requests cannot be replaced by a
second click, selection is not optimistic, and only a validated worker response
confirms the new focus. The worker persists it through the existing atomic
ledger. No XP, DDL, class, inventory or unlock is written by the frontend.

Contract progress is team progress, not personal captures. The HUD uses only
the current team and fresh native controller observations; expired, disabled or
unsupported tasks have no displayed values. Bars clamp at the goal while earned
numbers remain intact. Spectators/FFA do not get another team's task. The UI
never completes or credits a contract itself.

## Verification

Run the [offline baseline and client gates](UI-VALIDATION.md). Add `--ui` to
the existing isolated native runner:

```sh
python -B hosting/backend_verify.py --run --case mp_raid:dom --seconds 60 \
  --image outlands-t6:ui-dev --worker-image outlands-bo2-chat:local \
  --careers --squads --contracts --chat-context --expansion --ui
```

The native probe calls production presenters for loading, disabled, stale,
invalid, complete and saving states. Actual native bots exercise allocation,
both pages and repeated cleanup through real HUD methods. Bot exclusion and
the human-only focus queue remain enforced; no bot becomes a fake human.
The fixture also allocates all sixteen overlays together and verifies their
HUD handles are destroyed. Menu commands are excluded from bot reply generation.
These checks do not prove a real client received input or rendered the layout.

Later accept actual Windows/Linux clients at 1280x720 and 1920x1080: open both
pages, verify fonts/spacing/safe areas, change focus and observe acknowledgement,
retry rapid inputs, interrupt the worker, reconnect and rotate maps. Verify
death/spawn/disable/timeout cleanup. Check two humans' careers and teams remain
separate, and inspect normal BO2 progression after finishing and restarting.
Keep results and profile data private.

Native references: [HUD primitives](https://github.com/plutoniummod/t6-scripts/blob/main/MP/Core/maps/mp/gametypes/_hud_util.gsc)
and [custom command support](https://plutonium.pw/docs/changelog/).

The `--restart` fixture uses an explicit same-map reload, not a halftime or
round-preserving `map_restart`. Isolated FFA attempts with both `map_restart`
variants left bots connected but unspawned. Keep those failed results separate;
a full-reload pass does not accept warm FFA restart behavior with real clients.
