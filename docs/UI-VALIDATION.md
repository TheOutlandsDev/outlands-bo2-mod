# UI development and acceptance

Career and contract data feed an opt-in [native HUD preview](UI.md). Its actual
client rendering and input are not yet accepted. A full client menu and
mid-match loadout editor do not yet exist. The [Armory backend](ARMORY.md) supplies
single-slot validation/storage/queue code; native materialization and the
human unlock adapter remain pending. The following gates define how to
build and accept them. A backend pass is separate from a rendered UI pass.

## Repeatable offline baseline

From the project root, with Python 3.11 or newer:

```sh
python -B tools/validate_system.py
```

The runner executes the setup/hosting/release and AI regression suites, validates
chat configuration, exercises both synthetic fallback benchmarks, audits the
public source allowlist and checks Bash syntax on Linux. Windows runs the portable
validation-harness fixtures, configuration, both benchmarks and source audit;
POSIX permission/Wine regression suites remain on Linux. PowerShell parsing/setup
fixtures run separately in the Windows CI job. Reports identify the platform and
coverage profile. No game, model, credentials or player saves are required by these source
checks. Timeout, failed startup, a failing check or source changes during the
run fail validation. Remaining checks still run after an individual failure.

Each run creates a fresh private directory beneath `runtime/validation` with
per-check logs and `report.json`. An explicit `--report-dir` must also be fresh.
The summary binds evidence to a SHA256 of audited public paths and file bytes;
it contains check outcomes and acceptance status, without raw logs or player
identifiers. Keep logs local. CI uploads only the summary for each platform.
Compare source digests before reusing a result for a later build.

Exit 0 means only `source_passed`. Exit 1 means failed or invalid evidence.
The additional `--require-ui` switch returns exit 2 after a source pass while
UI acceptance is incomplete. No UI readiness can currently be granted by this
runner; adding real UI tests is part of implementing each screen.

## Gates for each screen

| Gate | Required evidence | Where it runs |
| --- | --- | --- |
| Data adapter | Production view model tested with new/earned/completed careers, team and FFA contracts, disabled features, loading, stale and unavailable data | Offline regression tests, added with the adapter |
| Commands | Production handlers reject invalid track IDs, out-of-order replies, expired sessions, slot reuse and another player's requests; repeated clicks cannot duplicate rewards | Offline tests and disposable engine probes |
| Navigation | Open, close, back and focus transitions; no duplicate listeners or input/HUD objects after respawn, reconnect and map change | State tests plus engine/client checks |
| Rendering | Readable at 1280x720 and 1920x1080, correct scaling and clipping, clear selection and loading/error feedback | Actual Windows and Linux clients, screenshots kept private |
| Input | Keyboard/controller prompts match bindings; mouse hit targets checked if implemented; closing restores normal controls | Actual Windows and Linux clients |
| Integration | Native scripts load, update production career/contract fields and release temporary HUD state; errors/crashes fail the run | Disposable engine state, then actual clients |
| Persistence | Select a focus, reconnect, rotate maps and restart; native XP and earned unlocks remain intact | Synthetic ledger tests plus actual clients |

Unavailable data must display as unavailable, not zero earned progress. Reward
labels must describe implemented rewards. Do not display native rank or unlocks
from an Outlands milestone counter. Contract progress must be labeled as team
progress where it comes from team counters. Display-only previews use fictional
fixtures and must be visibly identified as previews.

## Disposable native baseline

Use locally built candidate images containing the exact intended payload.
Record their immutable image IDs and compare copied source bytes with the
candidate before treating the result as candidate evidence. The source runner
does not verify image contents or import an older native report as acceptance.
Existing engine checks can be run independently:

```sh
python -B hosting/backend_verify.py --run --case mp_raid:dom --seconds 60 \
  --image outlands-t6:local --worker-image outlands-bo2-chat:local \
  --careers --squads --contracts --chat-context --expansion
```

Omit `--run` to inspect the plan. This uses disposable volumes, network mode
`none`, no published ports and no live profiles. Native bots remain bots; no
synthetic human is inserted into a production match. Existing probes cover
career/helpers, bot exclusion, contracts, squads and chat context. They do not
exercise a graphical menu. Add UI-specific probes when the UI adapter exists.
Raw reports remain private. A native crash or script error fails acceptance,
including a run that later recovers.

Keep UI probes and experimental handlers off the live server until their
source and native checks pass. Preserve a rollback image and existing player
storage before promotion. A graphical menu must pass both client platforms
before describing cross-platform UI support as verified.

## Loadout editor gate

Start with one Outlands class slot. Add tests against the production validator
for earned unlocks, Pick-10 costs, wildcard requirements, attachment conflicts,
invalid IDs, malformed requests and class ownership. The server must validate
every save. A successful UI click is not evidence of an accepted loadout.

Tests must show exactly one pending revision applies on the next eligible
respawn, no inventory change during the current life, and defined behavior for
round changes, disconnects, map changes and repeated saves. Rejected changes
preserve the last valid class. Persist only after validation and test interrupted
writes/restarts. Verify the actual spawned weapons, attachments, perks and
equipment on both clients; compare native progression before and after use.
Stock Create-a-Class integration remains a feasibility checkpoint. Do not
automatically write native class/DDL saves to simulate an implemented editor.

## Promotion record

For each candidate, retain source digest, private image IDs, check results and
platform-specific client results together. Keep pending gates explicit. Public
updates may include methods and aggregate results, without connection details,
identities, game assets, profile data, raw logs or screenshots containing them.
