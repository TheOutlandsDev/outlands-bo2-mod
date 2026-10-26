# Synthetic Windows client checks. No BO2 assets, network, model or accounts.
# Run: powershell -NoProfile -File tests/test_windows_client.ps1
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Run this test on Windows PowerShell.' }
$repository = Split-Path -Parent $PSScriptRoot
$helper = Join-Path $repository 'tools\windows_client.ps1'
. $helper
$script:passed = 0
$script:failed = 0
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('Outlands Windows tests ' + [Guid]::NewGuid().ToString('N'))
$null = [IO.Directory]::CreateDirectory($temporary)

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}
function Assert-Equal($Actual, $Expected, [string]$Message) {
    if ($Actual -cne $Expected) { throw $Message }
}
function Assert-Throws([scriptblock]$Action, [string]$Message) {
    $caught = $null
    try { $null = & $Action } catch { $caught = $_.Exception.Message }
    if ($null -eq $caught) { throw $Message }
    return $caught
}
function Test-Case([string]$Name, [scriptblock]$Action) {
    try {
        & $Action
        $script:passed++
        Write-Output ('PASS: ' + $Name)
    } catch {
        $script:failed++
        [Console]::Error.WriteLine('FAIL: ' + $Name + ': ' + $_.Exception.Message)
    }
}
function Write-FixtureBytes([string]$Path, [byte[]]$Bytes) {
    $null = [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Path))
    [IO.File]::WriteAllBytes($Path, $Bytes)
}
function Write-FixtureText([string]$Path, [string]$Text) {
    Write-FixtureBytes $Path ([Text.UTF8Encoding]::new($false).GetBytes($Text))
}
function Write-FixtureJson([string]$Path, $Value) {
    Write-FixtureText $Path ($Value | ConvertTo-Json -Depth 8)
}
function Get-FixtureSnapshot([string]$Path) {
    $rows = @(Get-ChildItem -LiteralPath $Path -Recurse -Force | Sort-Object FullName | ForEach-Object {
        $relative = $_.FullName.Substring($Path.Length)
        if ($_.PSIsContainer) { 'directory|' + $relative }
        else {
            $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
            'file|' + $relative + '|' + $_.Length + '|' + $_.LastWriteTimeUtc.Ticks + '|' + $hash
        }
    })
    return $rows -join "`n"
}
function Quote-ChildArgument([string]$Value) {
    # Windows native argument quoting: double backslashes before quotes/end.
    $escaped = [regex]::Replace($Value, '(\\*)"', '$1$1\"')
    $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
    return '"' + $escaped + '"'
}
function Invoke-ClientChild([string]$Target, [string[]]$ClientArguments) {
    $engine = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $arguments = @('-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', $script:driver, $Target) + $ClientArguments
    $start = New-Object Diagnostics.ProcessStartInfo
    $start.FileName = $engine
    $start.Arguments = (@($arguments | ForEach-Object { Quote-ChildArgument $_ }) -join ' ')
    $start.WorkingDirectory = $script:client
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    foreach ($key in @('OUTLANDS_GAME_DIR', 'OUTLANDS_PLUTONIUM_DIR', 'OUTLANDS_PLAYER_NAME', 'OUTLANDS_CLIENT_PORT', 'OUTLANDS_STEAM_DIR', 'OUTLANDS_PROTON')) {
        $start.EnvironmentVariables.Remove($key)
    }
    $start.EnvironmentVariables['PATH'] = $script:fakeBin + ';' + $env:PATH
    $start.EnvironmentVariables['LOCALAPPDATA'] = Join-Path $temporary 'Synthetic local appdata'
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $start
    try {
        $null = $process.Start()
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(30000)) {
            $process.Kill()
            throw 'Client check did not finish within 30 seconds.'
        }
        return @{ code = $process.ExitCode; output = $stdout.GetAwaiter().GetResult(); error = $stderr.GetAwaiter().GetResult() }
    } finally { $process.Dispose() }
}

try {
    Test-Case 'all PowerShell sources parse' {
        $sources = @(Get-ChildItem -LiteralPath $repository -Recurse -File -Filter '*.ps1')
        Assert-True ($sources.Count -ge 4) 'Expected the setup, launcher, helpers and Windows tests.'
        foreach ($source in $sources) {
            $tokens = $null; $errors = $null
            $null = [Management.Automation.Language.Parser]::ParseFile($source.FullName, [ref]$tokens, [ref]$errors)
            Assert-True (@($errors).Count -eq 0) ('PowerShell parser rejected ' + $source.Name)
        }
    }

    Test-Case 'documented backup copies full storage and verifies relative-file hashes' {
        $guide = [IO.File]::ReadAllText((Join-Path $repository 'docs\WINDOWS.md'))
        $blocks = [regex]::Matches($guide, '(?ms)^```powershell\r?\n(.*?)^```')
        foreach ($block in $blocks) {
            $tokens = $null; $errors = $null
            $null = [Management.Automation.Language.Parser]::ParseInput($block.Groups[1].Value, [ref]$tokens, [ref]$errors)
            Assert-Equal @($errors).Count 0 'A documented PowerShell example failed to parse.'
        }
        $fixtureRuntime = Join-Path $temporary 'backup source runtime'
        $fixtureBackups = Join-Path $temporary 'profile backups'
        Write-FixtureText (Join-Path $fixtureRuntime 'storage\t6\players\synthetic.cfg') 'synthetic settings'
        Write-FixtureBytes (Join-Path $fixtureRuntime 'storage\demonware\synthetic-profile\stats') ([byte[]](1,2,3,255))
        $before = Get-FixtureSnapshot $fixtureRuntime
        $sample = @($blocks | Where-Object { $_.Groups[1].Value.Contains('$manifest =') })
        Assert-Equal $sample.Count 1 'Expected exactly one complete backup example.'
        $code = [regex]::Replace($sample[0].Groups[1].Value, '(?m)^\$runtimeDir = .*$', '$runtimeDir = $fixtureRuntime')
        $code = [regex]::Replace($code, '(?m)^\$backupParent = .*$', '$backupParent = $fixtureBackups')
        $backupRoot = & ([scriptblock]::Create($code + "`nWrite-Output `$backupRoot"))
        Assert-Equal (Get-FixtureSnapshot $fixtureRuntime) $before 'The backup example changed source storage.'
        $manifest = [IO.File]::ReadAllText((Join-Path $backupRoot 'SHA256-MANIFEST.json')) | ConvertFrom-Json
        Assert-Equal @($manifest).Count 2 'The backup omitted a T6 or stat-storage file.'
        foreach ($row in $manifest) {
            Assert-True (-not [IO.Path]::IsPathRooted($row.Path)) 'The manifest exposed an absolute source path.'
            $copied = Join-Path (Join-Path $backupRoot 'storage') $row.Path
            Assert-Equal (Get-FileHash -LiteralPath $copied -Algorithm SHA256).Hash $row.SHA256 'A copied file does not match its manifest hash.'
        }
        $fixtureBackups = Join-Path $fixtureRuntime 'storage\nested backup'
        $null = Assert-Throws { & ([scriptblock]::Create($code)) } 'A recursive backup inside source storage was accepted.'
        Assert-Equal (Get-FixtureSnapshot $fixtureRuntime) $before 'Rejected recursive backup changed source storage.'
    }

    $scratch = Join-Path $temporary 'helper fixtures'
    $null = [IO.Directory]::CreateDirectory($scratch)
    $invitePath = Join-Path $scratch 'private invite.json'
    Test-Case 'private invite validation rejects command injection and invalid schema' {
        $valid = @{ schema_version = 1; server_address = 'outlands.example'; server_port = 4977; join_password = 'synthetic-test-password' }
        Write-FixtureJson $invitePath $valid
        $parsed = Read-OutlandsInvite $invitePath
        Assert-Equal $parsed.address 'outlands.example:4977' 'Valid invite address was changed.'
        Assert-Equal $parsed.password 'synthetic-test-password' 'Valid invite password was changed.'
        $cases = @(
            @{ field = 'schema_version'; value = 2 },
            @{ field = 'schema_version'; value = '1' },
            @{ field = 'server_port'; value = 0 },
            @{ field = 'server_port'; value = 65536 },
            @{ field = 'server_port'; value = $true },
            @{ field = 'server_address'; value = 'outlands.example:4977' },
            @{ field = 'server_address'; value = 'outlands.example;quit' },
            @{ field = 'server_address'; value = "outlands.example`nquit" },
            @{ field = 'server_address'; value = 'user@outlands.example' },
            @{ field = 'join_password'; value = 'DO-NOT-ECHO;quit' },
            @{ field = 'join_password'; value = '' },
            @{ field = 'join_password'; value = 'bad"password' },
            @{ field = 'join_password'; value = 'bad\password' },
            @{ field = 'join_password'; value = 'bad//password' },
            @{ field = 'join_password'; value = "bad`npassword" }
        )
        foreach ($case in $cases) {
            $invalid = $valid.Clone(); $invalid[$case.field] = $case.value
            Write-FixtureJson $invitePath $invalid
            $message = Assert-Throws { Read-OutlandsInvite $invitePath } 'Unsafe invite was accepted.'
            Assert-True (-not $message.Contains('DO-NOT-ECHO')) 'Validation echoed private input.'
        }
        $invalid = $valid.Clone(); $invalid.Remove('join_password')
        Write-FixtureJson $invitePath $invalid
        $null = Assert-Throws { Read-OutlandsInvite $invitePath } 'Missing invite field was accepted.'
        $invalid = $valid.Clone(); $invalid['extra_command'] = 'quit'
        Write-FixtureJson $invitePath $invalid
        $null = Assert-Throws { Read-OutlandsInvite $invitePath } 'Unknown invite field was accepted.'
        Write-FixtureJson $invitePath $valid
    }

    Test-Case 'join builder requires explicit no-password intent and rejects injection' {
        $text = New-OutlandsJoinText 'outlands.example' '' -NoPassword
        Assert-Equal $text "password `"`"`nconnect outlands.example:4977`n" 'No-password mode did not clear the saved password first.'
        $path = Join-Path $scratch 'no password join.cfg'
        Write-FixtureText $path $text
        Test-OutlandsJoin $path
        $null = Assert-Throws { New-OutlandsJoinText 'outlands.example' '' } 'Missing password silently enabled no-password mode.'
        $null = Assert-Throws { New-OutlandsJoinText 'outlands.example' 'synthetic-secret' -NoPassword } 'Conflicting password modes were accepted.'
        foreach ($address in @('outlands.example;quit', "outlands.example`nquit", 'outlands.example:0')) {
            $null = Assert-Throws { New-OutlandsJoinText $address '' -NoPassword } 'Unsafe no-password address was accepted.'
        }
        Write-FixtureText $path "password `"`"`nconnect outlands.example:4977`nquit`n"
        $null = Assert-Throws { Test-OutlandsJoin $path } 'An extra command was accepted in a no-password CFG.'
    }

    Test-Case 'saved LAN identity accepts one stable name and rejects malformed files' {
        $path = Join-Path $scratch 'player name.txt'
        foreach ($ending in @('', "`n", "`r`n")) {
            Write-FixtureText $path ('Stable Player' + $ending)
            Assert-Equal (Read-OutlandsName $path) 'Stable Player' 'Stable name did not survive a supported line ending.'
        }
        foreach ($invalid in @('', ' leading', 'trailing ', "Stable`nOther", 'bad;command', ('x' * 25), ('Stable' + [char]0))) {
            Write-FixtureText $path $invalid
            $null = Assert-Throws { Read-OutlandsName $path } 'Invalid saved identity was accepted.'
        }
        Write-FixtureBytes $path ([byte[]](83, 116, 97, 98, 108, 101, 255))
        $null = Assert-Throws { Read-OutlandsName $path } 'Non-ASCII saved identity was accepted.'
    }

    Test-Case 'non-secret settings validate paths with spaces and reject secret fields' {
        $path = Join-Path $scratch 'client settings.json'
        $settings = @{ game_dir = 'C:\Synthetic owned game'; plutonium_dir = 'C:\Synthetic local appdata\Plutonium'; client_port = 4976 }
        Write-FixtureJson $path $settings
        $parsed = Read-OutlandsSettings $path
        Assert-Equal $parsed.game_dir $settings.game_dir 'A path containing spaces was changed.'
        Assert-Equal $parsed.client_port 4976 'Client port was changed.'
        $settings['join_password'] = 'must-not-be-a-public-setting'
        Write-FixtureJson $path $settings
        $null = Assert-Throws { Read-OutlandsSettings $path } 'Secret field was accepted into public settings.'
        Write-FixtureJson $path @{ game_dir = "C:\bad`npath" }
        $null = Assert-Throws { Read-OutlandsSettings $path } 'A path containing a newline was accepted.'
        Write-FixtureJson $path @{ client_port = 65536 }
        $null = Assert-Throws { Read-OutlandsSettings $path } 'An invalid saved port was accepted.'
    }

    Test-Case 'private client writes restrict ACL to the current Windows identity' {
        $path = Join-Path $scratch 'private client name.txt'
        Write-OutlandsFile $path ([Text.Encoding]::ASCII.GetBytes("Stable Player`n"))
        Assert-Equal (Read-OutlandsName $path) 'Stable Player' 'Private write changed name bytes.'
        $acl = [IO.File]::GetAccessControl($path)
        Assert-True $acl.AreAccessRulesProtected 'Private client file still inherits permissions.'
        $rules = @($acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier]))
        Assert-Equal $rules.Count 1 'Private client file has unexpected access rules.'
        $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
        Assert-Equal $rules[0].IdentityReference.Value $sid 'Private file permits another identity.'
        Assert-Equal $rules[0].AccessControlType ([Security.AccessControl.AccessControlType]::Allow) 'Private file allow rule is missing.'
        Assert-True (($rules[0].FileSystemRights -band [Security.AccessControl.FileSystemRights]::FullControl) -eq [Security.AccessControl.FileSystemRights]::FullControl) 'Current identity lacks full control.'
    }

    # Copy only source scripts into a disposable project. Every executable below
    # is deliberately invalid: a launch attempt must fail instead of running it.
    $script:client = Join-Path $temporary 'client source with spaces'
    $tools = Join-Path $script:client 'tools'
    $null = [IO.Directory]::CreateDirectory($tools)
    foreach ($relative in @('setup-client-windows.ps1', 'tools\windows_client.ps1', 'tools\play_lan_windows.ps1')) {
        Copy-Item -LiteralPath (Join-Path $repository $relative) -Destination (Join-Path $script:client $relative)
    }
    $game = Join-Path $temporary 'owned game with spaces'
    foreach ($relative in @('t6mp.exe', 'zone\all\code_pre_gfx_mp.ff', 'zone\all\common_mp.ff')) {
        Write-FixtureText (Join-Path $game $relative) 'synthetic non-game fixture'
    }
    $runtime = Join-Path $temporary 'Plutonium runtime with spaces'
    foreach ($relative in @('bin\plutonium-bootstrapper-win32.exe', 'games\t6mp.exe')) {
        Write-FixtureText (Join-Path $runtime $relative) 'synthetic non-executable fixture'
    }
    $namePath = Join-Path $runtime 'storage\t6\outlands_player_name.txt'
    Write-OutlandsFile $namePath ([Text.Encoding]::ASCII.GetBytes("Stable Player`n"))
    $joinPath = Join-Path $runtime 'storage\t6\outlands_join.cfg'
    Write-OutlandsFile $joinPath ([Text.Encoding]::ASCII.GetBytes("password `"synthetic-test-password`"`nconnect outlands.example:4977`n"))
    $settingsPath = Join-Path $script:client 'runtime\client.json'
    Write-FixtureJson $settingsPath @{ game_dir = $game; plutonium_dir = $runtime; client_port = 4976 }
    $statsPath = Join-Path $runtime 'storage\demonware\synthetic-profile\mpstatsCompressed'
    Write-FixtureBytes $statsPath ([byte[]](1, 3, 5, 7, 255))
    $script:fakeBin = Join-Path $temporary 'fake commands'
    Write-FixtureText (Join-Path $script:fakeBin 'tailscale.exe') 'synthetic non-executable presence marker'
    $script:driver = Join-Path $temporary 'guarded child.ps1'
    Write-FixtureText $script:driver @'
$ErrorActionPreference = 'Stop'
function global:Invoke-WebRequest { throw 'Test guard: downloads are forbidden during checks.' }
function global:Read-Host { throw 'Test guard: prompts are forbidden during checks.' }
function global:Start-Process { throw 'Test guard: process launches are forbidden during checks.' }
$target = $args[0]
$forward = @()
if ($args.Count -gt 1) { $forward = @($args[1..($args.Count - 1)]) }
& $target @forward
exit $LASTEXITCODE
'@
    $setup = Join-Path $script:client 'setup-client-windows.ps1'
    $play = Join-Path $tools 'play_lan_windows.ps1'

    Test-Case 'dry run imports a private invite without download, prompt, writes or name change' {
        $before = Get-FixtureSnapshot $temporary
        $result = Invoke-ClientChild $setup @('--dry-run', '--game-dir', $game, '--plutonium-dir', $runtime, '--name', 'Alternate Name', '--invite', $invitePath)
        Assert-Equal $result.code 0 ('Client dry run failed: ' + $result.error)
        Assert-True ($result.output.Contains('Install inputs passed.')) 'Dry run did not validate inputs.'
        Assert-True (-not $result.output.Contains('synthetic-test-password')) 'Dry run printed the invite password.'
        Assert-Equal (Get-FixtureSnapshot $temporary) $before 'Dry run changed fixture files or created runtime/downloads.'
        Assert-Equal (Read-OutlandsName $namePath) 'Stable Player' 'Dry run replaced the saved LAN identity.'
    }

    Test-Case 'setup check reuses saved settings and private identity without modifying state' {
        $before = Get-FixtureSnapshot $temporary
        $result = Invoke-ClientChild $setup @('--check')
        Assert-Equal $result.code 0 ('Installed client check failed: ' + $result.error)
        Assert-True ($result.output.Contains('passed checks.')) 'Setup check did not complete.'
        Assert-Equal (Get-FixtureSnapshot $temporary) $before 'Setup check changed client or profile files.'
    }

    Test-Case 'play check validates the private join CFG without executing a game' {
        $before = Get-FixtureSnapshot $temporary
        $result = Invoke-ClientChild $play @('--join', '--check')
        Assert-Equal $result.code 0 ('Play prerequisites check failed: ' + $result.error)
        Assert-True ($result.output.Contains('No files changed or game process started.')) 'Play check did not stop before launch.'
        Assert-Equal (Get-FixtureSnapshot $temporary) $before 'Play check changed the identity or profile.'
    }

    Test-Case 'no-password preflight is read-only and rejects conflicting invites' {
        $before = Get-FixtureSnapshot $temporary
        $result = Invoke-ClientChild $setup @('--dry-run', '--skip-updater', '--no-password')
        Assert-Equal $result.code 0 ('No-password preflight failed: ' + $result.error)
        Assert-Equal (Get-FixtureSnapshot $temporary) $before 'No-password preflight changed client or profile files.'
        $result = Invoke-ClientChild $setup @('--dry-run', '--no-password', '--invite', $invitePath)
        Assert-True ($result.code -ne 0) 'Setup accepted an invite together with no-password mode.'
        Assert-True (-not ($result.output + $result.error).Contains('synthetic-test-password')) 'Rejected setup exposed a password.'
        Assert-Equal (Get-FixtureSnapshot $temporary) $before 'Conflicting setup options changed client state.'
    }

    Test-Case 'saved no-password CFG passes launch checks without changing profile or identity' {
        $original = [IO.File]::ReadAllBytes($joinPath)
        try {
            Write-FixtureText $joinPath (New-OutlandsJoinText 'outlands.example' '' -NoPassword)
            $before = Get-FixtureSnapshot $temporary
            $result = Invoke-ClientChild $play @('--join', '--check')
            Assert-Equal $result.code 0 ('No-password launch check failed: ' + $result.error)
            $result = Invoke-ClientChild $setup @('--check')
            Assert-Equal $result.code 0 ('No-password setup check failed: ' + $result.error)
            Assert-Equal (Get-FixtureSnapshot $temporary) $before 'No-password checks changed profile files or LAN identity.'
        } finally { Write-FixtureBytes $joinPath $original }
    }

    Test-Case 'invalid dry-run identity fails without changing any client state' {
        $before = Get-FixtureSnapshot $temporary
        $result = Invoke-ClientChild $setup @('--dry-run', '--name', 'bad;command')
        Assert-True ($result.code -ne 0) 'An unsafe identity was accepted by the setup entry point.'
        Assert-Equal (Get-FixtureSnapshot $temporary) $before 'Rejected setup changed existing state.'
    }
} finally {
    $cleanupTarget = [IO.Path]::GetFullPath($temporary)
    $tempParent = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
    if (-not $cleanupTarget.StartsWith($tempParent, [StringComparison]::OrdinalIgnoreCase) -or
        [IO.Path]::GetFileName($cleanupTarget) -notmatch '^Outlands Windows tests [0-9a-f]{32}$') {
        throw 'Refusing cleanup outside the dedicated synthetic test directory.'
    }
    if ([IO.Directory]::Exists($cleanupTarget)) { Remove-Item -LiteralPath $cleanupTarget -Recurse -Force }
}

Write-Output ('Windows synthetic checks: ' + $script:passed + ' passed, ' + $script:failed + ' failed.')
if ($script:failed -gt 0) { exit 1 }
exit 0
