# FILE: scripts/install-source.ps1
# PURPOSE: Build a repo-like source tree, populate tui_client/dist, and install SILC from an editable checkout.
# OWNS: Windows source-bootstrap install flow for local checkout and downloaded source tarball modes.
# EXPORTS: none - executable bootstrap script.
# DOCS: agent_chat/plan_zip_distribution_2026-04-10.md, docs/arch_tui.md, README.md

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Repo = if ($env:SILC_REPO) { $env:SILC_REPO } else { 'lirrensi/silc' }
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$LocalRoot = Split-Path -Parent $ScriptRoot
$DefaultRoot = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'SILC\source-installs'
$InstallRoot = if ($env:SILC_INSTALL_ROOT) { $env:SILC_INSTALL_ROOT } else { $DefaultRoot }

function Resolve-TuiAssetName {
    $arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant()
    switch ($arch) {
        'x64' { return 'silc-tui-windows-x86_64.exe' }
        default { throw "Unsupported Windows architecture: $arch" }
    }
}

if ((Test-Path (Join-Path $LocalRoot 'pyproject.toml')) -and (Test-Path (Join-Path $LocalRoot 'silc')) -and (Test-Path (Join-Path $LocalRoot 'manager_web_ui'))) {
    $SourceTree = $LocalRoot
}
else {
    $Stamp = Get-Date -Format 'yyyyMMddHHmmss'
    $TargetRoot = Join-Path $InstallRoot $Stamp
    $ArchivePath = Join-Path $TargetRoot 'source.tar.gz'
    $ExtractRoot = Join-Path $TargetRoot 'unpacked'
    New-Item -ItemType Directory -Force -Path $ExtractRoot | Out-Null
    Invoke-WebRequest -Uri "https://api.github.com/repos/$Repo/tarball" -OutFile $ArchivePath
    $SourceTree = python -c "import sys, tarfile; from pathlib import Path; archive_path = Path(sys.argv[1]); extract_root = Path(sys.argv[2]);
with tarfile.open(archive_path, 'r:gz') as archive:
    archive.extractall(extract_root)
entries = [path.resolve() for path in extract_root.iterdir() if path.is_dir()]
if len(entries) != 1:
    raise SystemExit(f'Expected one extracted source directory, found {len(entries)}')
print(entries[0])" $ArchivePath $ExtractRoot
}

Push-Location $SourceTree
try {
    python -m silc.utils.build_web
}
finally {
    Pop-Location
}

$TuiAssetName = Resolve-TuiAssetName
$TuiDistDir = Join-Path $SourceTree 'tui_client\dist'
$TuiBinaryPath = Join-Path $TuiDistDir 'silc-tui.exe'
New-Item -ItemType Directory -Force -Path $TuiDistDir | Out-Null
Invoke-WebRequest -Uri "https://github.com/$Repo/releases/latest/download/$TuiAssetName" -OutFile $TuiBinaryPath

uv tool install --force --editable $SourceTree

Write-Host "Source tree: $SourceTree"
Write-Host "Native TUI path: $TuiBinaryPath"
