# Shared game-host status

Reviewed November 16, 2026. This is a dated operations summary, not a live status feed.

## What is running

SPT/Fika, DayZ and BO2 run in containers on the maintained shared host. A separate
containerized governor reads human activity every 10 seconds and changes relative
CPU priority. Active games use 4096 CPU shares; games with 180 seconds of continuously
confirmed idle activity use 256. Idle games remain running and joinable.

CPU shares take effect during contention. They are not a guaranteed core count,
CPU percentage, memory allocation or FPS gain. Idle games can use spare CPU and
retain memory. The governor does not stop games or change their memory limits.

## What has been checked

| Check | Result | Limit |
| --- | --- | --- |
| SPT real-player session | Two players detected; backend and Fika headless priority rose automatically; raid telemetry reported both players and the connected headless host in raid. | No measured FPS comparison or independent extraction/save result. |
| BO2 real-player session | One human with 15 bots detected; Docker and kernel priority confirmed high while the other games were idle at low priority. | Map-transition and precise leave timing remain separate checks. |
| Player feedback | The owner reported that SPT and BO2 both played very well. | Subjective session feedback; no controlled before/after benchmark. |
| DayZ | Native health/query, idle priority and removed hard CPU/RAM caps were checked. | Real player join, switching and gameplay remain pending. |
| Controller | Thirteen automated tests cover activity parsing, stale data, bot exclusion, switching, cooldown and rollback. | Automated checks do not replace connected-player tests. |

## Known limitation

BO2's native telemetry periodically becomes unavailable. The governor protects
that game at high priority, then starts a new three-minute idle cooldown after the
source recovers. BO2 can temporarily remain high priority while empty. This issue
is recorded and has not been fixed. Unknown activity never silently counts as idle.

## Package and privacy boundaries

The shared-host governor is a separately maintained host component. This status
note does not add it to a public game installer or provide a deployment bundle.
Independent hosts need their own reviewed configuration and acceptance checks.
Existing package versions, checksums and historical evidence keep their original scope.

Credentials, private endpoints, invitations, account bindings, player profiles,
saves and raw logs/operational receipts remain private. Share invented examples
rather than real connection data when reporting a problem.
