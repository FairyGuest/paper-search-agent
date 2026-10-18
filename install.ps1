param(
    [switch]$SkipBrowser,
    [switch]$NoPath,
    [switch]$Launch
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$ProjectRoot = $PSScriptRoot
if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot "pyproject.toml"))) {
    throw "Extract the complete Paper SA project before running this installer."
}
Write-Host "Paper SA installer - local account installation, no Node.js required." -ForegroundColor Green
Write-Host "This installs uv (if missing), managed Python 3.12, Paper SA and Chromium."
$Uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $Uv) {
    $Installer = Join-Path ([System.IO.Path]::GetTempPath()) ("paper-sa-uv-" + [guid]::NewGuid().ToString() + ".ps1")
    try {
        Invoke-WebRequest -UseBasicParsing -Uri "https://astral.sh/uv/install.ps1" -OutFile $Installer
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Installer
        if ($LASTEXITCODE -ne 0) { throw "uv bootstrap failed." }
    } finally {
        if (Test-Path -LiteralPath $Installer) { Remove-Item -LiteralPath $Installer }
    }
    $UvPath = Join-Path $HOME ".local\bin\uv.exe"
    if (-not (Test-Path -LiteralPath $UvPath)) { throw "uv was installed but not found at $UvPath. Reopen the terminal and retry." }
} else {
    $UvPath = $Uv.Source
}
& $UvPath python install 3.12
if ($LASTEXITCODE -ne 0) { throw "Python installation failed. Check network access to GitHub." }
$Constraints = Join-Path ([System.IO.Path]::GetTempPath()) ("paper-sa-deps-" + [guid]::NewGuid().ToString() + ".txt")
try {
    & $UvPath export --project $ProjectRoot --frozen --no-dev --no-emit-project --no-hashes --output-file $Constraints | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Dependency lock export failed." }
    & $UvPath tool install --force --python 3.12 --constraint $Constraints $ProjectRoot
    if ($LASTEXITCODE -ne 0) { throw "Paper SA installation failed." }
} finally {
    if (Test-Path -LiteralPath $Constraints) { Remove-Item -LiteralPath $Constraints }
}
$BinDirectory = (& $UvPath tool dir --bin).Trim()
$PaperSA = Join-Path $BinDirectory "paper-sa.exe"
if (-not (Test-Path -LiteralPath $PaperSA)) { throw "paper-sa executable was not installed." }
if (-not $NoPath) {
    $UserPath = [string][Environment]::GetEnvironmentVariable("Path", "User")
    if (($UserPath -split ";") -notcontains $BinDirectory) {
        [Environment]::SetEnvironmentVariable("Path", (($UserPath.TrimEnd(";") + ";" + $BinDirectory).TrimStart(";")), "User")
    }
    $env:Path = $BinDirectory + ";" + $env:Path
}
if (-not $SkipBrowser) {
    & $PaperSA install-browser
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Chromium could not be downloaded. Paper SA is installed; use manual mode or retry: paper-sa install-browser"
    }
}
& $PaperSA --version
if ($LASTEXITCODE -ne 0) { throw "Installation verification failed." }
Write-Host "Ready. In a new terminal run: paper-sa" -ForegroundColor Green
Write-Host "Executable: $PaperSA"
if ($Launch) { & $PaperSA }
