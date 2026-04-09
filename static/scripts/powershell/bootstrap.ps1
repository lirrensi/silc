$script:SilcEsc = [char]0x1b

$script:SilcOriginalPrompt = $null
if (Test-Path function:prompt) {
    $script:SilcOriginalPrompt = (Get-Item function:prompt).ScriptBlock
}

function global:__silc_emit_cwd {
    $cwd = [System.Uri]::EscapeDataString((Get-Location).Path)
    [Console]::Out.Write("$script:SilcEsc]633;cwd=$cwd$script:SilcEsc\")
}

function global:__silc_emit_command($command) {
    if ([string]::IsNullOrWhiteSpace($command)) {
        return
    }

    if ($command -like '__silc_*') {
        return
    }

    [Console]::Out.Write("$script:SilcEsc]633;cmd=$command$script:SilcEsc\")
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
    [Console]::Out.WriteLine("__SILC_BEGIN_${token}__")
    Invoke-Expression $cmd
    $exitCode = $LASTEXITCODE
    if ($null -eq $exitCode) { $exitCode = 0 }
    [Console]::Out.WriteLine("__SILC_END_${token}__:$exitCode")
}

if (Get-Command Set-PSReadLineOption -ErrorAction SilentlyContinue) {
    try {
        Set-PSReadLineOption -CommandValidationHandler {
            param($CommandAst)

            if ($null -ne $CommandAst) {
                __silc_emit_command $CommandAst.Extent.Text
            }
        }
        Set-PSReadLineKeyHandler -Chord Enter -Function ValidateAndAcceptLine
    } catch {
        $null = $true
    }
}

__silc_emit_cwd
