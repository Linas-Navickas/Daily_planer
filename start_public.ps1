$ErrorActionPreference = "Stop"
$tunnelProcess = $null
$password = $null
$tunnelStdout = $null
$tunnelStderr = $null

function Get-AppLogicSignature {
    $files = @(
        (Join-Path $PSScriptRoot "main.py"),
        (Join-Path $PSScriptRoot "schemas.py"),
        (Join-Path $PSScriptRoot "mcp_server.py"),
        (Join-Path $PSScriptRoot "database.py"),
        (Join-Path $PSScriptRoot "index.html"),
        (Join-Path $PSScriptRoot "app.js")
    )
    $migrationPath = Join-Path $PSScriptRoot "migrations\versions"
    if (Test-Path -LiteralPath $migrationPath) {
        $files += Get-ChildItem -LiteralPath $migrationPath -Filter "*.py" -File -Recurse | Select-Object -ExpandProperty FullName
    }
    $parts = foreach ($file in $files | Sort-Object -Unique) {
        if (Test-Path -LiteralPath $file) {
            try { "${file}:$((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash)" }
            catch { return $null }
        }
    }
    return $parts -join "`n"
}

try {
    $dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $dockerCommand) { throw "Docker nerastas. Įdiekite ir paleiskite Docker Desktop." }

    $composeConfigJson = & $dockerCommand.Source compose --project-directory $PSScriptRoot config --format json 2>$null
    if ($LASTEXITCODE -ne 0) { throw "Nepavyko nuskaityti Docker Compose nustatymų. Patikrinkite .env failą." }
    try { $composeConfig = ($composeConfigJson -join [Environment]::NewLine) | ConvertFrom-Json }
    catch { throw "Docker Compose nustatymų nuskaityti nepavyko. Patikrinkite .env failą." }
    $password = [string]$composeConfig.services.app.environment.PLANNER_PASSWORD
    if ([string]::IsNullOrWhiteSpace($password) -or $password.Length -lt 12) {
        throw "Įrašykite bent 12 simbolių PLANNER_PASSWORD reikšmę į .env failą."
    }

    $env:PLANNER_PASSWORD = $password
    $sourceSignature = Get-AppLogicSignature
    & $dockerCommand.Source compose --project-directory $PSScriptRoot up -d --build db app mcp
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose nepaleido db, app ir mcp konteinerių. Patikrinkite .env nustatymus." }

    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            $null = Invoke-RestMethod -Uri "http://127.0.0.1:8000/healthz" -TimeoutSec 2
            $ready = $true
            break
        }
        catch { Start-Sleep -Seconds 1 }
    }
    if (-not $ready) {
        & $dockerCommand.Source compose --project-directory $PSScriptRoot logs --tail 40 app db
        throw "Planuoklio konteineris neatsiliepė. Patikrinkite Docker Compose žurnalą."
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
        $observedSignature = Get-AppLogicSignature
        if ($observedSignature -and $observedSignature -ne $sourceSignature) {
            Start-Sleep -Milliseconds 700
            $stableSignature = Get-AppLogicSignature
            if ($stableSignature -and $stableSignature -ne $sourceSignature) {
                Write-Host "Aptiktas programos pakeitimas. Perkuriamas app konteineris..."
                & $dockerCommand.Source compose --project-directory $PSScriptRoot up -d --build app
                if ($LASTEXITCODE -ne 0) { throw "Nepavyko atnaujinti app konteinerio." }
                $ready = $false
                for ($attempt = 0; $attempt -lt 60; $attempt++) {
                    try {
                        $null = Invoke-RestMethod -Uri "http://127.0.0.1:8000/healthz" -TimeoutSec 2
                        $ready = $true
                        break
                    }
                    catch { Start-Sleep -Seconds 1 }
                }
                if (-not $ready) { throw "Planuoklio serveris neatsiliepė po kodo pakeitimo." }
                $sourceSignature = $stableSignature
                Write-Host "App konteineris atnaujintas. Vietinis puslapis atsinaujins automatiškai. MCP konteineriui atnaujinti vykdykite: docker compose up -d --build mcp"
            }
        }
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
    if ($dockerCommand) {
        & $dockerCommand.Source compose --project-directory $PSScriptRoot stop app | Out-Null
    }
    foreach ($logPath in @($tunnelStdout, $tunnelStderr)) {
        if ($logPath -and (Test-Path $logPath)) { Remove-Item $logPath -Force }
    }
    $env:PLANNER_PASSWORD = $null
    $env:HOST = $null
    $env:PORT = $null
    $env:DEV_AUTO_RELOAD = $null
    $password = $null
}
