# Client-only helpers. Never reads account tokens or player stats.
$ErrorActionPreference = 'Stop'

function Test-OutlandsPort($Value) {
    $number = 0
    if ("$Value" -notmatch '\A[0-9]{1,5}\z' -or -not [int]::TryParse("$Value", [ref]$number) -or $number -lt 1 -or $number -gt 65535) { throw 'Port must be an integer from 1 to 65535.' }
    return $number
}
function Test-OutlandsName([string]$Name) {
    if ($Name -cnotmatch '\A[A-Za-z0-9 _.~-]{1,24}\z' -or $Name.Trim() -cne $Name) { throw 'Name must be 1-24 ASCII letters, numbers, spaces, dots, underscores, tildes or hyphens, without outer spaces.' }
    return $Name
}
function Read-OutlandsName([string]$Path) {
    try {
        $item = Get-Item -LiteralPath $Path
        if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $item.Length -gt 26) { throw 'Invalid file' }
        $bytes = [IO.File]::ReadAllBytes($Path)
        foreach ($value in $bytes) { if ($value -gt 127) { throw 'Non-ASCII name' } }
        return Test-OutlandsName ([regex]::Replace([Text.Encoding]::ASCII.GetString($bytes), '\r?\n\z', ''))
    } catch { throw 'Saved player name must be one valid ASCII name in a regular file.' }
}
function Read-OutlandsSettings([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return @{} }
    try {
        $item = Get-Item -LiteralPath $Path
        if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $item.Length -gt 16384) { throw 'Invalid file' }
        $data = [IO.File]::ReadAllText($Path) | ConvertFrom-Json
        if ($null -eq $data -or $data -isnot [pscustomobject]) { throw 'Invalid object' }
        $result = @{}
        foreach ($property in $data.PSObject.Properties) {
            if ($property.Name -notin @('game_dir','plutonium_dir','client_port','steam_dir','proton_path')) { throw 'Unsupported setting' }
            if ($property.Name -eq 'client_port') { $result[$property.Name] = Test-OutlandsPort $property.Value }
            elseif ($property.Value -isnot [string] -or $property.Value -match '[\x00\r\n]') { throw 'Invalid path' }
            else { $result[$property.Name] = $property.Value }
        }
        return $result
    } catch { throw 'Client settings must be regular JSON containing only supported paths and port.' }
}
function Resolve-OutlandsPath([string]$Path) {
    if ([string]::IsNullOrEmpty($Path) -or $Path -match '[\x00\r\n"]') { throw 'Choose a valid directory path without quotes or newlines.' }
    try { return [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($Path)) }
    catch { throw 'Choose a valid directory path.' }
}
function Test-OutlandsGame([string]$Path) {
    $full = Resolve-OutlandsPath $Path
    foreach ($relative in @('t6mp.exe','zone\all\code_pre_gfx_mp.ff','zone\all\common_mp.ff')) {
        if (-not [IO.File]::Exists((Join-Path $full $relative))) { throw 'Owned BO2 directory must contain t6mp.exe and multiplayer core fastfiles.' }
    }
    return $full
}
function Test-OutlandsRuntime([string]$Path) {
    $full = Resolve-OutlandsPath $Path
    foreach ($relative in @('bin\plutonium-bootstrapper-win32.exe','games\t6mp.exe')) {
        if (-not [IO.File]::Exists((Join-Path $full $relative))) { throw 'Official Plutonium runtime is incomplete. Open the updater and let it finish.' }
    }
    return $full
}
function Test-OutlandsAddress([string]$Address) {
    $parts = $Address.Split(':')
    if ($parts.Count -gt 2) { throw 'Host must be an IPv4 address or DNS name with optional :port.' }
    $serverHost = $parts[0]; $port = 4977
    if ($parts.Count -eq 2) { $port = Test-OutlandsPort $parts[1] }
    if ($serverHost -match '\A[0-9.]+\z') {
        if ($serverHost -notmatch '\A(?:0|[1-9][0-9]{0,2})(?:\.(?:0|[1-9][0-9]{0,2})){3}\z') { throw 'Host must contain a valid IPv4 address.' }
        foreach ($octet in $serverHost.Split('.')) { if ([int]$octet -gt 255) { throw 'Host must contain a valid IPv4 address.' } }
    } else {
        if ([string]::IsNullOrEmpty($serverHost) -or $serverHost.Length -gt 253) { throw 'Host must contain a valid DNS name.' }
        foreach ($label in $serverHost.Split('.')) { if ($label -notmatch '\A[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\z') { throw 'Host must contain a valid DNS name.' } }
    }
    return $serverHost + ':' + $port
}
function Test-OutlandsPassword([string]$Password) {
    if ($Password.Length -lt 1 -or $Password.Length -gt 128 -or $Password -match '[^\x20-\x7e]|["\\;/]') { throw 'Password must be 1-128 printable ASCII characters excluding quotes, slashes, backslashes and semicolons.' }
    return $Password
}
function Read-OutlandsInvite([string]$Path) {
    try {
        $item = Get-Item -LiteralPath $Path
        if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $item.Length -gt 4096) { throw 'Invalid file' }
        $data = [IO.File]::ReadAllText($Path) | ConvertFrom-Json
        $keys = @($data.PSObject.Properties.Name)
        if ($keys.Count -ne 4 -or @($keys | Where-Object { $_ -notin @('schema_version','server_address','server_port','join_password') }).Count -gt 0) { throw 'Invalid fields' }
        if (($data.schema_version -isnot [int] -and $data.schema_version -isnot [long]) -or $data.schema_version -ne 1) { throw 'Invalid schema' }
        if ($data.server_address -isnot [string] -or $data.server_address.Contains(':') -or $data.join_password -isnot [string]) { throw 'Invalid data' }
        $port = Test-OutlandsPort $data.server_port
        return @{ address = Test-OutlandsAddress ($data.server_address + ':' + $port); password = Test-OutlandsPassword $data.join_password }
    } catch { throw 'Private invite must be valid schema_version 1 JSON; contents were not printed.' }
}
function Test-OutlandsJoin([string]$Path) {
    try {
        $item = Get-Item -LiteralPath $Path
        if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $item.Length -gt 4096) { throw 'Invalid file' }
        $bytes = [IO.File]::ReadAllBytes($Path)
        foreach ($value in $bytes) { if ($value -gt 127) { throw 'Non-ASCII file' } }
        $lines = [regex]::Split([Text.Encoding]::ASCII.GetString($bytes), '\r?\n')
        if ($lines.Count -gt 1 -and $lines[-1] -eq '') { $lines = $lines[0..($lines.Count - 2)] }
        if ($lines.Count -ne 2 -or $lines[0] -cnotmatch '\Apassword "([^"]*)"\z') { throw 'Invalid password command' }
        $null = Test-OutlandsPassword $Matches[1]
        if ($lines[1] -cnotmatch '\Aconnect ([^\s]+)\z') { throw 'Invalid connect command' }
        $null = Test-OutlandsAddress $Matches[1]
    } catch { throw 'Private join CFG must contain only valid password and connect commands.' }
}
function Write-OutlandsFile([string]$Path, [byte[]]$Bytes) {
    $temporary = $null
    try {
        if (Test-Path -LiteralPath $Path) {
            $item = Get-Item -LiteralPath $Path
            if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Invalid destination' }
        }
        $null = [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Path))
        $temporary = $Path + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
        [IO.File]::WriteAllBytes($temporary, $Bytes)
        if ([IO.File]::Exists($Path)) { [IO.File]::Replace($temporary, $Path, $null) } else { [IO.File]::Move($temporary, $Path) }
        $access = New-Object Security.AccessControl.FileSecurity
        $access.SetAccessRuleProtection($true, $false)
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent().User
        $rule = New-Object Security.AccessControl.FileSystemAccessRule($identity, 'FullControl', 'Allow')
        $access.AddAccessRule($rule)
        [IO.File]::SetAccessControl($Path, $access)
    } catch { throw 'Cannot save a private client file; check destination permissions.' }
    finally { if ($temporary -and [IO.File]::Exists($temporary)) { [IO.File]::Delete($temporary) } }
}
function Read-OutlandsHidden([string]$Prompt) {
    $secure = Read-Host $Prompt -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer); $secure.Dispose() }
}
