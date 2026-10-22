# Installs PrestCribe on Windows, or updates it, from the latest GitHub release. Paste this in PowerShell:
#   powershell -ExecutionPolicy ByPass -c "irm https://github.com/bennos280/IT-Project-Unimelb-Archive-Team-4/releases/latest/download/install.ps1 | iex"
# It installs uv (which brings Python) if it's missing, puts the app in %LOCALAPPDATA%\PrestCribe (an update keeps its database,
# scans and results: none are in a release), installs its libraries, adds a PrestCribe shortcut to the desktop and starts it
# in its own window (Edge WebView2, installed here if the computer doesn't have it).
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
$uvw = Join-Path (Split-Path $uv) "uvw.exe"  # runs it with no console window
if (-not (Test-Path $uvw)) { $uvw = $uv }

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

$webview2 = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"  # Edge WebView2 Runtime: PrestCribe's window; missing or 0.0.0.0 = not installed
function Test-WebView2 {
    $version = foreach ($key in "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\$webview2", "HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\$webview2", "HKCU:\SOFTWARE\Microsoft\EdgeUpdate\Clients\$webview2") {
        (Get-ItemProperty $key -Name pv -ErrorAction SilentlyContinue).pv
    }
    [bool]($version | Where-Object { $_ -and $_ -ne "0.0.0.0" })
}
if (-not (Test-WebView2)) {
    Write-Host "Installing Microsoft Edge WebView2 (PrestCribe's window)..."
    $bootstrapper = Join-Path $env:TEMP "MicrosoftEdgeWebview2Setup.exe"
    $setup = $null
    try {
        Invoke-WebRequest "https://go.microsoft.com/fwlink/p/?LinkId=2124703" -OutFile $bootstrapper
        $setup = Start-Process $bootstrapper -ArgumentList "/silent", "/install" -Wait -PassThru
    } catch {
        Write-Warning "Couldn't run the WebView2 installer ($_)."
    } finally {
        Remove-Item $bootstrapper -Force -ErrorAction SilentlyContinue
    }
    if (-not (Test-WebView2)) {  # the exit code can say success with nothing installed, so the registry decides
        Write-Warning "WebView2 isn't installed (installer exit code: $($setup.ExitCode)): PrestCribe will open in your browser instead."
    }
}

if (-not $NoShortcut) {  # on the desktop, and in the Start menu, so searching Start for PrestCribe finds it
    # The shortcut's app ID is the one the window sets (backend/serve.py), so pinning the window pins this shortcut, not Python
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class PrestCribeAppId {
    [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IPropertyStore {
        int GetCount(out uint count); int GetAt(uint index, out PropertyKey key); int GetValue(ref PropertyKey key, out PropVariant value);
        int SetValue(ref PropertyKey key, ref PropVariant value); int Commit();
    }
    [StructLayout(LayoutKind.Sequential, Pack = 4)] struct PropertyKey { public Guid FormatId; public uint PropertyId; }
    [StructLayout(LayoutKind.Explicit, Size = 16)] struct PropVariant { [FieldOffset(0)] public ushort Type; [FieldOffset(8)] public IntPtr Text; }
    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    static extern int SHGetPropertyStoreFromParsingName(string path, IntPtr context, int flags, ref Guid iid, out IPropertyStore store);
    public static void Set(string shortcut, string id) {
        Guid iid = typeof(IPropertyStore).GUID;
        IPropertyStore store;
        Marshal.ThrowExceptionForHR(SHGetPropertyStoreFromParsingName(shortcut, IntPtr.Zero, 2, ref iid, out store));  // GPS_READWRITE
        PropertyKey key = new PropertyKey { FormatId = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), PropertyId = 5 };  // System.AppUserModel.ID
        PropVariant value = new PropVariant { Type = 31, Text = Marshal.StringToCoTaskMemUni(id) };  // VT_LPWSTR
        try { Marshal.ThrowExceptionForHR(store.SetValue(ref key, ref value)); Marshal.ThrowExceptionForHR(store.Commit()); }
        finally { Marshal.FreeCoTaskMem(value.Text); Marshal.ReleaseComObject(store); }
    }
}
'@
    foreach ($place in "Desktop", "Programs") {
        $path = Join-Path ([Environment]::GetFolderPath($place)) "PrestCribe.lnk"
        $link = (New-Object -ComObject WScript.Shell).CreateShortcut($path)
        $link.TargetPath = $uvw
        $link.Arguments = "run prestcribe"
        $link.WorkingDirectory = $Folder
        $link.Description = "Start PrestCribe"
        $link.IconLocation = Join-Path $Folder "frontend\dist\favicon.ico"
        $link.Save()
        try { [PrestCribeAppId]::Set($path, "PrestCribe") } catch { Write-Warning "Pinning PrestCribe to the taskbar may show Python's icon: $_" }
    }
    Write-Host "Added PrestCribe to your desktop and Start menu."
}

if (-not ((Get-Command claude -ErrorAction SilentlyContinue) -or (Get-Command codex -ErrorAction SilentlyContinue))) {
    Write-Warning "Reading pages needs Claude Code or the Codex CLI installed and signed in. PrestCribe's Settings page shows how."
}
Write-Host "PrestCribe is installed in $Folder."
if (-not $NoStart) {
    Start-Process $uvw -ArgumentList "run", "prestcribe" -WorkingDirectory $Folder
}
