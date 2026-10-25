# Changelog

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
  reuses the checks before publishing a new development prerelease. Existing
  releases are not overwritten and previews are not marked as latest.
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
