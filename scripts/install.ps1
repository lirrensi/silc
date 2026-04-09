# FILE: scripts/install.ps1
# PURPOSE: Download the latest repo-mirror release zip and install SILC from an editable unpacked tree.
# OWNS: Windows zip-bootstrap install flow for GitHub-hosted release assets.
# EXPORTS: none - executable bootstrap script.
# DOCS: agent_chat/plan_zip_distribution_2026-04-10.md, docs/arch_tui.md, README.md

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Repo = if ($env:SILC_REPO) { $env:SILC_REPO } else { 'lirrensi/silc' }
$DefaultRoot = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'SILC\releases'
$InstallRoot = if ($env:SILC_INSTALL_ROOT) { $env:SILC_INSTALL_ROOT } else { $DefaultRoot }

function Resolve-ZipAssetName {
    $arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant()
    switch ($arch) {
        'x64' { return 'silc-windows-x86_64.zip' }
        default { throw "Unsupported Windows architecture: $arch" }
    }
}

$AssetName = Resolve-ZipAssetName
$Stamp = Get-Date -Format 'yyyyMMddHHmmss'
$TargetRoot = Join-Path $InstallRoot $Stamp
$ArchivePath = Join-Path $TargetRoot $AssetName
$ExtractRoot = Join-Path $TargetRoot 'unpacked'

New-Item -ItemType Directory -Force -Path $ExtractRoot | Out-Null
Invoke-WebRequest -Uri "https://github.com/$Repo/releases/latest/download/$AssetName" -OutFile $ArchivePath

$RepoTree = python -c "import sys, zipfile; from pathlib import Path; archive_path = Path(sys.argv[1]); extract_root = Path(sys.argv[2]);
with zipfile.ZipFile(archive_path) as archive:
    archive.extractall(extract_root)
candidates = []
for pyproject in extract_root.rglob('pyproject.toml'):
    parent = pyproject.parent
    if (parent / 'silc').is_dir() and (parent / 'manager_web_ui').is_dir():
        candidates.append(parent.resolve())
if len(candidates) != 1:
    raise SystemExit(f'Expected one unpacked repo tree, found {len(candidates)}')
print(candidates[0])" $ArchivePath $ExtractRoot

uv tool install --force --editable $RepoTree

Write-Host "Unpacked SILC tree: $RepoTree"
Write-Host "Native TUI path: $(Join-Path $RepoTree 'tui_client\dist\silc-tui.exe')"
