$ErrorActionPreference = "Stop"
$serverProcess = $null
$password = $null

function Read-MaskedPassword {
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

$securePassword = Read-MaskedPassword "Sugalvokite planuoklio slaptažodį (bent 12 simbolių): "
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
    & ssh -o ExitOnForwardFailure=yes `
        -o ServerAliveInterval=60 `
        -o ServerAliveCountMax=3 `
        -R 80:localhost:8000 nokey@localhost.run
    if ($LASTEXITCODE -ne 0) {
        throw "SSH tunelis nutrūko (kodas $LASTEXITCODE). Paleiskite scenarijų iš naujo ir naudokite naują URL."
    }
}
finally {
    if ($serverProcess -and -not $serverProcess.HasExited) {
        Stop-Process -Id $serverProcess.Id -Force
    }
    $env:PLANNER_PASSWORD = $null
    $password = $null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPtr)
}
