$ErrorActionPreference = "Stop"
$profileName = "daily-planner"
$tunnelClientPath = Join-Path $PSScriptRoot ".tools\tunnel-client.exe"
$apiKeyPtr = [IntPtr]::Zero

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
    throw "Įdėkite tunnel-client.exe į .tools aplanką. Atsisiųskite jį iš OpenAI Platform → Tunnels."
}

$tunnelId = Read-Host "Įveskite OpenAI Platformoje sukurto tunelio ID"
if ([string]::IsNullOrWhiteSpace($tunnelId)) { throw "Tunelio ID negali būti tuščias." }

$secureApiKey = Read-MaskedSecret "Įveskite tunnel-client runtime API raktą: "
$apiKeyPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureApiKey)
try {
    $env:CONTROL_PLANE_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($apiKeyPtr)
    & $tunnelClientPath init --force --sample sample_mcp_remote_no_auth --profile $profileName --tunnel-id $tunnelId --mcp-server-url "http://127.0.0.1:8001/mcp"
    if ($LASTEXITCODE -ne 0) { throw "Tunnel profilio paruošti nepavyko. Patikrinkite tunnel-client help quickstart." }
    Write-Host "Tunelio profilis paruoštas. Raktas į projekto failus neįrašytas. Dabar paleiskite .\start_secure_mcp.ps1."
}
finally {
    $env:CONTROL_PLANE_API_KEY = $null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($apiKeyPtr)
}
