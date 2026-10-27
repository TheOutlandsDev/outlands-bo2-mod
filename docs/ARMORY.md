# Native Outlands Armory preview

The opt-in Armory now has a native HUD editor, server-side earned-unlock checks,
private single-slot storage and a native spawn integration. It is a base-class
preview awaiting real Windows/Linux acceptance. It does not edit native class
DDL, manufacture XP, unlock items, change the current life on Save, or replace
stock Create-a-Class.

## Tonight's client test

Join from the game console with `connect SERVER_ADDRESS:SERVER_PORT`, using
the host's privately supplied endpoint. Select a team and stock class and spawn.
Then use in-game text chat `!outlands armory` or console `say !outlands armory`.
Hidden `/!outlands armory` is also supported by the handler. The overlay does
not pause the match. It captures gameplay controls while open and keeps your
character vulnerable; open it when safe. Close chat/console, release held inputs,
then use ADS/Fire for rows, Tactical/Lethal for items, Use to save, Jump to equip
and Melee to close. See the [control table](COMMANDS.md#navigate-the-open-menu).

1. Use `!outlands down` / `!outlands up` to choose a row and `!outlands right` /
   `!outlands left` to change its item. Only currently earned, supported choices
   are cycled. A new slot starts as an empty draft; NONE is a legal choice.
2. Use `!outlands save`. Wait for SAVED / QUEUED, and confirm current weapons,
   ammo and perks have not changed. Close with `!outlands close`.
3. After your next normal respawn, inspect the actual primary, secondary,
   perks and grenade types/counts. Check another respawn retains the active
   class. A failed or late claim must not claim successful equipment.
4. Quit/reconnect, reopen the Armory and confirm the saved choices remain.
   Use `!outlands equip` to queue that saved revision for the next spawn.
5. Use `!outlands stock` or select a different stock class to cancel the
   Outlands class for subsequent respawns. Selecting the already-selected
   stock class may produce no native class-change event; use the chat command.
   Finish a round and confirm ordinary player/weapon progression survives
   restarting the client. With two players, confirm classes stay separate.

For every chat command above, prepend `say ` to use it in the game console.
Do not enter a bare `!outlands` there. The [command reference](COMMANDS.md)
explains hidden commands, private feedback and legacy aliases. Chat/explicit
`say` commands need no new client assets or bindings.

Optional `exec outlands_armory_keys.cfg` replaces F5-F9 and F11 bindings:
F5 toggle, F6 row, F7/F8 previous/next item, F9 save, F11 equip. Record your
existing bindings first. These overlap the optional Career HUD bindings.
Installers copy the CFG but never execute it. For an older client without that
file, use chat/console commands. A clickable mouse cursor is not
implemented. Keyboard/mouse and controller use the existing game actions. Native game-action navigation works
without these optional key CFGs. Accept the layout/fonts/input on both platforms
at 720p and 1080p;
backend HUD allocation does not establish actual client rendering.

## First native subset

The editor offers a primary, a pistol/launcher secondary, one perk from each of
three native groups, and ordinary lethal/tactical grenades with one charge each.
Items and localized labels are discovered from the installed native stats table.
Compound perks remain one pick but apply every native effect. Each selected
slot costs one point; the actual native allocation limit is displayed and
respected. NONE removes an item; knife-only is supported.

Attachments, wildcards, optics/camos/reticles, shields, ballistic knives,
scripted equipment and scorestreak editing remain in stock CAC. The standalone
backend library has broader attachment/wildcard rules, but those are not
exposed through this first native grant adapter. An advanced saved class is
refused rather than silently truncated. Stock scorestreak choices and earned
streak counters remain under native control.

Native `isitemlocked`, the earned `feature_cac` unlock, allocation-feature
unlocks, mode restrictions and item exclusions are read for each selected item.
The editor never infers ownership from displayed rank. The supported modes are
TDM, FFA, Kill Confirmed, CTF, Demolition, Domination, Hardpoint and Headquarters.
Disabled CAC or unsupported modes refuse application. Native metadata and actual
human unlock behavior still need client acceptance; no bot is relabeled as a
human for tests.

## Enable and rollback

The source defaults to off. Build the matching game and worker images and set
`T6_ARMORY_ENABLED=1` in the private Compose environment. The source and Dockhand
AI stacks pass it to both game and worker. Use the AI hosting profile even when
chat/model features are disabled: the Armory needs its persistence worker.
Entry point configures `outlands_armory` from that explicit flag. No port,
Tailscale access, credential or player profile change is required.

The adapter installs only if the native custom-loadout hook is free. A conflicting
hook blocks the feature instead of replacing another mod. The worker runs a
separate Armory thread so model response latency cannot block a respawn claim.
It reads private native observations and sends one fixed loopback RCON mailbox.
It has no public HTTP endpoint and sends no identities/loadouts to Ollama.

Turn the flag back to zero to close editors and stop future custom grants;
current inventory changes only at a normal spawn. Restore previous pinned images
for code rollback. Back up complete server storage and the private rival-state
volume before promotion. Keep Armory state/backups out of the public source.
No release tag implies real-client acceptance.

## Save, queue, grant and acknowledgement

`ai/armory.py` remains the strict validator and atomic single-slot store. Its
catalog and observation are separate trusted inputs, never editor-supplied
unlock flags. `ai/armory_native.py` parses bounded, anchored native-only records,
binds sessions/sequences/slots/identities and uses that same validator/store.
The exact seven-slot transport refuses extras and advanced combinations.

A save validates native unlocks, then commits a compare-and-swap revision before
acknowledging it. Duplicate requests are idempotent; altered/replayed requests
cannot replace an accepted revision. A pending revision is queued for one spawn
ordinal in the same connection and map. A save reply arriving after its intended
spawn is shown as saved but requires explicit Equip; it never changes a live
inventory. Cancelling invalidates the in-flight native mailbox as well as the
queue, so a late response cannot resurrect it.

The wrapper around native `level.spawnplayer` requests a durable claim before
calling the stock spawn path. It waits a bounded time before spawning; failure
retains the last accepted active class when valid, otherwise the stock class.
The native `givecustomloadout` hook grants the accepted base class during the
normal native class grant, before `spawned_player`. It refuses calls outside
that wrapper and clears its armed flag before mutation. No native class slot
is rewritten. Later lives reapply the active class with fresh native checks;
this is distinct from consuming the pending revision again.

After the native spawn event, readback checks actual primary/secondary/perk
effects, grenade counts/ammo and absence of unexpected base weapons. Native
scorestreak weapons are allowed. Only matching readback produces an equipment
acknowledgement. Saved, queued, durably claimed and equipped are separate states.
A process loss after durable claim may lose application, but cannot silently
replay it. If unconfirmed, save a new revision or reconnect and explicitly
requeue. Worker restart discards unconsumed queues; it preserves saved slots
and durable consumed-claim guards. Native XP/unlock acceptance remains a real
client test after these backend checks.

Damage/death/spawn closes the editor and releases its control ownership; native class changes, team changes, spectator
state and feature disable cancel queued/active classes. Map changes and reconnect
start a new session. Overlay ownership includes the session, preventing slot
reuse from displaying another connection's draft. Editors time out after forty
seconds, use a bounded set of client HUD objects and do not create extra command
listeners each time they open.

## Private data and failure handling

The Linux host store requires an owned mode-700 parent and mode-600 regular file,
refuses links, bounds entries/bytes and atomically replaces a flushed/fsynced
file. One Armory thread owns it. Only salted HMAC identity keys, class IDs,
revisions and request/claim digests persist. Raw GUID, session, name, address,
chat and native profile data do not persist in Armory state. Native identity
still has the existing LAN client's limitations; this is not a global account
system. Keep private console transport logs outside shared artifacts.

Disk failure does not acknowledge a save. A failure after rename requires store
reload before further mutation. Failed worker startup/request transport times
out without new equipment. Source tests inject malformed requests, locked
items, revision conflicts, two identities, duplicate claims, reconnects,
worker restarts, cancellations and interrupted writes. Keep raw diagnostics
and user profiles private.

## Reproducible checks

```sh
python -B -m unittest discover -s ai/tests -p 'test_armory*.py' -v
python -B tools/validate_system.py
python -B hosting/backend_verify.py --run --case mp_raid:dom --seconds 90 \
  --image outlands-t6:native-armory-dev \
  --worker-image outlands-bo2-chat:native-armory-dev --armory-editor --ui
```

Windows CI runs the portable validator/protocol tests and client setup checks;
Linux CI also runs private-store and backend-runner tests. Offline checks do
not launch a game or accept the interface. The isolated native runner uses
locally owned game files, no network/public ports, disposable volumes and bots.
It exercises real native class grants over two lives, compound perk effects,
current-life refusal, native reply/cancel checks, fixed loopback RCON through
the worker image and repeated editor HUD cleanup. The worker must start and no
human Armory ledger may be created by these all-bot fixtures. Pure worker tests
exercise the actual save/claim pipeline with explicitly synthetic identities.
Those are separate evidence scopes; real human transport/rendering/progression
remain tonight's acceptance gates.

`--restart` means a full same-map reload, not a warm/halftime restart. Existing
warm FFA restart limitations remain separate. Native references:
[spawn path](https://github.com/plutoniummod/t6-scripts/blob/main/MP/Core/maps/mp/gametypes/_globallogic_spawn.gsc),
[class grant/hook](https://github.com/plutoniummod/t6-scripts/blob/main/MP/Core/maps/mp/gametypes/_class.gsc),
[native bot unlock reads](https://github.com/plutoniummod/t6-scripts/blob/main/MP/Core/maps/mp/bots/_bot_loadout.gsc).
Follow the remaining [UI acceptance gates](UI-VALIDATION.md).
