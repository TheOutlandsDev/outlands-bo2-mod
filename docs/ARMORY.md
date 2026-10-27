# Outlands Armory backend

The first Armory slice implements a single saved loadout per native identity,
strict rules and a next-respawn queue. It is a backend library, not an available
in-game editor. There is no live Armory command, endpoint or automatic equipment
change. Career/Contracts HUD behavior is unchanged.

## Accepted request and trusted observations

`ai/armory.py` accepts an exact, bounded class schema: optional primary and
secondary, separate attachment lists, three perk groups, lethal/tactical type
and count, and at most three wildcards. Cosmetic choices, scorestreaks, names,
rank and unlock flags are not part of this request.

`Catalog` and `Observation` are separate trusted adapter inputs. The server must
populate available items, full allowed attachment combinations, earned item and
weapon-specific attachment unlocks, the actual allocation limit, native identity,
session, map epoch, spawn ordinal, observation time and the earned native
Create-a-Class feature unlock. A client must never
supply these through a save request. No bundled fictional catalog is used at
runtime; the small catalog in the tests is explicitly synthetic.

Rules reject unknown IDs, wrong slots, locked content, excess allocation,
duplicate items and incompatible attachment combinations. Overkill, both
Gunfighters, three Perk Greeds and Danger Close have explicit constraints and
cost a point themselves. Each selected item/attachment/perk/equipment unit also
costs one point. A lower native allocation limit is respected. A knife-only
class costs zero; cosmetic selections are outside this schema. Equipment count
limits come from the trusted catalog. The current subset refuses Tactician
because its second tactical slot and native count/cost semantics are not yet
accepted. The custom validator is an additional gate, not a replacement for
Plutonium's native class validity check.

Missing unlock observations fail closed. Maximum observation age is five
seconds; future observations, bots, spectators and catalog changes are refused.
Rank alone never establishes an unlock. All unlocks are rechecked at claim time,
including after a prestige/reset or changed server restrictions.

## One saved slot

`ArmoryStore.save()` validates first, then uses expected revision and an
idempotent request token to commit one private slot. Rejected saves preserve
the previous bytes. Duplicate requests return the committed revision; a reused
token with different contents is rejected. Responses are copies, so UI callers
cannot mutate the stored class. The service has no cross-player lookup field in
an untrusted loadout: ownership comes from the trusted observation.

The Linux host store requires an owned mode-700 directory and mode-600 regular
state file, refuses symlinks/hardlinks, bounds records/bytes and atomically
replaces a flushed/fsynced temporary file. One worker must own this store; it
is not a concurrent multi-writer database. The file contains a random salt,
HMAC identity keys, class IDs, revisions and request/content digests. It contains
no raw native GUID, name, chat, session, address or native profile data. Consumed
claims retain only a keyed digest of session/map scope and a spawn ordinal. Armory
state is separate from Operations, bot careers and native BO2 saves. Store
errors must not be presented as a successful save or queued revision.

## Respawn semantics

`RespawnQueue.enqueue()` validates the committed class again. It can replace a
pending revision with the newest accepted revision for the same identity.
Enqueueing never touches inventory. The current life cannot claim it. Exactly
the next spawn ordinal, in the same human session and map epoch, can claim it;
a successful claim durably consumes the revision before returning it. Repeated enqueue after consumption
cannot claim the same revision again in that session. A claim returns
`claimed_not_applied`; only an adapter's actual equipment readback can confirm
equipping. An adapter failure must be reported and never silently retried into
a later life.

Disconnect must cancel the ticket. Map change, changed session, disabled or
spectator state, stale observations, missed spawn, changed unlocks or a newer
unqueued save invalidate it. The native adapter must increment the spawn ordinal
for every life, including round starts; team or mode transitions should cancel
the ticket. Restart intentionally discards pending tickets but preserves the
saved slot. Reconnect requires an explicit requeue and fresh native observation.

## Native integration checkpoint

Native BO2 `giveloadout` runs before `spawned_player`. The stock class menu can
also regrant a class immediately during its grace period. Calling either from a
post-spawn editor callback would not establish next-respawn-only semantics.
See the native [spawn path](https://github.com/plutoniummod/t6-scripts/blob/main/MP/Core/maps/mp/gametypes/_globallogic_spawn.gsc),
[menu class selection](https://github.com/plutoniummod/t6-scripts/blob/main/MP/Core/maps/mp/gametypes/_globallogic_ui.gsc)
and [class implementation](https://github.com/plutoniummod/t6-scripts/blob/main/MP/Core/maps/mp/gametypes/_class.gsc).
Plutonium documents `classIsValid` and dedicated-server class checks in its
[changelog](https://plutonium.pw/docs/changelog/).

`outlands_armory.gsc` has no `main`, `init`, human mutation path or commands. Its
read-only inspector accesses the first five native custom slots. A loopback-only
disposable bot fixture can stage a reference to an existing valid native slot,
check current weapon/ammo remain unchanged, then observe a real death/respawn
and compare granted primary/secondary/perks. This is class-reference feasibility,
not arbitrary loadout materialization or earned human unlock acceptance. Native
slot validity alone must never be relabeled as verified human unlock ownership.

The missing integration gates are authoritative human unlock/catalog export,
native-safe materialization of a separately saved custom class without rewriting
DDL, pre-loadout queue consumption, verified equipment acknowledgement and the
actual editor controls. Until those pass, the public API remains a local library
and the live server receives no Armory equipment changes.

## Verification

```sh
python -B -m unittest discover -s ai/tests -p test_armory.py -v
python -B tools/validate_system.py
python -B hosting/backend_verify.py --run --case mp_raid:dom --seconds 60 \
  --image outlands-t6:armory-dev --armory
```

The first command exercises the actual validator/store/queue. Validator tests
run on Linux and Windows; the private Linux host store tests explicitly skip
on Windows. The full offline runner includes the tests on Linux. Native tests
require a private image containing locally owned game files and use disposable
state, no network, no published ports and no humans. Reports distinguish these
three scopes from actual Windows/Linux client editing and native progression.
Follow the remaining [UI acceptance gates](UI-VALIDATION.md) before enabling a
class editor or describing mid-match customization as available. If a process
dies after durable consume but before equipment acknowledgement, the UI must
report unconfirmed equipment. A new revision or explicit reconnect/requeue is
required; the old claim must not silently replay after restart.
