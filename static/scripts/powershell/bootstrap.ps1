$script:SilcEsc = [char]0x1b

$script:SilcOriginalPrompt = $null
if (Test-Path function:prompt) {
    $script:SilcOriginalPrompt = (Get-Item function:prompt).ScriptBlock
}

function global:__silc_emit_cwd {
    $cwd = [System.Uri]::EscapeDataString((Get-Location).Path)
    [Console]::Out.Write("$script:SilcEsc]633;cwd=$cwd$script:SilcEsc\")
}

function global:prompt {
    __silc_emit_cwd
    if ($null -ne $script:SilcOriginalPrompt) {
        & $script:SilcOriginalPrompt
    } else {
        "PS $($PWD.Path)> "
    }
}

function global:__silc_render_prompt {
    if ($null -ne $script:SilcOriginalPrompt) {
        & $script:SilcOriginalPrompt
    } else {
        "PS $($PWD.Path)> "
    }
}

function global:__silc_exec($cmd, $token) {
    __silc_render_prompt
    [Console]::Out.WriteLine($cmd)
    [Console]::Out.WriteLine("__SILC_BEGIN_${token}__")
    Invoke-Expression $cmd
    $exitCode = $LASTEXITCODE
    if ($null -eq $exitCode) { $exitCode = 0 }
    [Console]::Out.WriteLine("__SILC_END_${token}__:$exitCode")
}

__silc_emit_cwd
