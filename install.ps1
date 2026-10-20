# Installs PrestCribe on Windows, or updates it, from the latest GitHub release. Paste this in PowerShell:
#   powershell -ExecutionPolicy ByPass -c "irm https://github.com/bennos280/IT-Project-Unimelb-Archive-Team-4/releases/latest/download/install.ps1 | iex"
# It installs uv (which brings Python) if it's missing, puts the app in %LOCALAPPDATA%\PrestCribe (an update keeps its database,
# scans and results: none are in a release), installs its libraries, adds a PrestCribe shortcut to the desktop and starts it.
param(
    [string]$Zip = "",  # a release zip on this computer instead of the latest download
    [string]$Folder = "$env:LOCALAPPDATA\PrestCribe",
    [switch]$NoShortcut,
    [switch]$NoStart
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"  # Invoke-WebRequest is many times slower drawing its progress bar
$release = "https://github.com/bennos280/IT-Project-Unimelb-Archive-Team-4/releases/latest/download/PrestCribe.zip"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv..."
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$(if ($env:UV_INSTALL_DIR) { $env:UV_INSTALL_DIR } else { "$env:USERPROFILE\.local\bin" });$env:Path"
}
$uv = (Get-Command uv).Source

$work = Join-Path $env:TEMP "prestcribe-install-$PID"
New-Item -ItemType Directory -Force $work | Out-Null
try {
    if (-not $Zip) {
        Write-Host "Downloading PrestCribe..."
        $Zip = Join-Path $work "PrestCribe.zip"
        Invoke-WebRequest $release -OutFile $Zip
    }
    Expand-Archive $Zip (Join-Path $work "app")  # no database in it: the one here is kept, or made on first run
    New-Item -ItemType Directory -Force $Folder | Out-Null
    Copy-Item (Join-Path $work "app\*") $Folder -Recurse -Force
} finally {
    Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "Installing its libraries (the first time downloads a few hundred MB)..."
$sync = "sync", "--directory", $Folder
if (Test-Path (Join-Path $Folder ".venv\Lib\site-packages\torch")) { $sync += "--extra", "local-sorting" }  # an update keeps page sorting on this computer
& $uv @sync
if ($LASTEXITCODE) { throw "uv sync failed" }

if (-not $NoShortcut) {  # on the desktop, and in the Start menu, so searching Start for PrestCribe finds it
    foreach ($place in "Desktop", "Programs") {
        $link = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path ([Environment]::GetFolderPath($place)) "PrestCribe.lnk"))
        $link.TargetPath = $uv
        $link.Arguments = "run prestcribe"
        $link.WorkingDirectory = $Folder
        $link.Description = "Start PrestCribe"
        $link.IconLocation = Join-Path $Folder "frontend\dist\favicon.ico"
        $link.Save()
    }
    Write-Host "Added PrestCribe to your desktop and Start menu."
}

if (-not ((Get-Command claude -ErrorAction SilentlyContinue) -or (Get-Command codex -ErrorAction SilentlyContinue))) {
    Write-Warning "Reading pages needs Claude Code or the Codex CLI installed and signed in. PrestCribe's Settings page shows how."
}
Write-Host "PrestCribe is installed in $Folder."
if (-not $NoStart) {
    Start-Process $uv -ArgumentList "run", "prestcribe" -WorkingDirectory $Folder
}
