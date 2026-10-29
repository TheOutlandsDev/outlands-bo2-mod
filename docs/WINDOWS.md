# Windows client setup and validation

Use this procedure with an owned BO2 multiplayer installation, the official
Plutonium runtime and authorized Tailscale access to the hosting peer. The
commands use example paths and player names; enter connection details locally.

## Video guide

For a same-PC bot trial, see [local Windows play and its matching commands](#try-the-core-bots-on-one-windows-pc).

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

## Try the core bots on one Windows PC

[Watch: Try the Mod Locally on Windows - Developer vs AI Bots](https://youtu.be/4iWX_50ocBE)
(4 minutes). The recorded trial demonstrates a local map load, player spawn,
native bot population adjustment, and disconnect/rejoin. It uses source
revision `2ab198fdb40898c0a88e2743115999958a8dbcbd`. Saved progression, optional
external workers and connections from another computer were not validated by
this trial. The narration is AI-generated from the developer's own voice.

The core fill controller requires a **dedicated server**, including for this
same-PC trial. Starting only a normal Custom Game does not start that controller.
This procedure is for local play; friends hosting has separate requirements.

### Install the source files

Use an owned BO2 multiplayer installation and an installed, updated official
Plutonium runtime. Install Python 3 if needed. Close the game and preserve the
complete active `storage` directory using the backup procedure above. Review
other installed bot controllers before combining mods.

Open PowerShell in the extracted Outlands source folder. Replace the example
runtime path with the active installation you actually use. Preview, then apply:

```powershell
py -3 tools/install_files.py --plutonium-dir "D:\Tools\Plutonium"
py -3 tools/install_files.py --plutonium-dir "D:\Tools\Plutonium" --apply
```

The installer stops when an existing source file differs. Review that conflict
before replacing files. An existing `outlands_t6.cfg` is retained; check its
settings, including `outlands_native_bots 1`, rather than assuming defaults
were reapplied.

### Save a separate local configuration

In Notepad, save the following as `outlands_local_trial.cfg` in the active
runtime's `storage\t6` folder, for example
`D:\Tools\Plutonium\storage\t6\outlands_local_trial.cfg`. Select **All files**
and **UTF-8**. Enable file name extensions in Explorer and check that the name
does not end in `.cfg.txt`.

```text
exec outlands_t6.cfg
set net_ip "127.0.0.1"
set net_port 14977
g_password ""
sv_hostname "OUTLANDS | Local Tutorial Trial"
set sv_voice 0
set outlands_rotation 0
set outlands_bot_fill 8
set outlands_bot_idle_fill 8
set outlands_chat_enabled 0
set outlands_bot_careers 0
set g_log "outlands_local_trial_games.log"
sv_maprotation "gametype tdm execgts outlands_tdm.cfg map mp_raid"
```

The loopback address `127.0.0.1` points to this computer. Keep it for this trial;
the empty game password is intentional only for this loopback example. No
router port forwarding is needed for this same-PC connection. The target is
eight players **total**, including humans and bots, not eight additional bots.

### Start the client, then the server

In **PowerShell window 1**, use your own game/runtime paths and a stable local
player name. Start the client first and wait for its menu:

```powershell
$game = "D:\Games\Black Ops II"
$runtime = "D:\Tools\Plutonium"
$exe = "$runtime\bin\plutonium-bootstrapper-win32.exe"
$launch = 't6mp "' + $game + '\." '
$launch += '+name "PlayerOne" -lan +set fs_game "" +set net_port 14976'
Start-Process $exe -ArgumentList $launch -WorkingDirectory $runtime
```

In **PowerShell window 2**, start the local dedicated server. Keep this window
open so its `$server` variable is available when finishing:

```powershell
$game = "D:\Games\Black Ops II"
$runtime = "D:\Tools\Plutonium"
$exe = "$runtime\bin\plutonium-bootstrapper-win32.exe"
$launch = 't6mp "' + $game + '\." -dedicated -lan '
$launch += '+set fs_game "" +set net_ip 127.0.0.1 +set net_port 14977 '
$launch += '+set logfile 2 +exec outlands_local_trial.cfg +map_rotate'
$server = Start-Process $exe -ArgumentList $launch -WorkingDirectory $runtime `
  -WindowStyle Hidden -PassThru
```

These literal argument strings preserve the empty `fs_game ""` value in
Windows PowerShell 5.1. The client uses port `14976`; the server uses `14977`.
See the [official same-PC server notes](https://plutonium.pw/docs/server/t6/setting-up-a-server/)
for the client-first order and distinct-port requirement.

### Join and check the session

Open the in-game console (`~`; keyboard layouts differ). Enter separately:

```text
password ""
connect 127.0.0.1:14977
```

Wait for Raid, choose a class and spawn. Check bot population, teams and combat.
The recorded trial reached one human plus seven native bots, with four players
per team, and adjusted population after disconnect/rejoin. A menu or a running
server process alone does not establish a successful join.

Quit the client normally. Then, in window 2, stop only the server launched here:

```powershell
Stop-Process -Id $server.Id
```

Saved progression requires its own acceptance check: finish a match, quit
normally, rejoin with the same name and compare rank/weapon results. Do not
treat the successful local connection as proof of persistence or remote hosting.


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
