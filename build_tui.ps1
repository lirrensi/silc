Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RootDir = Split-Path -Parent $PSCommandPath
$TuiDir = Join-Path $RootDir 'tui_client'
$DistDir = Join-Path $TuiDir 'dist'
$Target = 'x86_64-pc-windows-gnu'
$SourceBinary = Join-Path $TuiDir "target\$Target\release\silc-tui.exe"
$DistBinary = Join-Path $DistDir 'silc-tui-windows.exe'

function Get-MingwGccPath {
    $candidates = @(
        'C:\msys64\mingw64\bin\gcc.exe',
        'C:\msys64\ucrt64\bin\gcc.exe',
        'C:\msys64\clang64\bin\gcc.exe'
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return (Resolve-Path $candidate).Path
        }
    }

    $cmd = Get-Command gcc -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -like '*msys64*') {
        return $cmd.Source
    }

    $cmd = Get-Command x86_64-w64-mingw32-gcc -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    return $null
}

New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

$GccPath = Get-MingwGccPath
if (-not $GccPath) {
    throw 'MinGW gcc not found. Install MSYS2/MinGW64 and ensure gcc.exe is available.'
}

$env:CARGO_TARGET_X86_64_PC_WINDOWS_GNU_LINKER = $GccPath
$mingwBin = Split-Path -Parent $GccPath
if ($env:PATH -notlike "*$mingwBin*") {
    $env:PATH = "$mingwBin;$env:PATH"
}

Push-Location $TuiDir
try {
    rustup target add $Target | Out-Null

    Write-Host "Building silc-tui for target: $Target"
    cargo build --release --target $Target

    if (-not (Test-Path $SourceBinary)) {
        throw "expected binary at $SourceBinary, build failed?"
    }

    Copy-Item $SourceBinary $DistBinary -Force
    Write-Host "Copied $SourceBinary -> $DistBinary"
}
finally {
    Pop-Location
}
