# Development releases

`VERSION` is the source version. The current version is `0.1.2`; its intended
tag is `v0.1.2`. The configured workflow publishes development prereleases and
does not mark them as the latest release. This document describes configuration
and maintainer steps, not evidence that a particular workflow has passed.

## Configured checks

[`ci.yml`](../.github/workflows/ci.yml) runs on pushes to `main`, pull requests,
manual dispatch and calls from the release workflow.

| Job | Checks |
| --- | --- |
| Linux, Ubuntu 24.04 / Python 3.11 | Setup/hosting/release regression tests, AI boundary tests, chat configuration, allowlisted source audit and Bash syntax |
| Windows Server 2022 / Windows PowerShell 5.1 | Script parsing and synthetic client setup dry-run/check fixtures |
| Package | Waits for both platform jobs, builds the source ZIP and verifies its SHA-256 manifest |

The CI artifact is `outlands-bo2-mod-dev-preview`, retained for 14 days. Its
files are `outlands-bo2-mod-v0.1.2-dev-preview.zip` and `SHA256SUMS`, with the
version taken from `VERSION` for subsequent releases.

Synthetic tests use temporary fixture files, not real BO2 assets or profiles.
They do not launch a game, run a native dedicated server, download a runtime or
model, or establish Tailscale reachability. Passing Windows checks verifies the
tested setup logic. Native GSC, joining, combat, progression retention and visible
presentation need the separate [gameplay validation guide](VALIDATION.md).

## Source package boundaries

`tools/build_release.py` builds from an explicit public-source allowlist. The
ZIP uses stable file ordering, timestamps and modes so identical source and
toolchain inputs produce the same archive. Shell helpers receive executable
archive modes; the documented `bash setup-client-linux.sh` first command also
works when a checkout or extraction lacks executable bits.

Distribute original source, tests, configuration templates and documentation.
Do not include owned game assets, Plutonium/vendor binaries, container images,
downloaded model weights, runtime prefixes, logs, invites, passwords, tokens,
server volumes or player saves. A checksum verifies downloaded bytes; it does
not establish gameplay compatibility or replace review of package contents.

The source audit rejects private tailnet addresses/DNS names, user-specific
Linux and Windows home paths, and default Windows PC names. The public Windows
guide uses generic examples and keeps personal activity, profile values and
conversation metadata out of its instructions and acceptance matrix.

To audit the public source locally without packaging:

```sh
python3 -B tools/build_release.py
```

To create a fresh versioned preview and verify it:

```sh
python3 -B tools/build_release.py --output dist/outlands-bo2-mod-v0.1.2-dev-preview.zip
(cd dist && sha256sum --check SHA256SUMS)
```

Use a new output path; existing release files are not silently overwritten.
These commands prepare source artifacts only and do not start the host/game.

## Publish a preview

1. Update `VERSION`, `CHANGELOG.md` and relevant technical documentation. Use a
   new version for changed release contents; preserve already-distributed tags.
2. Put the intended source on `main` through the normal review process. Inspect
   the actual Linux and Windows job results and the packaged file list.
3. Open the **Publish dev preview** workflow in GitHub Actions, choose **Run
   workflow** and select `main`. The workflow validates `VERSION` and runs the
   shared checks. Only after they pass does the publishing job create
   `v0.1.2` at the tested `GITHUB_SHA` and publish. No local GitHub credential is
   needed; the job uses GitHub's built-in workflow token.
4. Alternatively, create and push an exact version-matching tag or manually
   dispatch on an existing matching tag. The tag name must be `v` followed by
   `VERSION`. [`release.yml`](../.github/workflows/release.yml) verifies it and
   reruns the shared checks before publication. Both paths attach the versioned
   ZIP and `SHA256SUMS`, use `CHANGELOG.md` as release notes, and mark the release
   as a prerelease rather than latest.
5. Download the published files, verify the checksum from their containing
   directory, and check that the source archive contains the intended version.

Manual release dispatch accepts `main` or an existing matching tag. Other
branches and mismatched tags are rejected. The publishing job alone receives
repository-content write permission; test jobs use read access.

Tag creation conflicts fail without moving the existing tag. If a failure
leaves the matching tag created but no release published, dispatch again on
that existing tag rather than `main`. Release reruns refuse to overwrite an
existing release. Publish a corrected version/tag instead of replacing
already-distributed preview assets. Confirm the actual Actions run and release
page before saying publication succeeded.
