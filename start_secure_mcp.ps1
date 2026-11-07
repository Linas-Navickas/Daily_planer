$ErrorActionPreference = "Stop"
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

function Has-ComposeSetting {
    param([Parameter(Mandatory = $true)][string]$Name)
    if (-not (Test-Path -LiteralPath $envFilePath)) { return $false }
    return [bool](Get-Content -LiteralPath $envFilePath -Encoding UTF8 | Where-Object { $_ -match "^$([regex]::Escape($Name))=.+$" } | Select-Object -First 1)
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
    if (-not (Has-ComposeSetting "POSTGRES_PASSWORD") -or -not (Has-ComposeSetting "PLANNER_PASSWORD")) {
        throw "Į .env failą įrašykite POSTGRES_PASSWORD ir PLANNER_PASSWORD reikšmes pagal .env.example, išsaugodami jame CONTROL_PLANE_API_KEY."
    }
    $dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $dockerCommand) { throw "Docker nerastas. Įdiekite ir paleiskite Docker Desktop." }
    & $dockerCommand.Source compose --project-directory $PSScriptRoot up -d --build db app mcp
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose nepaleido db, app ir mcp konteinerių. Patikrinkite .env nustatymus." }
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            $null = Invoke-RestMethod -Uri "http://127.0.0.1:8001/healthz" -TimeoutSec 2
            $ready = $true
            break
        }
        catch { Start-Sleep -Seconds 1 }
    }
    if (-not $ready) {
        & $dockerCommand.Source compose --project-directory $PSScriptRoot logs --tail 40 mcp db
        throw "MCP konteineris neatsiliepė. Patikrinkite Docker Compose žurnalą."
    }

    Write-Host "db, app ir mcp konteineriai paleisti. Pradedamas Secure MCP Tunnel."
    & $tunnelClientPath run --profile "daily-planner"
    if ($LASTEXITCODE -ne 0) { throw "Secure MCP Tunnel sustojo su klaida (kodas $LASTEXITCODE)." }
}
finally {
    $env:CONTROL_PLANE_API_KEY = $null
    $apiKey = $null
    $secureApiKey = $null
    if ($apiKeyPtr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($apiKeyPtr) }
}
