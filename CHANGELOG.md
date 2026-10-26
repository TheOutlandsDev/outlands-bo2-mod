# Changelog

## 0.1.2 — Development preview

- Preserve the Windows setup/preflight, profile backup and direct LAN joining
  guidance added after v0.1.1, with subsequent successful joining/bot-combat
  results separated from the pending Windows progression restart check.

This update expands native bot sessions and keeps filling active after transient
spawn failures. These are implemented settings and controller changes; full
gameplay acceptance across the expanded rotation remains pending.

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
or bot careers. Live Raid / Domination checks verified 8v8 assignment,
16 → 15 → 16 mid-match refill, Windows staying connected, and a second human
replacing a bot. Full rotation, all-mode gameplay and prolonged failed-add
recovery still need live acceptance. Earlier baseline results remain documented in
[validation status](docs/VALIDATION.md).

## 0.1.1 — Development preview

This update adds automated source checks and release packaging. The configured
workflow must pass before publishing; this changelog does not assert a completed
CI run or release.

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

The existing Linux native-bot/progression/chat acceptance record is preserved.
Windows gameplay remains untested. This update does not claim new runtime
gameplay, MW2 feature parity, additional unlock checks or bot learning behavior.

## 0.1.0 — Initial source baseline

- Private Plutonium T6 LAN multiplayer over Tailscale, with a contained Wine
  dedicated host and optional Dockhand management.
- Native bot filling, fictional aliases, cosmetic levels, native randomized
  loadouts and optional local Ollama chat.
- Linux and Windows client setup/launch helpers, stable LAN names and private
  schema-version-1 invites.
- Source-only distribution: owned BO2 files, official runtime, model weights,
  credentials, private state and player saves remain separate.

See [validation status](docs/VALIDATION.md) for the evidence and limits of this
baseline rather than treating a source release as platform-wide acceptance.
