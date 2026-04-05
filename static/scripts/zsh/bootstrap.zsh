setopt prompt_subst

__silc_emit_cwd() {
  printf '\033]633;cwd=%s\033\\' "$PWD"
}

autoload -Uz add-zsh-hook 2>/dev/null
if (( $+functions[add-zsh-hook] )); then
  add-zsh-hook precmd __silc_emit_cwd
else
  precmd_functions+=(__silc_emit_cwd)
fi

__silc_exec() {
  printf '__SILC_BEGIN_%s__\n' "$2"
  eval "$1"
  printf '__SILC_END_%s__:%d\n' "$2" "$?"
}

__silc_emit_cwd
