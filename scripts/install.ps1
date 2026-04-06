Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Repo = if ($env:SILC_REPO) { $env:SILC_REPO } else { 'lirrensi/silc' }
$InstallDir = if ($env:SILC_INSTALL_DIR) { $env:SILC_INSTALL_DIR } else { Join-Path $HOME 'bin' }

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

$arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant()
switch ($arch) {
    'x64' { $asset = 'silc-windows-x86_64.exe' }
    default { throw "Unsupported Windows architecture: $arch" }
}

$url = "https://github.com/$Repo/releases/latest/download/$asset"
$target = Join-Path $InstallDir 'silc.exe'
$tempFile = "$target.tmp"

Invoke-WebRequest -Uri $url -OutFile $tempFile
Move-Item -Force $tempFile $target

$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($userPath -notlike "*$InstallDir*") {
    [Environment]::SetEnvironmentVariable('Path', "$userPath;$InstallDir", 'User')
}

if (-not ($env:Path -like "*$InstallDir*")) {
    $env:Path = "$InstallDir;$env:Path"
}

Write-Host "Installed SILC to $target"
