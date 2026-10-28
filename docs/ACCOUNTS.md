# Personal Outlands accounts — opt-in development preview

One Google-backed Outlands identity can link multiple native profiles on enrolled
servers. The private account screen is separate from the anonymous, read-only
[shared portal](PORTAL.md). This preview is disabled by default and is not a live
login or cloud-save service. No released client automatically enables it.

## What is implemented

- Google authorization-code login requests only `openid`. State, browser binding,
  PKCE and nonce protect the exchange. The official `google-auth` verifier checks
  signed tokens, issuer, audience and expiry. Only a keyed hash of the verified
  stable Google subject enters the account database; Google passwords, email,
  profile names and tokens are not stored.
- An opaque, revocable, seven-day browser session selects the private account.
  Same-origin JSON writes cannot select a different account through request JSON.
  Outlands display-name edits use a revision check.
- An operator-enrolled worker observes human native sessions, snapshots and
  requests for `!outlands link`. A private one-use code expires after three
  minutes. The browser confirms the current session, including after reconnect
  or map change. Names and LAN GUIDs alone do not authenticate a browser user.
- The adapter reads native rank XP and available player rank/prestige. It does
  not read weapon progression, inventories, unlock lists or local save files.
  Stats are absolute observations with freshness and profile/server provenance.
  An exact duplicate cannot refresh liveness or award progress.
- Linked profile ownership survives restarts; current session authorization does
  not. Reusing a LAN name/GUID cannot transfer an already linked profile to a
  different account. Silent sessions lose their live indication after 30 seconds.

The account works across PCs and servers by linking their distinct profiles.
Their XP is not summed or merged. Native progression remains in BO2 saves on the
machine/profile used by the client. Full save portability, conflict resolution,
backup/restore and automated companion proofs are separate future work.

## Trust and operational limits

The worker is trusted to report its enrolled server's observations. This is not
anti-cheat or proof that a LAN profile cannot be impersonated in-game. A confirmed
account session does not authorize a different account's dashboard. A session
nonce may not be reopened during the retained replay window.

Private SQLite storage uses a stable 32-byte identity key, owned mode-700
folders and mode-600 files on Linux. Back up the identity key and database
together while the service is stopped. Do not regenerate the key against an
existing database. The initial implementation is single-host SQLite with
explicit limits (4,096 accounts, 64 servers and 32 profiles per account); it is a
foundation for migration, not a large-scale production claim. Account deletion,
recovery/unlink, server credential rotation and multi-host database operations
remain release gates before wider rollout.

The native console contains private session/profile observations for its local
worker. It must remain outside public logs/artifacts. Pairing codes must appear
only to the requesting player, never in public chat or model prompts. The fixed
RCON response mailbox and real client code display need acceptance before enable.

## Prepare Google and HTTPS

Use an operator-controlled HTTPS account origin, represented below by
`https://accounts.example.org`. Do not use that placeholder as a real deployment.
Create a Google OAuth **Web application** client with the exact redirect URI:

```
https://accounts.example.org/auth/google/callback
```

Configure the consent screen, authorized domains and test users as required by
the Google project. Download its OAuth client JSON directly to a private host
file outside this repository, mode 600. Never paste its secret into chat, GitHub,
Compose environment values, commands or public artifacts. The JSON must contain
`web.client_id`, `web.client_secret` and the registered `redirect_uris`.
See [Google's OpenID Connect setup](https://developers.google.com/identity/openid-connect/openid-connect)
and [server-side token verification](https://developers.google.com/identity/sign-in/web/backend-auth).

The account backend binds only `127.0.0.1:8087` inside the Tailscale network
namespace. A reviewed HTTPS reverse proxy must preserve the configured Host,
keep the backend unreachable through other ingress paths and route only the
account application. No TLS proxy, Tailscale Serve change or public forwarding
is configured by the overlay. Keep the existing shared portal separate.

## Private bootstrap after origin/proxy review

Build the source image with `docker compose -f hosting/compose.yaml -f
hosting/compose.accounts.yaml build accounts`. Include your existing private
Compose overrides when appropriate. Store `OUTLANDS_ACCOUNT_ORIGIN` in the
private host environment. Keep `T6_ACCOUNTS_ENABLED=0` throughout preparation.

For the following commands, use the same Compose project and base/overrides as
the running host. The extra account overlay declares three dedicated volumes;
it does not mount client save folders. The tools profile has no network.

```sh
# OAuth JSON comes from a private file mount. Container root only bootstraps
# ownership of these new account volumes; credentials are never printed.
docker compose -f hosting/compose.yaml -f hosting/compose.accounts.yaml \
  run --rm --no-deps --user 0:0 --cap-add CHOWN --cap-add DAC_OVERRIDE \
  -v /private/google-client.json:/seed/google-client.json:ro \
  account-admin configure --origin https://accounts.example.org \
  --google-client /seed/google-client.json

# Use a stable non-personal server identifier of 16-128 safe characters.
docker compose -f hosting/compose.yaml -f hosting/compose.accounts.yaml \
  run --rm --no-deps account-admin enroll --server example_server_001
```

Existing outputs are never overwritten. Normal file-write failures roll back
enrollment. A process/power failure between file persistence and SQLite commit
requires an offline operator check of enrollment before retrying; do not delete
or regenerate credentials blindly. Do not run bootstrap on a live database.
Only the offline bootstrap above adds CHOWN and DAC_OVERRIDE to read the private
seed and initialize ownership in its mapped volumes. Runtime services retain no
capabilities. Review this bootstrap alongside the concrete deployment before use.

Start only the account service behind the approved HTTPS proxy first. Verify real
Google login, wrong-account isolation, logout and expiry. Enable the worker and
`T6_ACCOUNTS_ENABLED=1` only after the native acceptance gates below pass. Existing
base hosting does not include this overlay and remains unchanged.

## Reproducible validation and remaining gates

Install `accounts/requirements.txt` in an isolated environment, then run:

```sh
python -B -m unittest discover -s tests -p 'test_account*.py' -v
python -B -m unittest discover -s tests -p test_google_login.py -v
python -B tools/validate_system.py
# With a separately built private game image (no public game assets):
python -B hosting/backend_verify.py --run --image outlands-t6:accounts-dev \
  --case mp_raid:dom --seconds 60 --ui --accounts
```

The Linux CI job also builds the rootless account image and exercises the real
configure/enroll/start/restart sequence with synthetic OAuth configuration in
new disposable volumes. It rejects repeated bootstrap, checks mode-600 secrets
and database, verifies anonymous API refusal and removes its fixture resources.
To reproduce without real credentials or live server data:

```sh
docker build -f accounts/Dockerfile -t outlands-bo2-accounts:dev .
python -B hosting/account_verify.py --run --image outlands-bo2-accounts:dev
```

Without `--run`, the verifier prints its plan and creates nothing. It uses only
a locally built image, no network and no published ports. Reports remain private.
This catches deployment ownership/capability errors that in-process fixtures
cannot reproduce.

CI explicitly imports the pinned verification dependencies before tests so RSA
signature cases cannot silently skip. Fixtures cover two-account isolation,
concurrent code claims, reconnect/replay, expiry, revision conflicts, native
protocol bounds, fixed mailbox transport, failed private-file writes and actual
RSA signature rejection using fixture keys. These do not authenticate real
Google users or establish real client usability.

`test_account_agent.py` also runs the actual worker main loop against a temporary
console log, the real loopback account HTTP server and a loopback UDP receiver.
Only its private fixture paths and wait/stop boundary are substituted. It checks
that old logs are skipped, fresh observations survive worker restart, native XP
can decrease without being merged, one-use codes reach only the fixed mailbox,
and another browser account cannot view or claim an owned profile after reconnect.
The test uses synthetic principals and does not promote a native bot to a human.
Both CI platforms include this test through the account test discovery command.

For preparation from a phone, validate the account page and Google login while
connected to the host's tailnet, then complete the distinct second-account
privacy test with another consenting identity. Keep native linking disabled
until a controlled game-client test is ready. At that test, sign in on the phone,
join the game on the PC, type `!outlands link` in game chat and enter the private
code on the account page. Check actual XP/level/prestige, reconnect and confirm
again. Phone-width browser checks and synthetic worker transport do not establish
in-game code readability, real-device access or player-stat correctness.

Required enablement gates:

1. Review the concrete HTTPS origin/proxy and private credentials; test the real
   registered Google callback with two consenting test accounts.
2. Compile/load the adapter in the native engine, reject all test clients as
   account holders, and verify the fixed response does not leak pairing codes
   into console/container logs. Do not fabricate a human identity for this test.
3. On real Windows and Linux clients, request a private code, confirm it in the
   browser, verify actual rank XP observations and freshness, reconnect and
   confirm again. Check code readability and focus/navigation on mobile.
4. Prove other accounts cannot see or claim the linked profile; check logout,
   expired codes, restart persistence and key/database backup restoration.
5. Complete recovery/deletion/rotation workflows and capacity/load testing before
   broader use. Plan a shared database and authenticated per-server transport
   before spreading the service across hosts.

Rollback: set the native flag to 0, stop only account services/proxy routes and
remove the optional overlay from future host invocations. Retain encrypted
private account backups for recovery. Native saves were never modified.
