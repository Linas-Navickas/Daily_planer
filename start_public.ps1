$ErrorActionPreference = "Stop"
$serverProcess = $null
$tunnelProcess = $null
$password = $null
$tunnelStdout = $null
$tunnelStderr = $null

function Read-MaskedPassword {
    param([string]$Prompt)
    Write-Host -NoNewline $Prompt
    $value = New-Object System.Security.SecureString
    while ($true) {
        try {
            $key = [Console]::ReadKey($true)
        }
        catch [System.InvalidOperationException] {
            Write-Host "`nŠis terminalas nepalaiko slapto įvedimo taškeliais. Įveskite slaptažodį į saugų įvedimo lauką."
            return Read-Host -Prompt $Prompt -AsSecureString
        }
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
    $env:HOST = "127.0.0.1"
    $serverPath = Join-Path $PSScriptRoot "main.py"
    $serverProcess = Start-Process -FilePath "python" `
        -ArgumentList @("-u", "`"$serverPath`"") `
        -WorkingDirectory $PSScriptRoot `
        -PassThru `
        -WindowStyle Hidden

    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if ($serverProcess.HasExited) {
            throw "Planuoklio serveris nepasileido. Patikrinkite, ar įdiegtas Python ir ar prievadas 8000 laisvas."
        }
        $client = New-Object System.Net.Sockets.TcpClient
        try {
            $client.Connect("127.0.0.1", 8000)
            $ready = $true
            break
        }
        catch { Start-Sleep -Milliseconds 300 }
        finally { $client.Dispose() }
    }
    if (-not $ready) {
        throw "Planuoklio serveris neatsiliepė per 9 sekundes."
    }

    $cloudflaredPath = Join-Path $PSScriptRoot ".tools\cloudflared.exe"
    if (-not (Test-Path $cloudflaredPath)) {
        $cloudflaredCommand = Get-Command cloudflared -ErrorAction SilentlyContinue
        if (-not $cloudflaredCommand) {
            throw "Nerasta cloudflared. Paleiskite cloudflared.exe diegimo instrukciją arba įdiekite jį į PATH."
        }
        $cloudflaredPath = $cloudflaredCommand.Source
    }

    Write-Host "Planuoklis paleistas. Cloudflare Quick Tunnel parodys laikiną HTTPS URL."
    $tunnelStdout = Join-Path $env:TEMP ("planner-cloudflared-{0}.out.log" -f [guid]::NewGuid())
    $tunnelStderr = Join-Path $env:TEMP ("planner-cloudflared-{0}.err.log" -f [guid]::NewGuid())
    $tunnelProcess = Start-Process -FilePath $cloudflaredPath `
        -ArgumentList @("tunnel", "--url", "http://127.0.0.1:8000") `
        -PassThru `
        -WindowStyle Hidden `
        -RedirectStandardOutput $tunnelStdout `
        -RedirectStandardError $tunnelStderr

    $publicUrl = $null
    $qrPath = Join-Path $PSScriptRoot "planner-qr.png"
    Write-Host "Laukiama Cloudflare adreso..."
    while (-not $tunnelProcess.HasExited -and -not $publicUrl) {
        foreach ($logPath in @($tunnelStdout, $tunnelStderr)) {
            if (Test-Path $logPath) {
                $match = Select-String -Path $logPath -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' | Select-Object -First 1
                if ($match) {
                    $publicUrl = $match.Matches[0].Value
                    break
                }
            }
        }
        if (-not $publicUrl) {
            Start-Sleep -Milliseconds 500
        }
    }

    if ($publicUrl) {
        Write-Host "Viešas planuoklio adresas: $publicUrl"
        Write-Host "ChatGPT papildinio pastoviam MCP ryšiui paleiskite start_secure_mcp.ps1; šis Quick Tunnel skirtas planuoklio svetainei."
        $qrGeneratorPath = Join-Path $PSScriptRoot "generate_qr.py"
        & python $qrGeneratorPath $publicUrl $qrPath
        if ($LASTEXITCODE -eq 0) {
            Write-Host "QR kodas atnaujintas: $qrPath"
        }
        else {
            throw "QR kodo sukurti nepavyko. Įdiekite modulį su: python -m pip install -r requirements.txt"
        }
        if (-not (Test-Path $qrPath)) {
            throw "QR kodo failas nesukurtas: $qrPath"
        }
        Start-Process -FilePath $qrPath
        Write-Host "QR kodas atidarytas vaizdų peržiūros programoje."
        $localUrl = "http://127.0.0.1:8000"
        Start-Process -FilePath $localUrl
        Write-Host "Planuoklis atidarytas kompiuterio naršyklėje: $localUrl"
        Write-Host "Telefone naudokite QR kodą arba viešą adresą: $publicUrl"
        Write-Host "Tunelis veiks tol, kol šis langas bus atidarytas. Sustabdykite su Ctrl+C."
    }
    else {
        Write-Host "Cloudflare tunelis sustojo nesuteikęs viešo URL."
        foreach ($logPath in @($tunnelStdout, $tunnelStderr)) {
            if (Test-Path $logPath) { Get-Content $logPath }
        }
    }

    while (-not $tunnelProcess.HasExited) {
        Start-Sleep -Seconds 1
    }
    if ($tunnelProcess.ExitCode -ne 0) {
        if (Test-Path $tunnelStderr) { Get-Content $tunnelStderr }
        throw "Cloudflare tunelis nutrūko (kodas $($tunnelProcess.ExitCode)). Paleiskite scenarijų iš naujo ir naudokite naują URL."
    }
}
finally {
    if ($tunnelProcess -and -not $tunnelProcess.HasExited) {
        Stop-Process -Id $tunnelProcess.Id -Force
    }
    if ($serverProcess -and -not $serverProcess.HasExited) {
        Stop-Process -Id $serverProcess.Id -Force
    }
    foreach ($logPath in @($tunnelStdout, $tunnelStderr)) {
        if ($logPath -and (Test-Path $logPath)) { Remove-Item $logPath -Force }
    }
    $env:PLANNER_PASSWORD = $null
    $env:HOST = $null
    $env:PORT = $null
    $password = $null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPtr)
}
