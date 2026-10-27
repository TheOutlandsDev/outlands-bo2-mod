# Changelog

## Unreleased — cooperative lobbies, grounded task chat, squads, contracts and rivals

- Repair Outlands command parsing for native two-byte chat prefixes across
  Career, Contracts, Operations and Armory. Normalize case/spacing and hidden
  forms, give private readiness feedback and identity-free command results, and
  use hidden `say` commands in optional key CFGs. Keep human chat/model privacy
  checks strict. Require nineteen real native all/team chat events in UI backend
  acceptance. Document direct `connect` as the canonical joining method with
  deployment details kept private; real human input/rendering remains a client gate.

- Add a 31-map multiplayer catalog and weighted installed-map decks, independent
  mode weights, recent-map protection and private restart history. Hand off the
  next native rotation through a map-scoped mailbox; retain static fallback and
  exclude unavailable DLC. Preserve private operator weights. Add an isolated
  native map-load, normal match-end and restart assay.
- Allow configurable native idle matches and bounded bot conversation with or
  without humans. Verify production filling, worker transport and native speech
  ACKs rather than direct speech fixtures. Preserve human-reply priority, context
  validation, turn limits, native stats and all shared rate limits.

- Add an opt-in native Armory base-class editor with earned item/CAC checks,
  localized native labels and complete compound-perk effects. Connect single-slot
  persistence through a separate model-independent worker thread and fixed local
  mailbox. Claim before native spawning, grant in the native custom-loadout hook,
  verify actual equipment, retain an active class across lives and cancel stale
  or superseded requests. Preserve native class DDL, unlocks, XP and streaks.
  Keep advanced attachments/wildcards/equipment in stock CAC and real client
  input/progression acceptance separate from synthetic and native bot checks.

- Add the single-slot Armory backend with trusted unlock observations, a bounded
  Pick-10 subset, attachment combinations, wildcard/slot checks, private atomic
  revisioned saves and an at-most-once next-spawn claim queue. Revalidate unlocks
  at claim time and preserve the previous slot on rejected or failed saves.
  Add portable rule tests and a disposable native class-reference spawn probe.
  The broader attachment/wildcard schema remains a backend library; the native
  editor below exposes only its separately tested base-class subset.

- Add an opt-in native Career/Contracts HUD using acknowledged personal careers
  and fresh current-team task counters. Share the guarded focus queue with chat,
  hide unavailable values, use numeric HUD counters, and bound overlay lifetime
  and cleanup. Supply optional F6-F9 bindings without executing them on install.
  Add disposable native presenter/allocation/cleanup probes; real Windows/Linux
  rendering and input remain separate client acceptance gates.

- Add one offline validation command with private logs, a source-bound summary,
  timeout/failure handling and explicit pending UI/client gates. Configure both
  CI platforms to retain sanitized summaries and define graphical menu/loadout
  acceptance before those features are implemented.

- Add optional persistent Outlands milestone careers, three contribution tracks,
  a first Broken Signal commendation and focus/view chat commands. Keep native
  human progression separate and protect private state with salted identities,
  atomic writes and observation replay checks.
- Extend chat with numbered two-to-four-line exchanges, verified contract-completion
  opportunities and natural acknowledgements without repeated task nouns. Retain
  human priority, shared budgets, state expiry and bot-only native speech.
- Feature Signal Four as recurring bot characters while preserving native class
  roles and objective squads. Add synthetic persistence/dialogue tests and isolated
  native milestone-helper/bot-exclusion checks. Real-client acceptance remains
  separate from backend evidence.


- Double ambient conversation frequency with a shared six-line-per-minute cap,
  shorter answer delay and per-bot cooldown. General replies and fallbacks react
  to the previous message and fresh own-scoreboard context; human input keeps
  priority and task grounding remains independent. Own-scoreboard context now
  expires after sixty seconds without a fresh native sample.

- Slightly stagger bot response to UAVs and other air support: a bounded initial
  delay and stable per-target 80 percent participation, preserving native ignore,
  launcher, lock-on and damage rules. Add tuning and stock-selection overrides.

- Keep human joins together up to team capacity through native team menus.
  Balance teams using bot-only removals and native refill, including mid-match
  departures and full uneven lobbies; reserve spectator slots and retain FFA.
- Add isolated native departure/refill, imbalance repair and off/resume checks,
  plus count-only party capacity checks. Actual human joins remain a separate
  client acceptance step; no fake human presence is used by verification.

- Ground occasional squad/order, objective and contract banter in each selected
  bot's current native task, with short model replies and matching fallbacks.
- Keep second turns on the same team, reject changed or expired task context,
  preserve shared chat limits and add an independent task-context off switch.
- Verify typed native snapshots, zero-human refusal and the speech primitive
  separately; benchmark local model output without posting it to a game.

- Add optional coordinated native-bot objective squads and rotating team match
  contracts, with independent off switches and preserved host configuration.
- Track contract goals from real native counters, awarding match-local Outlands
  commendations without changing human XP, unlocks or saved progression.
- Extend isolated native verification with squad goal acknowledgements,
  contract completion, off-switch, unsupported-mode and restart checks.

- Add private, roster-only persistent bot careers with idempotent native-score
  snapshots, guarded cosmetic restores and independent chat/career switches.
- Enrich all fictional bot personalities with stable traits, fresh own-scoreboard
  context and bot-only familiarity confirmed by native speech acknowledgements.
- Add an isolated native-bot verification runner with match, round-restart,
  worker-restart and server-process-restart checks; no human fixture is fabricated.
- Add metadata-only owned-content inventory, DLC/mode boundaries and strict source
  rotation preflight; no commercial assets are distributed.

- Add explicit Windows `--no-password` setup and reusable join-CFG generation.
  Protected invites still require a nonempty password; conflicting modes and
  command injection are rejected. The existing launcher accepts the deliberately
  empty-password CFG without changing a player's saved identity or stats.
- Provide a reusable Windows guide covering explicit runtime paths, full-storage
  backup/hash verification, preflight, joining and progression acceptance.
- Replace dated workstation/session notes and personal progression values with
  a project acceptance matrix and repeatable methodology.
- Extend the source privacy audit to reject Windows user paths, default PC names
  and private tailnet DNS names. Keep profile storage, backups and runtime logs
  outside Git and the explicit release allowlist.

- Add 48 fictional gamertags and matching individual chat personalities.
- Add weighted bot display levels and random cosmetic prestiges, stable across
  respawns and guarded by native display limits; human progression is unchanged.
- Select coherent native class pools for rusher, assault, objective, support and
  marksman roles, with a bounded marksman count and native anti-air fallback.
- Vary native low-priority patrol timing per role while retaining the stock
  pathfinding, objective, combat and recovery brain.
- Add bounded two-line public bot conversations, human-reply priority,
  independent dialogue switches and shared cooldown/minute limits.
- Document the architecture, validation procedure and public-source boundaries
  without personal session records or private deployment details.
- Correct backup guidance to preserve the complete client storage directory,
  including native progression under storage/demonware.

These are working-source changes. The v0.1.2 tag and distributed archives remain
unchanged. New native display, movement and conversation behavior needs a human
playtest in addition to the automated and isolated engine checks.

## 0.1.2 — Development preview

- Document Windows setup/preflight, full profile backups and direct LAN joining.

This update expands native bot sessions and keeps filling active after transient
spawn failures.

- Native difficulty is now Hard, with 16 player slots and a target of 16 total
  humans plus bots, allowing 8v8 in team modes.
- The controller polls throughout the match to refill vacant connection slots.
  After three failed native adds it retries in batches with 10-, 20- and then
  at most 30-second cooldowns. Two-second polling continues during cooldown,
  and human-count or target changes reset the retry sequence. Dead players
  retain their slots and use native respawning.
- Rotation covers the 15 multiplayer maps installed for the host baseline:
  14 base maps plus Nuketown 2025. Clients need their owned files for each
  selected map; separately released DLC maps are not included.
- Eight modes have individual wrappers that reset native defaults before
  applying their settings: Team Deathmatch, Free-for-All, Kill Confirmed,
  Capture the Flag, Demolition, Domination, Headquarters and Hardpoint.
- Time and score targets are doubled from the previous baseline:

| Mode | Time limit (minutes) | Score limit |
| --- | ---: | ---: |
| Team Deathmatch (`tdm`) | 20 | 200 |
| Free-for-All (`dm`) | 20 | 60 |
| Kill Confirmed (`conf`) | 20 | 150 |
| Capture the Flag (`ctf`) | 10 | 6 |
| Demolition (`dem`) | 5 | 4 |
| Domination (`dom`) | 10 | 200 |
| Headquarters (`hq`) | 30 | 500 |
| Hardpoint (`koth`) | 20 | 500 |

Native timer and round rules remain in force. CTF overtime and Demolition
bomb/round rules can end rounds independently of these score caps. Native
movement, combat, loadout validity and earned human progression remain under
the game; this update adds no human XP or unlock writes, persistent bot learning
or bot careers. Use the [validation guide](docs/VALIDATION.md) to test the chosen
rotation and runtime.

## 0.1.1 — Development preview

This update adds automated source checks and release packaging.

- Linux regression checks cover client setup, host state, release packaging,
  chat boundaries/configuration and Bash syntax.
- Windows Server 2022 runs Windows PowerShell 5.1 parsing and synthetic client
  setup dry-run/check tests, without launching BO2.
- Packaging waits for both jobs and produces a deterministic allowlisted source
  ZIP plus `SHA256SUMS`; CI artifacts are retained for 14 days.
- A version-matching `v*` tag, or manual dispatch on an existing matching tag,
  reuses the checks before publishing a new development prerelease.
- Manual release dispatch on `main` runs all checks before creating the matching
  tag at the tested commit and publishing with GitHub's built-in token. A tag
  creation conflict fails without moving the existing tag. Existing releases
  are not overwritten and previews are not marked as latest.
- [Release instructions](docs/RELEASING.md) document versioning, checks, package
  boundaries and the remaining gameplay acceptance work.

## 0.1.0 — Initial source baseline

- Private Plutonium T6 LAN multiplayer over Tailscale, with a contained Wine
  dedicated host and optional Dockhand management.
- Native bot filling, fictional aliases, cosmetic levels, native randomized
  loadouts and optional local Ollama chat.
- Linux and Windows client setup/launch helpers, stable LAN names and private
  schema-version-1 invites.
- Source-only distribution: owned BO2 files, official runtime, model weights,
  credentials, private state and player saves remain separate.

See the [validation guide](docs/VALIDATION.md) for platform and runtime checks.
