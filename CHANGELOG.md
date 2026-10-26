# Changelog

## Unreleased — custom AI profiles and Windows setup

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
