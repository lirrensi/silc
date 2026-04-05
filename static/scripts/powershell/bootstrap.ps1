Set-StrictMode -Version Latest

$script:SilcEsc = [char]0x1b

function global:__silc_emit_cwd {
    $cwd = [System.Uri]::EscapeDataString((Get-Location).Path)
    [Console]::Out.Write("$script:SilcEsc]633;cwd=$cwd$script:SilcEsc\")
}

function global:prompt {
    __silc_emit_cwd
    "PS $($PWD.Path)> "
}

function global:__silc_exec($cmd, $token) {
    $prompt = "PS $($PWD.Path)> "
    [Console]::Out.Write($prompt)
    [Console]::Out.WriteLine($cmd)
    [Console]::Out.WriteLine("__SILC_BEGIN_${token}__")
    Invoke-Expression $cmd
    $exitCode = $LASTEXITCODE
    if ($null -eq $exitCode) { $exitCode = 0 }
    [Console]::Out.WriteLine("__SILC_END_${token}__:$exitCode")
}

__silc_emit_cwd
