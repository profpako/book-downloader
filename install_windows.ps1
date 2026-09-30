$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if ($env:OS -ne "Windows_NT") {
    throw "Questo installer funziona solo su Windows."
}

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Test-Python([string]$Path) {
    try {
        & $Path -c "import sys; raise SystemExit(not ((3, 10) <= sys.version_info < (3, 15)))" 2>$null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Find-Python {
    $localPython = Join-Path $Root ".runtime\python\python.exe"
    if ((Test-Path $localPython) -and (Test-Python $localPython)) {
        return $localPython
    }

    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        foreach ($version in @("3.14", "3.13", "3.12", "3.11", "3.10")) {
            try {
                $path = & $launcher.Source "-$version" -c "import sys; print(sys.executable)" 2>$null | Select-Object -Last 1
                if ($path -and (Test-Python $path)) { return $path }
            } catch {}
        }
    }

    foreach ($name in @("python.exe", "python3.exe")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command -and $command.Source -notlike "$env:LOCALAPPDATA\Microsoft\WindowsApps\python*.exe") {
            try {
                $path = & $command.Source -c "import sys; print(sys.executable)" 2>$null | Select-Object -Last 1
                if ($path -and (Test-Python $path)) { return $path }
            } catch {}
        }
    }
    return $null
}

function Get-PythonManager {
    $command = Get-Command pymanager.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }

    $candidates = @(
        "$env:LOCALAPPDATA\Microsoft\WindowsApps\pymanager.exe"
        Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WindowsApps\PythonSoftwareFoundation.PythonManager_*\pymanager.exe" -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName }
    )
    return $candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
}

function Install-PythonManager {
    $manager = Get-PythonManager
    if ($manager) { return $manager }

    Write-Host "Python compatibile non trovato: installazione del gestore ufficiale Python..."
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if ($winget) {
        & $winget.Source install 9NQ7512CXL7T -e --accept-package-agreements --accept-source-agreements --disable-interactivity | Out-Host
        $manager = Get-PythonManager
    }

    if (-not $manager) {
        Write-Host "WinGet non disponibile: uso il pacchetto ufficiale python.org..."
        Add-AppxPackage -AppInstallerFile "https://www.python.org/ftp/python/pymanager/pymanager.appinstaller" | Out-Host
        $manager = Get-PythonManager
    }
    if (-not $manager) { throw "Gestore Python installato ma non trovato. Riavvia Windows e rilancia INSTALLA_WINDOWS.bat." }
    return $manager
}

$Python = Find-Python
if (-not $Python) {
    $manager = Install-PythonManager
    $runtimeDir = Join-Path $Root ".runtime\python"
    if (Test-Path $runtimeDir) { Remove-Item $runtimeDir -Recurse -Force }
    New-Item (Split-Path $runtimeDir) -ItemType Directory -Force | Out-Null
    Write-Host "Installazione di Python 3.14..."
    & $manager install "--target=$runtimeDir" 3.14
    if ($LASTEXITCODE -ne 0) { throw "Installazione di Python 3.14 non riuscita (codice $LASTEXITCODE)." }
    $Python = Join-Path $runtimeDir "python.exe"
}
if (-not (Test-Python $Python)) { throw "Impossibile trovare una versione compatibile di Python (3.10-3.14)." }

function Test-Node([string]$Path) {
    try {
        & $Path -e 'const n=Number(process.versions.node.split(".")[0]); process.exit(n < 22 || n % 2)' 2>$null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Install-NodeLts {
    Write-Host "Node.js supportato non trovato: download dell'ultima versione LTS..."
    $architecture = [Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant()
    if ($architecture -notin @("x64", "arm64")) { throw "Architettura Windows non supportata: $architecture." }

    $release = Invoke-RestMethod "https://nodejs.org/dist/index.json" | Where-Object { $_.lts } | Select-Object -First 1
    if (-not $release) { throw "Impossibile individuare l'ultima versione LTS di Node.js." }

    $folderName = "node-$($release.version)-win-$architecture"
    $zipName = "$folderName.zip"
    if ($release.files -notcontains "win-$architecture-zip") { throw "Node.js $($release.version) non è disponibile per $architecture." }

    $temporary = Join-Path ([IO.Path]::GetTempPath()) ("book-downloader-" + [Guid]::NewGuid())
    $zipPath = Join-Path $temporary $zipName
    New-Item $temporary -ItemType Directory | Out-Null
    try {
        $baseUrl = "https://nodejs.org/dist/$($release.version)"
        $checksums = (Invoke-WebRequest "$baseUrl/SHASUMS256.txt" -UseBasicParsing).Content
        $match = [regex]::Match($checksums, "(?m)^([a-f0-9]{64})\s+$([regex]::Escape($zipName))\s*$")
        if (-not $match.Success) { throw "Checksum ufficiale di Node.js non trovato." }

        Invoke-WebRequest "$baseUrl/$zipName" -OutFile $zipPath -UseBasicParsing
        $actualHash = (Get-FileHash $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actualHash -ne $match.Groups[1].Value) { throw "Il controllo di integrità del download Node.js non è riuscito." }

        Expand-Archive $zipPath -DestinationPath $temporary
        $destination = Join-Path $Root ".runtime\node"
        if (Test-Path $destination) { Remove-Item $destination -Recurse -Force }
        New-Item (Split-Path $destination) -ItemType Directory -Force | Out-Null
        Move-Item (Join-Path $temporary $folderName) $destination
        return (Join-Path $destination "node.exe")
    } finally {
        if (Test-Path $temporary) { Remove-Item $temporary -Recurse -Force }
    }
}

$Node = Join-Path $Root ".runtime\node\node.exe"
if (-not (Test-Path $Node) -or -not (Test-Node $Node)) {
    $nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
    $Node = if ($nodeCommand) { $nodeCommand.Source } else { $null }
}

$Npm = if ($Node) { Join-Path (Split-Path $Node) "npm.cmd" } else { $null }
if (-not $Node -or -not (Test-Node $Node) -or -not (Test-Path $Npm)) {
    $Node = Install-NodeLts
    $Npm = Join-Path (Split-Path $Node) "npm.cmd"
}

$pythonVersion = & $Python --version 2>&1
$nodeVersion = & $Node --version
Write-Host "Uso $pythonVersion e Node $nodeVersion."

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython) -or -not (Test-Python $VenvPython)) {
    & $Python -m venv --clear (Join-Path $Root ".venv")
    if ($LASTEXITCODE -ne 0) { throw "Creazione dell'ambiente Python non riuscita." }
}

& $VenvPython -m pip install -r (Join-Path $Root "sidecar\requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Installazione delle dipendenze Python non riuscita." }
& $VenvPython -m playwright install chromium
if ($LASTEXITCODE -ne 0) { throw "Installazione di Chromium non riuscita." }
& $Npm ci --prefix (Join-Path $Root "app")
if ($LASTEXITCODE -ne 0) { throw "Installazione delle dipendenze dell'interfaccia non riuscita." }

function Test-Url([string]$Url) {
    try {
        Invoke-WebRequest $Url -UseBasicParsing -TimeoutSec 1 | Out-Null
        return $true
    } catch {
        return $false
    }
}

Write-Host "Installazione completata. Avvio Book Downloader..."
$apiProcess = $null
try {
    if (-not (Test-Url "http://127.0.0.1:8923/health")) {
        $apiProcess = Start-Process $VenvPython -ArgumentList "sidecar_api.py" -WorkingDirectory (Join-Path $Root "sidecar") -NoNewWindow -PassThru
        foreach ($attempt in 1..20) {
            if (Test-Url "http://127.0.0.1:8923/health") { break }
            if ($apiProcess.HasExited) { throw "Il servizio Python non si è avviato." }
            Start-Sleep -Milliseconds 500
        }
        if (-not (Test-Url "http://127.0.0.1:8923/health")) { throw "Il servizio Python non risponde sulla porta 8923." }
    }

    if (Test-Url "http://localhost:1420/") {
        Start-Process "http://localhost:1420/"
        if ($apiProcess) { Wait-Process $apiProcess.Id }
    } else {
        & $Npm run dev --prefix (Join-Path $Root "app") -- --open
    }
} finally {
    if ($apiProcess -and -not $apiProcess.HasExited) { Stop-Process $apiProcess.Id -Force }
}
