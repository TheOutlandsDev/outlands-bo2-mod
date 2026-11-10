# Native challenge-event preview

This optional development preview connects original server callback code to the
portable AN-94 headshot challenge. It is not part of the live script payload,
does not equip a camo, and never writes native BO2 rank, Create-a-Class or DDL
saves. Both modes are disabled by default. Preview scripts stay outside the
live script payload. No commercial asset, live profile or credential is packaged.

## Trust and ownership

`hosting/challenge_adapter.gsc` registers in the engine's additional unthreaded
player-death callback list. It leaves existing callbacks intact. Only a native
human attacker with a nonzero GUID can produce a challenge kill. The adapter
requires a confirmed enemy death, an AN-94 base weapon and a native head hit
with bullet/headshot means of death. Suicides, teammates, spectators, bots and
other weapons do not earn progress. Native victim death counters suppress a
duplicate callback for the same death. Attachment suffixes are reduced to the
base weapon without altering the weapon itself.

The game and private follower share a random mode-600 token. Legacy native records
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
This legacy ledger is not automatically migrated into an account. One worker
owns each state directory; the runtime takes an exclusive writer lock.

## Account-owned mode

`ai/challenge_delivery.py` and `accounts/challenges.py` form the separate account
preview. It requires all of these independent opt-ins:

- Account service: `OUTLANDS_CHALLENGE_PREVIEW=1` (the internal route is absent
  otherwise).
- Offline operator capability for the already enrolled game server:
  `python3 -B /app/accounts/admin.py enable-challenges --server SERVER_ID` inside
  the account image with its existing private volumes. `disable-challenges`
  revokes that capability. Neither command is a browser/API operation.
- Disposable game configuration: `outlands_challenges=1`,
  `outlands_challenge_accounts=1` and the existing native account adapter enabled
  with `T6_ACCOUNTS_ENABLED=1`. Inject the preview scripts only in isolated state.
- A separate Linux worker using the private native token, enrolled server
  credential, owned mode-700 durable state and private RCON secret. Transport is
  reviewed HTTPS or same-network-namespace loopback HTTP; redirects and ambient
  proxies are refused. Its only game-control packet is the fixed grant mailbox.

The player must confirm the **current native session** through their signed-in
Google account and the existing private pairing code. Binding also requires a
fresh trusted native snapshot and the confirmed profile owner. A GUID, name,
browser request or previous pairing alone cannot authorize a new session. New
map/reconnect sessions require fresh confirmation with the current adapter.
After confirming the same Google identity on another PC/server, custom progress
belongs to that same Outlands account. Native BO2 saves and ranks stay separate.

The service issues an opaque six-hour grant bound immutably to the account,
server, profile and native session. Native callbacks emit eligible V2 records
only after a current grant is installed. Expired, mismatched or missing grants
produce no credit; there is no retroactive award for pre-link gameplay. The
native mailbox rejects stale requests, bots and reused slots. Renewals preserve
the ownership boundary. Private bind records contain a GUID; award records and
the durable outbox do not. Keep all raw logs, grants and databases private.

## Delivery and persistence

In account mode, the worker reads retained `logs/console-*.log` archives and the
active `console.log`. The host entrypoint uses rename/create rotation. Device,
inode, prefix and checkpoint-byte checks detect discontinuity. Each bounded
batch commits its staged events and read cursor in the **same SQLite
transaction**. Interrupted staging cannot advance the cursor alone. Partial
active records wait for completion; removed unread files, rewrites and
copy-truncation block ingestion instead of silently skipping rewards.

The private outbox retries until the account service acknowledges the award.
Account progress and the duplicate receipt commit in one transaction. If a
response is lost after that commit, retry returns a duplicate without another
increment. Changed replays, wrong servers and grant/session transplants are
rejected. Delayed events credit the grant's original account even after its
native session closes; they cannot be reassigned through a later GUID owner.
Only the signed-in account sees its custom progress in `/api/me`.

This guarantee covers completed records in **retained** logs and staged events.
It cannot recover engine-buffered records lost before logging, unretained logs
deleted during an outage, or arbitrary storage failure. Grant replay retention
is seven days from issue. Backlogs beyond that window stay pending for operator
review; they are never silently acknowledged. Keep archives/private state for
the recovery window, back them up together, and monitor pending counts. The
worker refuses implicit destination/credential changes and stops ingestion at
its explicit file/event capacity. No automatic cleanup sacrifices unread data.

## Backend verification

```sh
python3 -B -m unittest discover -s ai/tests -p 'test_*challenge*.py' -v
python3 -B hosting/challenge_verify.py --run \
  --image PRIVATE_GAME_IMAGE --worker-image PRIVATE_WORKER_IMAGE \
  --case mp_raid:tdm --seconds 90 --report-dir PRIVATE_REPORT_DIRECTORY
python3 -B hosting/challenge_verify.py --run --accounts-preview \
  --image PRIVATE_GAME_IMAGE --worker-image PRIVATE_WORKER_IMAGE \
  --case mp_raid:tdm --seconds 90 --report-dir ANOTHER_PRIVATE_REPORT_DIRECTORY
python3 -B hosting/account_verify.py --run --challenges-preview \
  --image PRIVATE_ACCOUNT_IMAGE --report-dir PRIVATE_ACCOUNT_REPORT_DIRECTORY
```

The native check installs preview scripts only into disposable state, uses
network mode `none`, publishes no ports and uses no live saves. It observes
real bot deaths through the registered callback, requires every bot death to be
rejected, checks no human progress ledger is created, and restarts the separate
follower. It never fabricates a native human or awards native XP. The Python
tests use synthetic trusted records to verify legitimate eligibility, duplicate
and changed replay rejection, player separation, interrupted writes, exact-once
progress and restart persistence. Those fixtures are not native-human evidence.

Account-mode native checks additionally exercise grant parsing, consume a fixed
invalid-owner mailbox canary, require zero installed bot grants/awards/outbox
events, and restart the worker. Account container checks use synthetic trusted
principals over real loopback HTTP, then restart the service and verify private
account progress, duplicate refusal and native-save separation. They do not
simulate a human inside the game or replace real Google consent evidence.

Source tests cover multi-archive outages, atomic rollback, response loss after
remote commit, malformed acknowledgments, cross-PC/server ownership, account
separation, expired grants, slot/session substitution and completion. Legacy
mode still follows only the current log; the archival guarantee applies to
account mode. Completing 25 headshots sets `completed`, while `reward_ready`
remains false until the original camo asset and equip path are accepted.

## Client acceptance and promotion

Keep the preview off the live server until actual human headshots and reconnect
identity are verified. Test wrong weapons, teammates, misses, one qualifying
headshot, client/worker/server restart and player separation. Compare native
BO2 progress before and after. A successful counter test still does not accept
a visible, owned or equippable camo. The original
[Lua menu source](../client-preview/README.md) has a separate loading gate.

Native callback reference:
https://github.com/plutoniummod/t6-scripts/blob/main/MP/Core/maps/mp/gametypes/_globallogic_player.gsc
