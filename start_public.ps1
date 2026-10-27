$ErrorActionPreference = "Stop"
$serverProcess = $null
$password = $null
$securePassword = Read-Host "Sugalvokite planuoklio slaptažodį" -AsSecureString
$passwordPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)

try {
    $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPtr)
    if ([string]::IsNullOrWhiteSpace($password) -or $password.Length -lt 12) {
        throw "Naudokite bent 12 simbolių slaptažodį."
    }

    $env:PLANNER_PASSWORD = $password
    $env:PORT = "8000"
    $serverPath = Join-Path $PSScriptRoot "main.py"
    $serverProcess = Start-Process -FilePath "python" `
        -ArgumentList @("-u", "`"$serverPath`"") `
        -WorkingDirectory $PSScriptRoot `
        -PassThru `
        -WindowStyle Hidden

    Start-Sleep -Seconds 2
    if ($serverProcess.HasExited) {
        throw "Planuoklio serveris nepasileido. Patikrinkite, ar įdiegtas Python."
    }

    Write-Host "Planuoklis paleistas. SSH tunelio išorinis adresas bus parodytas žemiau."
    Write-Host "Pirmą kartą prisijungiant SSH gali paprašyti patvirtinti localhost.run serverio raktą."
    Write-Host "Tunelio langą uždarykite su Ctrl+C."
    & ssh -R 80:localhost:8000 nokey@localhost.run
}
finally {
    if ($serverProcess -and -not $serverProcess.HasExited) {
        Stop-Process -Id $serverProcess.Id -Force
    }
    $env:PLANNER_PASSWORD = $null
    $password = $null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPtr)
}
