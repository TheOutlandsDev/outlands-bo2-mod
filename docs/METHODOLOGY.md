# Implementation methodology

Outlands extends native Plutonium T6 LAN multiplayer with original GSC modules,
client setup tools and an optional local chat worker. The design preserves
normal earned human progression and native bot control while adding configurable
population, appearance, class roles, objective squads, contracts and conversation.

## Components and ownership

| Component | Responsibility |
| --- | --- |
| Client setup/launch helpers | Validate owned inputs, save a stable LAN name and private join configuration, launch the official runtime |
| Wine dedicated game container | Run native multiplayer and load original source from `storage/t6` |
| Tailscale sidecar | Provide private network reachability with its own persistent identity |
| `outlands_native_bots.gsc` | Own population filling and bounded recovery |
| `outlands_bot_identity.gsc` | Apply bot-only cosmetic level and prestige display |
| `outlands_bot_profiles.gsc` | Filter native class choices and adjust optional patrol cadence |
| `outlands_bot_careers.gsc` / `ai/careers.py` | Persist fictional-bot native-score deltas and restore guarded cosmetic careers |
| `outlands_squads.gsc` | Allocate bot-only attack/defend/support duties through guarded native objective hooks |
| `outlands_contracts.gsc` | Observe native team/player deltas for timed match-local contracts and commendations |
| `outlands_chat.gsc` | Schedule bounded events and validate responses before native speech |
| `ai/bridge.py` and Ollama | Generate or select short chat lines through a fixed local response mailbox |
| `tools/build_release.py` | Audit and package an explicit source-only allowlist |

The game shares the Tailscale sidecar's network namespace. Compose publishes no
host ports. Persistent game state, Tailscale identity and optional model weights
use separate volumes. Dockhand imports the image-only Compose variant after
private images are built locally. Full game images must remain private.

## Progression and identity

Human XP, unlocks and weapon progression stay under native game rules. Setup does
not copy saves or grant equipment. A stable, unique LAN player name identifies a
client's LAN profile; changing it can select different progression. Preserve the
active runtime's complete `storage` directory when backing up or updating.

Bot identity is separate from human profiles. The identity watcher waits for
native bot loadout initialization and checks `istestclient()` before applying
native display calls. Weighted levels and prestiges are sampled once per bot
connection, bounded against native rank/icon limits and reapplied after respawn.
Random display identities do not write DDL XP or change loadout eligibility. The
optional [rival ledger](RIVALS.md) adds persistent fictional-bot careers from native
scoreboard deltas, with separate cosmetic XP and guarded restores. The roster
contains fictional aliases and matching chat voices.

## Population and match settings

One fill controller owns bot population. Stock `bot_friends` and `bot_enemies`
stay at zero to avoid competing generators. After a human joins, the controller
polls every two seconds and adds at most one native test client per check, up to
the configured total and server capacity. Dead players still count as connected.
Population reductions remove only native bots.

Three failed native additions trigger a 10-second retry cooldown; subsequent
failed batches increase this to 20 and at most 30 seconds. Polling continues
during cooldown. Human-count or target changes reset recovery state. Defaults
are native Hard difficulty and 16 total players, yielding 8v8 in team modes.

For team modes, cooperative join hooks wrap native auto-assign and explicit
team selection. Humans follow the current human cohort until that side reaches
capacity; overflow uses the other side. Existing spectators are not moved. The
stock automatic team balancer is paused while cooperative placement is active,
then restored when that feature or the native-bot module is disabled, including
on a later FFA map. Native class, spawn, team-change and halftime rules still run.

A shared count planner handles both total fill and team quotas. It removes only
verified bots from an oversized side before adding native bots to the smaller
side, even when the lobby is already full. Unassigned bots get time to initialize.
Spectator connections reserve slots; the active budget rounds down to an even
total to avoid a remove/add loop. Configurable idle fill keeps an all-bot match
running without humans; zero disables idle management and leaves existing bots alone.
Both settings default on and migrate only when absent from host configuration.

Each mode wrapper resets native defaults before loading its matching mode and
applying doubled time/score targets. Native objective, overtime and round rules
remain authoritative. The default rotation lists the base maps plus Nuketown
2025; operators must supply owned assets for every selected map.

## Class roles and movement

Profiles hook native class-pool and patrol functions only when their required
helpers exist and no other mod already detours those functions. If unavailable,
the profile layer disables itself and leaves native behavior intact.

The original native generator owns valid weapons, attachments, perks and
equipment. A connection role filters eligible native class choices:

| Role | Preferred weapon groups |
| --- | --- |
| Rusher | SMG and shotgun |
| Assault | Assault rifle |
| Objective | Assault rifle and SMG |
| Support | LMG and assault rifle |
| Marksman | Sniper rifle |

Native initialized presets provide a fallback when filtering produces no
eligible choices. Native anti-air threat handling keeps the full native class
pool. Marksman roles have a configurable cap, defaulting to two.

Optional patrol timing varies low-priority patrol refresh intervals by role.
Native goal selection, pathfinding, objective logic, combat and stuck recovery
remain in control. This changes cadence; it does not implement learned routes,
opponent imitation or an adaptive combat model.

## Objective coordination and contracts

The optional [squad layer](SQUADS-CONTRACTS.md) allocates bounded duties per team
and reassesses actual native objectives. It uses only the current gametype's
helpers, checks detour ownership and falls back to stock behavior when a hook,
target or path is unavailable. Low-priority perimeter duties cancel only their
own goal on disable or reassignment. Combat, carrier interactions and emergency
recovery retain native priority; the model never chooses movement commands.

Contracts measure adjacent native kill, individual-score or team-score deltas.
New occupants and team switches establish fresh baselines. Counter decreases
rebase independently; implausible jumps give no credit. A strict deadline and
one completion transition prevent late or duplicate commendations. Rewards are
match-local announcements/counters, with no native progression or save writes.

The disposable runner checks both modules against real engine counters, including
initial disable, unsupported modes, mid-match disable/resume and restarts. Native
goal acknowledgements establish that calls were accepted; they do not establish
which goal wins priority, smarter route choice or better human-perceived balance.

## Local conversation pipeline

The GSC adapter emits a versioned, bounded event. The worker validates its shape,
deduplicates IDs, applies queue/rate limits, then requests a short Ollama reply
or chooses a canned fallback. The model recipe configures a separately obtained
base model; it does not distribute weights or claim training from scratch.

The worker can submit only a fixed response dvar over loopback RCON. It cannot
execute model-selected commands. Output is length-limited and reduced to a safe
character set. Before `sayall`, GSC checks the exact pending ID, native bot status,
slot/name, current request lifetime and enabled state. Slots reused by humans
cannot receive bot speech.

Ambient conversation uses explicit numbered turns, usually two and at most four.
Human public-chat replies take priority and cancel queued followups. All turns
share global, per-bot and per-minute budgets. Context is short-lived; chat is
generated only from native bots and fresh context; optional no-audience
speech is controlled by `outlands_chat_without_humans`. Team/hidden chat is excluded. The worker stores
no persistent chat text; its short model context stays in memory. Console events
can contain public chat, so raw server logs
must remain private. See the [chat protocol](../ai/README.md) for exact limits.

## Configuration, testing and distribution

Shipped nonsecret defaults and scripts are distinct from private operator state.
Host startup refreshes source payloads and migrates supported new defaults while
preserving existing operator choices. Review main-CFG merges deliberately;
retain private credentials, access-policy lines and rollback backups.

Use synthetic unit tests for setup, migration, packaging and chat boundaries.
Use a separate, network-isolated native server for GSC integration. Use real
client gameplay for rendered presentation, movement quality and earned progress
after restarting. The [validation guide](VALIDATION.md) describes these checks
without exposing individual session data.

GitHub CI checks Linux and Windows setup logic before packaging. The public
archive contains only allowlisted original text sources, with deterministic
ordering, modes and timestamps. Game assets, vendor binaries, images, model
weights, runtime prefixes, profiles, logs, invites and credentials are excluded.
Technical documentation uses generic examples and does not include personal
playtest narratives or deployment identities. Preserve existing release tags;
publish changed release contents under a new version.

## Grounded task conversation verification

Capture squad, objective and contract context through the same formatter used by
production requests, in network-isolated native bot matches. Validate exact
schemas, current assignments and contract values; reject malformed snapshots.
Test the optional no-human request guard and context off switch independently
from a probe-only native speech primitive. The ambient-chat assay instead uses
production idle fill, a real worker and matching native speech ACKs. Never
fabricate human presence. See [rotation and idle matches](ROTATION.md).

Feed private snapshots to the worker's model benchmark with no RCON credential
or server-state mount. Require bounded, task-compatible output and report model
versus fallback use. Unit checks cover conflicting orders, false completion,
stale conversation context, team/phase matching and existing rate/queue guards.
These checks do not establish human-visible timing or naturalness; retain that
as a separate client acceptance test. Publish code and aggregate outcomes only.

Native team changes may leave a rejected squad record until reassessment. Count
only assignments for the bot's current team, require the production validator to
reject stale records, and fail if a rejected record retains an Outlands movement
goal. Final observations still require complete role allocation. An isolated
same-frame metadata fixture can check steering/context rejection without changing
native teams, goals, human presence, scores or progression.

## Air-support reaction tuning

An optional profile hook wraps native `threat_should_ignore`, retaining the
native result first. Only dedicated-server test clients receive the additional
gate, and only UAV/counter-UAV or helicopter/plane entities qualify. Players,
ground equipment, remote mortars and quadrotors retain their native filtering.
Per-bot state is keyed by target entity, so interleaved aircraft do not restart
each other's timers. Entity references reject stale entries after destruction.
The initial 2500 ms delay has up to 50 percent random jitter; a stable 80 percent
participation roll reduces simultaneous responders. Values are bounded and
operator settings survive host upgrades. Delay 0 plus chance 100 restores stock
selection immediately; profile/native-bot off switches bypass the hook.

The implementation changes target eligibility, without rewriting aim, rocket
lock-on, scorestreak health or damage. Native threat discovery may already take
longer than the gate. Private script-entity fixtures exercise classification,
actual engine timing, interleaved targets, participation extremes, stock override
and native-ignore precedence; they do not establish real aircraft lifetime or
human-perceived balance. Those remain a gameplay test with earned streaks.

## Ground-streak EMP support

The optional `outlands_bot_ground_support` hook retains native Guardian/sentry
navigation danger marking. An actual native turret encounter starts a
team-shared, four-second reaction timer. Sightings expire after twenty seconds;
friendly, unowned, carried, inactive and destroyed turrets are excluded.

After pressure is established, one living bot per team can replace an existing
flash, concussion or smoke tactical with one EMP on its next spawn. Native
item unlock and equipment rules must permit it. Empty tactical slots and spent
grenades are never replenished. Human loadouts, stats and unlocks are untouched;
existing native EMP classes retain their allocation.

The responder requests a native flank node at priority two, below immediate
combat/cover behavior. Within nine hundred game units and line of sight, it
turns through native look controls and requests the real secondary-tactical
input. It yields to living player threats, remote streak control, planting,
defusing and flag carrying. It never overrides global danger nodes, teleports,
applies direct damage or invents a grenade. Normal offhand animation, projectile
physics, ammunition consumption and streak damage remain native.

The stock EMP helper uses `emp_mp`, while the MP inventory uses
`emp_grenade_mp`. Native helper requests did not reliably produce projectiles in
the isolated engine. The guarded ground-target path uses a short, owned tactical
button press instead. Native `grenade_fire` with the correct weapon and a real
entity confirms delivery. A six-second shared cooldown applies to requests and
confirmed throws; pending requests expire without spending or refilling ammo.
Input ownership survives stale cleanup attempts and releases on firing, normal
completion, death, respawn, timeout and match end. Only bot-owned tactical input
is released. Other targets and the feature off switch use the original helper.

Per-map request/projectile counters and the last per-bot projectile count support
backend diagnostics without publishing names, positions or player data. Set
`outlands_bot_ground_support 0` to restore stock behavior. Disabling profiles or
native bots also bypasses the feature. Configuration migration preserves an
explicit operator setting. This is one adaptive equipment role per team; it
cannot promise a counter when native unlocks, tactical allocation, active combat
or survival prevent one. Lane movement and effectiveness require playtesting.

## Responsive casual chat

Ambient openers default to thirty seconds and a second bot may answer after
twelve seconds. All turns and public human replies share a six-request minute
budget, a ten-second global gap and a forty-five-second per-bot cooldown. Failed
requests consume that budget too. An exchange remains bounded to four delivered lines.

The worker classifies only the recipient bot's fresh own public scoreboard,
separately from fictional career totals. General prompts and fallback lines can
acknowledge a rough match, favorable personal score or trades without inventing
streaks, team results or enemy positions. Public-message replies address their
input first; task prompts continue to exclude unrelated career/performance data.
Snapshots expire after sixty seconds and never become current merely by loading
the private career ledger. The model cannot change gameplay through this path.

A host can apply these numeric chat dvars live and recreate only the worker to
load generator changes. Preserve other host settings and the rival ledger;
read back live dvars and require new native delivery ACKs. Game restarts are not
required when the installed GSC protocol remains unchanged.


## Separate challenge careers

[Outlands Operations](OPERATIONS.md) observes human kills and personally
contributed team-contract completions. A deterministic worker commits milestones
to a separate salted private ledger before returning a bounded notification
profile. The model neither sees human identities nor awards rewards. Native XP,
DDL, equipment and saves remain unchanged. Synthetic restart/retry/atomic-write
tests and isolated native bot-exclusion checks are separate from later real-client
identity and command-delivery acceptance.

## Native command ingress

Career, Contracts, Operations and Armory share a bounded chat normalizer. The
engine can attach two control bytes before text; stripping a single byte makes
an otherwise correct command fail. Test the engine's actual `sayall`/`sayteam`
event payload before attributing failures to a client or network endpoint.
Local commands produce private feedback and fixed identity-free diagnostics.
They accept hidden/team forms without changing the stricter privacy flags
required for human messages entering the chat/model worker. Optional key CFGs
use hidden `say` commands; direct console `connect` remains the join method.

The disposable UI assay uses every supported command through native chat methods,
compares production parsers with the old one-byte behavior, rejects malformed
commands, checks privacy guards and enforces bot exclusion. Its assessor rejects
missing, duplicate, prefixed and failed ingress evidence. This establishes native
parser integration; actual human/client command delivery remains a separate test.

Opening a native HUD now acquires one per-player gameplay focus token. A bounded
poll reads existing game actions while normal controls are frozen; it does not
replace bindings, create a desktop window or add invulnerability. Held opening
inputs must be released before navigation, only navigation repeats, and saves
remain edge-triggered. The same destruction path releases focus on close,
damage, lifecycle changes, timeout and disable. Native prematch, migration,
death and round-end freezes retain authority. Native tests exercise all seven
button reads while frozen, both mappings, exclusive ownership and repeated
cleanup. Actual human binding/keyboard/controller behavior remains a client gate.

The optional browser portal follows only new anonymous native match snapshots,
then exports allowlisted aggregates through a separate offline process. HTTP
regressions cover stale data, route restrictions and private-field exclusion.
Native probes validate emitted snapshots; browser layout/navigation and actual
remote-device access remain distinct checks. See [portal methodology](PORTAL.md).
