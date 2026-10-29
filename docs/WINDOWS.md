# Windows client setup and validation

Use this procedure with an owned BO2 multiplayer installation, the official
Plutonium runtime and authorized Tailscale access to the hosting peer. The
commands use example paths and player names; enter connection details locally.

## Video guide

[Watch the beginner guide: setup files, joining and Linux hosting](https://youtu.be/DYRYgX5y2HM)
(10 minutes). It shows Windows file locations, ZIP extraction, profile backup and
illustrated setup, joining and hosting commands. Applied client setup, a live
Linux deployment and a successful game join are separate validation stages.
The recording uses source revision `2ab198fdb40898c0a88e2743115999958a8dbcbd`;
follow the current written instructions when your source differs.

## Identify and check the inputs

Confirm the exact owned game directory and the runtime that contains the active
profile. An automation terminal can redirect `LOCALAPPDATA`; supply the actual
runtime directory with `--plutonium-dir` instead of assuming that environment
variable identifies the installation you use.

The game check requires `t6mp.exe`, `zone/all/code_pre_gfx_mp.ff` and
`zone/all/common_mp.ff`. The runtime check requires
`bin/plutonium-bootstrapper-win32.exe` and `games/t6mp.exe`. File presence does
not verify the runtime revision or replace the official updater.

Compare the downloaded source ZIP's SHA-256 with its published release digest.
Then open PowerShell in the extracted source directory and check the inputs:

```powershell
.\setup-client-windows.cmd --dry-run --skip-updater --game-dir "D:\Games\Black Ops II" --plutonium-dir "D:\Tools\Plutonium" --name "Player One"
```

This command performs no downloads, prompts, writes or game launch. Use a
unique player name and keep it stable across launches: LAN identity and earned
progression depend on it.

## Preserve the profile before setup or a playtest

Close BO2 normally. Back up the active runtime's entire `storage` directory,
including both T6 configuration and any active stat storage. A backup of only
`storage/t6` can omit profiles stored elsewhere under `storage`.

This example creates a new backup outside the source checkout and verifies
every copied file. Replace the runtime path before running it. Reparse points
are rejected so the copy stays within the selected source tree.

```powershell
$runtimeDir = "D:\Tools\Plutonium"
$storageSource = Join-Path $runtimeDir 'storage'
$storageSource = [IO.Path]::GetFullPath($storageSource).TrimEnd('\')
$backupParent = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'BO2 profile backups'
$backupRoot = Join-Path $backupParent ([Guid]::NewGuid().ToString('N'))
if ([IO.Path]::GetFullPath($backupRoot).StartsWith($storageSource + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Choose a backup destination outside the source storage tree.'
}
$items = @(Get-Item -LiteralPath $storageSource -ErrorAction Stop) +
    @(Get-ChildItem -LiteralPath $storageSource -Recurse -Force -ErrorAction Stop)
if (@($items | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) {
    throw 'Select a profile tree without reparse points.'
}
$null = New-Item -ItemType Directory -Path $backupParent -Force -ErrorAction Stop
$null = New-Item -ItemType Directory -Path $backupRoot -ErrorAction Stop
$backupStorage = Join-Path $backupRoot 'storage'
Copy-Item -LiteralPath $storageSource -Destination $backupStorage -Recurse -Force -ErrorAction Stop
$manifest = @(foreach ($item in $items | Where-Object { -not $_.PSIsContainer }) {
    $relative = $item.FullName.Substring($storageSource.Length + 1)
    $sourceHash = (Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash
    $copiedHash = (Get-FileHash -LiteralPath (Join-Path $backupStorage $relative) -Algorithm SHA256).Hash
    if ($sourceHash -ne $copiedHash) { throw 'Backup verification failed; keep the source intact.' }
    [pscustomobject]@{ Path = $relative; Length = $item.Length; SHA256 = $sourceHash }
})
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $backupRoot 'SHA256-MANIFEST.json') -Encoding UTF8
```

Keep this backup and manifest private. A backup does not establish gameplay or
progression acceptance, and setup does not reset or copy player stats.

## Configure the connection

For a password-protected host, import its private invite:

```powershell
.\setup-client-windows.cmd --skip-updater --invite "D:\Private\outlands.invite.json" --game-dir "D:\Games\Black Ops II" --plutonium-dir "D:\Tools\Plutonium" --name "Player One"
```

For a host deliberately configured without a game password, use the explicit
Windows option:

```powershell
.\setup-client-windows.cmd --skip-updater --no-password --game-dir "D:\Games\Black Ops II" --plutonium-dir "D:\Tools\Plutonium" --name "Player One"
```

Setup prompts locally for the private server address. No password is requested
in this mode. `--no-password` cannot be combined with `--invite`; protected
invites still require their nonempty password. Existing releases that do not
recognize this option can use the direct LAN/console fallback below.

The client writes exactly two commands to its private `outlands_join.cfg`:
`password ""` followed by `connect` with the locally supplied address. Clearing
the password prevents an old saved value from being sent. This only changes
client settings; server configuration and Tailscale authorization are separate.

## Check, launch and direct joining

```powershell
.\setup-client-windows.cmd --check
.\play-outlands-windows.cmd
```

The check validates saved settings without launching a game. The launcher uses
the configured runtime, stable name, LAN mode and client port, then executes the
optional private join CFG. This file shortcut has separate runtime/search-path
requirements. Use direct `connect` below as the canonical join method, including
when a wrapper launches BO2 but does not join. Neither source nor examples embed a real host
address, personal identity or credential.

If using an older release without the explicit option, launch the existing
runtime directly with your owned game folder and stable name:

```powershell
$gameDir = "D:\Games\Black Ops II"
$runtimeDir = "D:\Tools\Plutonium"
$playerName = "Player One"
Push-Location -LiteralPath $runtimeDir
try {
    & '.\bin\plutonium-bootstrapper-win32.exe' t6mp "$gameDir\." +name $playerName -lan +set net_port 4976
} finally {
    Pop-Location
}
```

Open the game console with `~` and enter these commands separately. Substitute
the host's privately supplied address and port for the placeholder:

```text
password ""
connect SERVER_ADDRESS:SERVER_PORT
```

After spawning, Outlands commands go in text chat (`!outlands help`) or use
`say !outlands help` in the game console. See the [command reference](COMMANDS.md).

## Validate each stage separately

1. Confirm Tailscale authorization and a reply from the intended hosting peer.
   A relay reply establishes peer reachability, not a direct path or game join.
2. Complete map negotiation, choose a team/class and spawn. An unanswered UDP
   query or `PLATFORM_DISCONNECTED_FROM_SERVER` does not establish its cause.
3. Verify native bot population, team assignment and combat. Complete a match
   and compare the after-action rank and weapon results.
4. Quit normally, restart the client, rejoin with the same name and compare the
   saved results. Test server restart retention separately.

Use [the acceptance matrix](VALIDATION.md) for the remaining checks. Record
pass/fail outcomes without publishing screenshots of personal profiles, raw
chat, account IDs, addresses, device inventories or logs.

## Publish only reusable source

Keep runtime settings, connection CFGs, invites, backups and manifests outside
the public source. Use the explicit source allowlist rather than uploading a
game directory or selecting every local file:

```powershell
python -B tools/build_release.py
```

Run the synthetic Windows tests and the release checks before publishing code.
The public method describes inputs, operations and acceptance criteria;
conversation transcripts, session timestamps and personal environment details
are excluded.
