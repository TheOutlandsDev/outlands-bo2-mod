# Native challenge-event preview

This optional development preview connects original server callback code to the
portable AN-94 headshot challenge. It is not part of the live script payload,
has no public HTTP input, does not equip a camo, and never writes native BO2
rank, Create-a-Class or DDL saves. The worker has no RCON or game control channel.

## Trust and ownership

`hosting/challenge_adapter.gsc` registers in the engine's additional unthreaded
player-death callback list. It leaves existing callbacks intact. Only a native
human attacker with a nonzero GUID can produce a challenge kill. The adapter
requires a confirmed enemy death, an AN-94 base weapon and a native head hit
with bullet/headshot means of death. Suicides, teammates, spectators, bots and
other weapons do not earn progress. Native victim death counters suppress a
duplicate callback for the same death. Attachment suffixes are reduced to the
base weapon without altering the weapon itself.

The game and private follower share a random mode-600 token. Native records
include that token, a map epoch, player-session identity and monotonic sequence.
The follower accepts anchored native records only, checks the token, requires a
human-session hello, binds slot/session/identity, and rejects departed sessions,
slot reuse, missing bindings and sequence replays. Ineligible sequence numbers
cannot later be rewritten as eligible kills. Private console logs contain
credentials and native identifiers and must never be uploaded.

The separate worker HMACs each native identifier using a private identity key.
Only salted keys and event fingerprints persist in its owned mode-700 directory.
Back up `identity.key` together with `progress.json`. This is server-local native
identity, not verified Google-account ownership or cross-server portability.
An account mapping must be independently verified before those claims can be
made. One worker owns this ledger; the runtime takes an exclusive writer lock.

## Backend verification

```sh
python3 -B -m unittest discover -s ai/tests -p 'test_*challenge*.py' -v
python3 -B hosting/challenge_verify.py --run \
  --image PRIVATE_GAME_IMAGE --worker-image PRIVATE_WORKER_IMAGE \
  --case mp_raid:tdm --seconds 90 --report-dir PRIVATE_REPORT_DIRECTORY
```

The native check installs preview scripts only into disposable state, uses
network mode `none`, publishes no ports and uses no live saves. It observes
real bot deaths through the registered callback, requires every bot death to be
rejected, checks no human progress ledger is created, and restarts the separate
follower. It never fabricates a native human or awards native XP. The Python
tests use synthetic trusted records to verify legitimate eligibility, duplicate
and changed replay rejection, player separation, interrupted writes, exact-once
progress and restart persistence. Those fixtures are not native-human evidence.

On startup, the worker replays the current regular console log in bounded chunks;
the durable reward receipts prevent duplicate awards. A worker offline across
archived log rotation may miss events. The preview fails conservatively instead
of reconstructing rewards from score totals. Durable archival ingestion and
transactional multi-server account ownership remain future work.

## Client acceptance and promotion

Keep the preview off the live server until actual human headshots and reconnect
identity are verified. Test wrong weapons, teammates, misses, one qualifying
headshot, client/worker/server restart and player separation. Compare native
BO2 progress before and after. A successful counter test still does not accept
a visible, owned or equippable camo. The original
[Lua menu source](../client-preview/README.md) has a separate loading gate.

Native callback reference:
https://github.com/plutoniummod/t6-scripts/blob/main/MP/Core/maps/mp/gametypes/_globallogic_player.gsc
