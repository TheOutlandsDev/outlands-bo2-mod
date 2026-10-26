# Implementation methodology

Outlands extends native Plutonium T6 LAN multiplayer with original GSC modules,
client setup tools and an optional local chat worker. The design preserves
normal earned human progression and native bot control while adding configurable
population, appearance, class roles and conversation.

## Components and ownership

| Component | Responsibility |
| --- | --- |
| Client setup/launch helpers | Validate owned inputs, save a stable LAN name and private join configuration, launch the official runtime |
| Wine dedicated game container | Run native multiplayer and load original source from `storage/t6` |
| Tailscale sidecar | Provide private network reachability with its own persistent identity |
| `outlands_native_bots.gsc` | Own population filling and bounded recovery |
| `outlands_bot_identity.gsc` | Apply bot-only cosmetic level and prestige display |
| `outlands_bot_profiles.gsc` | Filter native class choices and adjust optional patrol cadence |
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
They do not write DDL XP, change loadout unlock eligibility or create persistent
bot careers. The roster contains fictional aliases and matching chat voices.

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

Ambient conversation has at most an opener and one answer by another bot.
Human public-chat replies take priority and cancel queued followups. Both turns
share global, per-bot and per-minute budgets. Context is short-lived, no chat is
generated without humans, and team/hidden chat is excluded. The worker stores
no chat history; console events can contain public chat, so raw server logs
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
