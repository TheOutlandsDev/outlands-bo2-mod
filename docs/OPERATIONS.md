# Outlands Operations

An optional server-owned career accompanies normal BO2 rank and weapon XP.
It never changes native stats, damage, inventory, weapon unlocks or player saves.
No new client assets are required. Windows and Linux use the same server logic.

## First operation: Broken Signal

| Track | Server-observed credit | Milestone thresholds |
| --- | --- | --- |
| Assault | New personal kills after the connection baseline | 25, 100, 250 |
| Objective | Completed team-points contracts with personal score contribution during that phase | 3, 10, 25 |
| Support | Completed combined-score contracts with personal score contribution during that phase | 3, 10, 25 |

Objective credit is participation in a team contract, not an individual capture
count. Support credit is a score contribution, not proof of an assist or rescue.
Bots cannot earn human milestones. Joining after a completion or remaining idle
cannot earn contract participation. Counter resets and excessive jumps rebase
conservatively. Disabled intervals do not earn catch-up credit.

All three tracks progress together. Free-for-all can advance Assault; team-contract
tracks require a supported team mode. Public chat commands `!career` and
`!track assault`, `!track objective`, `!track support` display progress or select
a focus. Responses are private on-screen notifications, not public profile
broadcasts. Notifications appear on restore, a milestone, a focus change or an
explicit request rather than every sample. Selection persists on this server.

The first milestone in all three tracks completes Broken Signal and earns the
Field Regular designation in the operation notification. This is an Outlands
commendation; it is not a custom BO2 calling card or native equipment unlock.
Additional weapon mastery, armory rewards and operation chains are future work.

## Hosting and persistence

The AI hosting overlays explicitly enable `T6_OPERATIONS_ENABLED=1` on game and
worker. Source/default installs leave the feature disabled. The game switch is
`outlands_operations`; the worker switch is independent of chat and bot careers.
A worker with operations enabled can run without Ollama generation. Its service
may still depend on Ollama through the provided full AI hosting overlay.

The private `/rivals/operations.json` ledger uses atomic mode-600 writes in an
owned mode-700 directory. Back up the complete rival-state volume while the
worker is stopped. Its random server salt and HMAC identity keys must stay with
progress. It stores numeric milestones, a chosen track and bounded replay
metadata. Raw GUIDs travel only through the private native console transport;
names, GUIDs, chat and addresses never enter the persistent operation ledger or
model prompts. Do not publish this state or raw diagnostics.

Identity uses the native nonzero hexadecimal `player.guid`, never a display-name
fallback. Missing/invalid identifiers earn no credit. Native/LAN identity is not
an authenticated cross-server account system: clients sharing or changing an
identity can share or lose access to progress. Reconnect stability on each actual
Windows/Linux client must be accepted in a later gameplay test. These rewards
are cosmetic; do not add trading or valuable entitlements on this identity model.

The worker commits before replying. Retries reuse the exact observation and
cannot double-award progress. Reconnect/map changes establish new baselines;
worker restarts retain observed sequence numbers. Caches are bounded and old
console logs are not replayed. A crash before an unreported observation reaches
the worker can lose that unsampled interval; samples run about every 15 seconds
plus a final map-end observation. This is conservative rather than speculative.
One game mailbox is serialized and validates the pending session, slot, live
human identity, numeric bounds and expiry before showing any response.

## Signal Four and conversation

NightLedger, CopperWren, StaticBloom and RiftRunner form a featured recurring
character group, Signal Four. Their existing native class roles remain intact.
Membership influences personality context; it does not claim all members are
currently present or on the same team, force a roster, or create new combat AI.
Existing objective squads continue to own current attack/defend assignments.

V3 chat adds explicit turn/limit fields and numbered replies. Most conversations
remain two lines; 35 percent may use the configured `outlands_chat_turn_limit`
(2-4, default 4). Each accepted delivery schedules at most one next turn from a
different eligible same-team bot. Human messages cancel queued followups. All
turns share the existing six-request/minute ceiling, global and per-bot gaps.
State changes, departures, expiry and disabled switches cancel stale exchanges.
V1/V2 worker inputs retain their legacy two-line behavior.

Verified contract completions create short-lived chat opportunities, coalesced
into one pending event. A fresh compatible contract snapshot is still required.
Middle turns may ask a short question; final turns close. Replies can acknowledge
another bot without repeating words such as contract or objective, while false
completions, contrary orders, invented counts and named flags remain rejected.

## Verification boundaries

Run the Python regression suites, configuration check and source-package audit.
`hosting/backend_verify.py --expansion --chat-context --squads --contracts`
adds isolated native checks for module loading, GUID/numeric/tier helpers and
bot exclusion. Synthetic worker tests separately check progression, selection,
reconnect/restart replay, failed writes, private permissions and chat chains.
No synthetic human observation is inserted into a live server.

Backend checks do not establish human command delivery, real-client GUID
stability, visual notifications, conversational quality or fun. Accept those
later with real clients, including reconnect, map rotation and full restart.
