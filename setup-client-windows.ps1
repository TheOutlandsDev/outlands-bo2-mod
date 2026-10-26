# Client setup only. No BO2 assets or existing player stats are copied/reset.
$clientArguments = @($args)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'tools\windows_client.ps1')
$project = $PSScriptRoot

function Ask-OutlandsYes([string]$Prompt, [bool]$Default) {
    while ($true) {
        $suffix = if ($Default) { ' [Y/n]' } else { ' [y/N]' }
        $answer = (Read-Host ($Prompt + $suffix)).ToLowerInvariant()
        if ($answer -eq '') { return $Default }
        if ($answer -in @('y','yes')) { return $true }
        if ($answer -in @('n','no')) { return $false }
        Write-Host 'Enter yes or no.'
    }
}
function Ask-OutlandsValue([string]$Prompt, $Default, [scriptblock]$Validator, [bool]$Hidden = $false) {
    while ($true) {
        $suffix = if ($null -ne $Default) { ' [Enter to keep saved value]' } else { '' }
        $value = if ($Hidden) { Read-OutlandsHidden ($Prompt + $suffix) } else { Read-Host ($Prompt + $suffix) }
        if ($value -eq '' -and $null -ne $Default) { $value = $Default }
        try { return & $Validator $value }
        catch { [Console]::Error.WriteLine($_.Exception.Message) }
    }
}
try {
    $check = $false; $dry = $false; $skipUpdater = $false; $shortcut = $false; $noPassword = $false; $options = @{}
    for ($index = 0; $index -lt $clientArguments.Count; $index++) {
        $option = $clientArguments[$index].ToLowerInvariant()
        switch -Exact ($option) {
            { $_ -in '--help', '-h', '-help' } {
                Write-Output 'Usage: setup-client-windows.cmd [--check | --dry-run] [options]'
                Write-Output 'Interactive setup downloads/opens the official updater and collects private connection details using hidden terminal prompts.'
                Write-Output '--invite PATH imports private JSON: schema_version 1, server_address (IPv4/DNS without port), server_port, join_password.'
                Write-Output 'Options: --game-dir PATH, --name NAME, --plutonium-dir PATH, --port PORT, --skip-updater, --desktop-shortcut.'
                Write-Output '--no-password explicitly saves an empty game password for a host configured without one; cannot combine with --invite.'
                Write-Output '--dry-run validates install inputs; --check validates an installed client. Neither writes, downloads, prompts or launches.'
                Write-Output 'Each player needs owned BO2 files and a unique stable LAN name. Close the game before setup. Existing stats are preserved.'
                Write-Output 'Install/sign in to Tailscale separately: https://tailscale.com/download/windows . No system service is changed.'
                exit 0
            }
            { $_ -in '--check', '-check' } { $check = $true }
            { $_ -in '--dry-run', '-dryrun' } { $dry = $true }
            { $_ -in '--skip-updater', '-skipupdater' } { $skipUpdater = $true }
            { $_ -in '--desktop-shortcut', '-desktopshortcut' } { $shortcut = $true }
            '--no-password' { $noPassword = $true }
            { $_ -in '--game-dir', '--name', '--plutonium-dir', '--port', '--invite' } {
                $index++
                if ($index -ge $clientArguments.Count -or $clientArguments[$index] -eq '') { throw 'An option is missing its value. Run with --help.' }
                $options[$option] = $clientArguments[$index]
            }
            default { throw 'Unknown setup option. Run with --help.' }
        }
    }
    if ($check -and $dry) { throw 'Choose either --check or --dry-run.' }
    if ($noPassword -and $options.ContainsKey('--invite')) { throw 'Choose either --invite or --no-password.' }
    $settingsFile = Join-Path $project 'runtime\client.json'
    $settings = Read-OutlandsSettings $settingsFile
    $game = if ($options.ContainsKey('--game-dir')) { $options['--game-dir'] } elseif ($env:OUTLANDS_GAME_DIR) { $env:OUTLANDS_GAME_DIR } elseif ($settings.game_dir) { $settings.game_dir } else { Join-Path ${env:ProgramFiles(x86)} 'Steam\steamapps\common\Call of Duty Black Ops II' }
    $plutonium = if ($options.ContainsKey('--plutonium-dir')) { $options['--plutonium-dir'] } elseif ($env:OUTLANDS_PLUTONIUM_DIR) { $env:OUTLANDS_PLUTONIUM_DIR } elseif ($settings.plutonium_dir) { $settings.plutonium_dir } else { Join-Path $env:LOCALAPPDATA 'Plutonium' }
    $plutonium = Resolve-OutlandsPath $plutonium
    $storage = Join-Path $plutonium 'storage\t6'; $nameFile = Join-Path $storage 'outlands_player_name.txt'
    $name = if ($options.ContainsKey('--name')) { $options['--name'] } elseif ($env:OUTLANDS_PLAYER_NAME) { $env:OUTLANDS_PLAYER_NAME } elseif (Test-Path -LiteralPath $nameFile) { Read-OutlandsName $nameFile } else { $null }
    $port = if ($options.ContainsKey('--port')) { $options['--port'] } elseif ($env:OUTLANDS_CLIENT_PORT) { $env:OUTLANDS_CLIENT_PORT } elseif ($settings.client_port) { $settings.client_port } else { 4976 }
    $port = Test-OutlandsPort $port
    $invite = if ($options.ContainsKey('--invite')) { Read-OutlandsInvite (Resolve-OutlandsPath $options['--invite']) } else { $null }
    $tailscale = Get-Command tailscale.exe -ErrorAction SilentlyContinue
    if (-not $tailscale -and [IO.File]::Exists((Join-Path $env:ProgramFiles 'Tailscale\tailscale.exe'))) { $tailscale = $true }
    if ($check -or $dry) {
        $game = Test-OutlandsGame $game
        if ($null -eq $name) { throw 'Provide --name NAME for a first-install dry run, or save a stable name through setup.' }
        $null = Test-OutlandsName $name
        if ($check -or $skipUpdater) { $plutonium = Test-OutlandsRuntime $plutonium }
        if ($check) {
            Test-OutlandsJoin (Join-Path $storage 'outlands_join.cfg')
            if (-not $tailscale) { throw 'Tailscale is missing. Install it and sign in before joining.' }
            Write-Output 'Client files, saved identity and private join CFG passed checks. Network reachability and gameplay were not tested.'
        } else {
            Write-Output 'Install inputs passed. Apply would download/open the official updater unless --skip-updater is set, then collect or import private join details.'
            Write-Output 'Only local client settings, the name file, join CFG and optional shortcut are written. BO2 files and existing stats are preserved.'
            if (-not $tailscale) { Write-Output 'Install/sign in to Tailscale separately: https://tailscale.com/download/windows' }
        }
        exit 0
    }
    if ([Console]::IsInputRedirected) { throw 'Interactive setup requires a terminal. Use --check or --dry-run for unattended validation.' }
    Write-Output 'The Outlands BO2 Mod client setup. BO2 assets and existing stats will not be copied or replaced.'
    $game = Ask-OutlandsValue 'Owned BO2 game directory' $game { param($value) Test-OutlandsGame $value }
    $name = Ask-OutlandsValue 'Stable unique LAN player name (keep this for progression)' $name { param($value) Test-OutlandsName $value }
    if (-not $skipUpdater) {
        $updater = Join-Path $project 'runtime\downloads\plutonium.exe'
        $null = [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($updater))
        $temporary = $updater + '.' + [Guid]::NewGuid().ToString('N') + '.download'
        try {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            $progress = $ProgressPreference; $ProgressPreference = 'SilentlyContinue'
            try { $response = Invoke-WebRequest -Uri 'https://cdn.plutonium.pw/updater/plutonium.exe' -OutFile $temporary -UseBasicParsing -PassThru }
            finally { $ProgressPreference = $progress }
            $final = $response.BaseResponse.ResponseUri
            if ($final.Scheme -ne 'https' -or $final.Host -notin @('cdn.plutonium.pw','plutonium.pw')) { throw 'Updater redirected outside official HTTPS hosts.' }
            $bytes = [IO.File]::ReadAllBytes($temporary)
            if ($bytes.Length -lt 1024 -or $bytes.Length -gt 134217728 -or $bytes[0] -ne 77 -or $bytes[1] -ne 90) { throw 'Official updater is not the expected Windows executable.' }
            Write-OutlandsFile $updater $bytes
        } finally { if ([IO.File]::Exists($temporary)) { [IO.File]::Delete($temporary) } }
        if (Ask-OutlandsYes 'Open the official updater now? Let downloads finish, then close the launcher to continue' $true) {
            $start = New-Object Diagnostics.ProcessStartInfo
            $start.FileName = $updater; $start.WorkingDirectory = $project; $start.UseShellExecute = $false
            $start.RedirectStandardOutput = $true; $start.RedirectStandardError = $true
            $process = New-Object Diagnostics.Process; $process.StartInfo = $start
            $null = $process.Start()
            $stdout = $process.StandardOutput.ReadToEndAsync(); $stderr = $process.StandardError.ReadToEndAsync()
            $process.WaitForExit(); $null = $stdout.GetAwaiter().GetResult(); $null = $stderr.GetAwaiter().GetResult(); $process.Dispose()
        }
    }
    $plutonium = Test-OutlandsRuntime $plutonium
    $joinFile = Join-Path $storage 'outlands_join.cfg'
    $replace = $noPassword -or $null -ne $invite -or -not (Test-Path -LiteralPath $joinFile)
    if (-not $replace) { $replace = Ask-OutlandsYes 'Replace existing private connection settings?' $false }
    $joinBytes = $null
    if ($replace) {
        if ($invite) { $address = $invite.address; $password = $invite.password }
        else {
            $address = Ask-OutlandsValue 'Private hosting IPv4 or DNS name, optionally :port (hidden)' $null { param($value) Test-OutlandsAddress $value } $true
            $password = if ($noPassword) { '' } else { Ask-OutlandsValue 'Private server join password (hidden)' $null { param($value) Test-OutlandsPassword $value } $true }
        }
        $joinBytes = [Text.Encoding]::ASCII.GetBytes((New-OutlandsJoinText $address $password -NoPassword:$noPassword))
    } else { Test-OutlandsJoin $joinFile }
    Write-OutlandsFile $nameFile ([Text.Encoding]::ASCII.GetBytes($name + [char]10))
    if ($null -ne $joinBytes) { Write-OutlandsFile $joinFile $joinBytes }
    $publicSettings = @{ game_dir = $game; plutonium_dir = $plutonium; client_port = $port } | ConvertTo-Json
    Write-OutlandsFile $settingsFile ([Text.UTF8Encoding]::new($false).GetBytes($publicSettings + [char]10))
    if ($shortcut -or (Ask-OutlandsYes 'Add a desktop shortcut?' $false)) {
        $shell = New-Object -ComObject WScript.Shell
        $link = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'The Outlands BO2 Mod.lnk'))
        $link.TargetPath = Join-Path $project 'play-outlands-windows.cmd'; $link.WorkingDirectory = $project
        $link.Description = 'Join the privately configured Outlands BO2 server in LAN mode.'; $link.Save()
    }
    Write-Output 'Client setup saved. Run play-outlands-windows.cmd to join, or setup-client-windows.cmd --check first.'
    Write-Output 'Keep runtime\client.json and invite files private. Changing your LAN name selects a different profile.'
    if (-not $tailscale) { Write-Output 'Install/sign in to Tailscale before joining: https://tailscale.com/download/windows' }
    exit 0
} catch {
    $message = if ($_.Exception -is [Management.Automation.RuntimeException]) { $_.Exception.Message } else { 'Setup could not finish; check paths, terminal input and internet access.' }
    [Console]::Error.WriteLine('Outlands client: ' + $message)
    exit 1
}
