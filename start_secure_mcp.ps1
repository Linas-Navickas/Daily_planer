$ErrorActionPreference = "Stop"
$serverProcess = $null
$apiKeyPtr = [IntPtr]::Zero
$secureApiKey = $null
$apiKey = $null
$tunnelClientPath = Join-Path $PSScriptRoot ".tools\tunnel-client.exe"
$envFilePath = Join-Path $PSScriptRoot ".env"

function Get-StoredApiKey {
    if (-not (Test-Path -LiteralPath $envFilePath)) { return $null }
    $line = Get-Content -LiteralPath $envFilePath -Encoding UTF8 | Where-Object { $_ -match '^CONTROL_PLANE_API_KEY=' } | Select-Object -Last 1
    if (-not $line) { return $null }
    return $line.Substring('CONTROL_PLANE_API_KEY='.Length).Trim()
}

function Save-ApiKey {
    param([Parameter(Mandatory = $true)][string]$Value)
    $lines = @()
    if (Test-Path -LiteralPath $envFilePath) {
        $lines = @(Get-Content -LiteralPath $envFilePath -Encoding UTF8 | Where-Object { $_ -notmatch '^CONTROL_PLANE_API_KEY=' })
    }
    $lines += "CONTROL_PLANE_API_KEY=$Value"
    [System.IO.File]::WriteAllLines($envFilePath, [string[]]$lines, (New-Object System.Text.UTF8Encoding($false)))
}

function Read-MaskedSecret {
    param([string]$Prompt)
    Write-Host -NoNewline $Prompt
    $value = New-Object System.Security.SecureString
    while ($true) {
        $key = [Console]::ReadKey($true)
        if ($key.Key -eq [ConsoleKey]::Enter) {
            [Console]::WriteLine()
            $value.MakeReadOnly()
            return $value
        }
        if ($key.Key -eq [ConsoleKey]::Backspace) {
            if ($value.Length -gt 0) {
                $value.RemoveAt($value.Length - 1)
                [Console]::Write("`b `b")
            }
            continue
        }
        if (-not [char]::IsControl($key.KeyChar)) {
            $value.AppendChar($key.KeyChar)
            [Console]::Write(".")
        }
    }
}

if (-not (Test-Path $tunnelClientPath)) {
    throw "Nerasta .tools\tunnel-client.exe. Atsisiųskite jį iš OpenAI Platform → Tunnels."
}

try {
    $apiKey = Get-StoredApiKey
    if ([string]::IsNullOrWhiteSpace($apiKey)) {
        $secureApiKey = Read-MaskedSecret "Pirmą kartą įveskite tunnel-client runtime API raktą (jis bus išsaugotas .env): "
        $apiKeyPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureApiKey)
        $apiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($apiKeyPtr)
        if ([string]::IsNullOrWhiteSpace($apiKey) -or $apiKey.Contains("`n") -or $apiKey.Contains("`r")) {
            throw "API raktas negali būti tuščias arba turėti naujos eilutės simbolių."
        }
        Save-ApiKey -Value $apiKey
        Write-Host "Raktas išsaugotas .env faile. Kitą kartą jo įvesti nereikės."
    }
}
catch {
    if ($apiKeyPtr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($apiKeyPtr) }
    throw
}

try {
    $env:CONTROL_PLANE_API_KEY = $apiKey
    $env:PLANNER_PASSWORD = "secure-mcp-local-only"
    $env:DATA_DIR = Join-Path $PSScriptRoot "data"
    $env:PORT = "8001"
    $env:HOST = "127.0.0.1"
    $env:MCP_TUNNEL_MODE = "1"

    $serverPath = Join-Path $PSScriptRoot "main.py"
    $serverProcess = Start-Process -FilePath "python" -ArgumentList @("-u", "`"$serverPath`"") -WorkingDirectory $PSScriptRoot -PassThru -WindowStyle Hidden
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if ($serverProcess.HasExited) { throw "Lokaliai apribotas MCP serveris nepasileido." }
        $client = New-Object System.Net.Sockets.TcpClient
        try {
            $client.Connect("127.0.0.1", 8001)
            $ready = $true
            break
        }
        catch { Start-Sleep -Milliseconds 300 }
        finally { $client.Dispose() }
    }
    if (-not $ready) { throw "MCP serveris neatsiliepė per 9 sekundes." }

    Write-Host "Pradedamas Secure MCP Tunnel. Jis pasiekiamas tik per jūsų OpenAI tunelį."
    & $tunnelClientPath run --profile "daily-planner"
    if ($LASTEXITCODE -ne 0) { throw "Secure MCP Tunnel sustojo su klaida (kodas $LASTEXITCODE)." }
}
finally {
    if ($serverProcess -and -not $serverProcess.HasExited) { Stop-Process -Id $serverProcess.Id -Force }
    $env:CONTROL_PLANE_API_KEY = $null
    $env:PLANNER_PASSWORD = $null
    $env:DATA_DIR = $null
    $env:PORT = $null
    $env:HOST = $null
    $env:MCP_TUNNEL_MODE = $null
    $apiKey = $null
    $secureApiKey = $null
    if ($apiKeyPtr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($apiKeyPtr) }
}
