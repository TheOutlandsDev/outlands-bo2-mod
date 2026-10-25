# Client launcher. Arguments are parsed literally, never evaluated as code.
$clientArguments = @($args)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'windows_client.ps1')
$project = Split-Path -Parent $PSScriptRoot
try {
    $settings = Read-OutlandsSettings (Join-Path $project 'runtime\client.json')
    $game = if ($env:OUTLANDS_GAME_DIR) { $env:OUTLANDS_GAME_DIR } elseif ($settings.game_dir) { $settings.game_dir } else { Split-Path -Parent $project }
    $plutonium = if ($env:OUTLANDS_PLUTONIUM_DIR) { $env:OUTLANDS_PLUTONIUM_DIR } elseif ($settings.plutonium_dir) { $settings.plutonium_dir } else { Join-Path $env:LOCALAPPDATA 'Plutonium' }
    $port = if ($env:OUTLANDS_CLIENT_PORT) { $env:OUTLANDS_CLIENT_PORT } elseif ($settings.client_port) { $settings.client_port } else { 4976 }
    $join = $false; $check = $false; $gameArgument = $false
    foreach ($argument in $clientArguments) {
        switch -Exact ($argument.ToLowerInvariant()) {
            { $_ -in '--help', '-h' } {
                Write-Output 'Usage: play-lan-windows.cmd [--join] [--check] ["BO2_GAME_DIRECTORY"]'
                Write-Output 'Setup saves game/runtime paths and port. OUTLANDS_GAME_DIR, OUTLANDS_PLUTONIUM_DIR and OUTLANDS_CLIENT_PORT override saved values.'
                Write-Output 'Name priority: OUTLANDS_PLAYER_NAME, then active storage\t6\outlands_player_name.txt. Each player needs a unique stable name for progression.'
                Write-Output '--join executes the private outlands_join.cfg. --check performs no writes or game launch.'
                exit 0
            }
            '--join' { $join = $true }
            '--check' { $check = $true }
            default {
                if ($gameArgument -or $argument.StartsWith('--')) { throw 'Supply at most one quoted game folder. Run with --help for usage.' }
                $game = $argument; $gameArgument = $true
            }
        }
    }
    $game = Test-OutlandsGame $game
    $plutonium = Test-OutlandsRuntime $plutonium
    $port = Test-OutlandsPort $port
    $nameFile = Join-Path $plutonium 'storage\t6\outlands_player_name.txt'
    $name = if ($env:OUTLANDS_PLAYER_NAME) { Test-OutlandsName $env:OUTLANDS_PLAYER_NAME } else { Read-OutlandsName $nameFile }
    if ($join) { Test-OutlandsJoin (Join-Path $plutonium 'storage\t6\outlands_join.cfg') }
    if ($check) { Write-Output 'LAN client prerequisites passed. No files changed or game process started.'; exit 0 }
    Write-OutlandsFile $nameFile ([Text.Encoding]::ASCII.GetBytes($name + [char]10))
    $native = @('t6mp', ($game.TrimEnd('\') + '\.'), '+name', $name, '-lan', '+set', 'net_port', "$port")
    if ($join) { $native += @('+exec', 'outlands_join.cfg') }
    Push-Location -LiteralPath $plutonium
    try { & (Join-Path $plutonium 'bin\plutonium-bootstrapper-win32.exe') @native; $result = $LASTEXITCODE }
    finally { Pop-Location }
    exit $result
} catch {
    [Console]::Error.WriteLine('Outlands LAN: ' + $_.Exception.Message)
    exit 1
}
