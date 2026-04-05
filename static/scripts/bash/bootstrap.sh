__silc_emit_cwd() {
  printf '\033]633;cwd=%s\033\\' "$PWD"
}

__silc_exec() {
  printf '__SILC_BEGIN_%s__\n' "$2"
  eval "$1"
  printf '__SILC_END_%s__:%d\n' "$2" "$?"
}

if [ -n "${PROMPT_COMMAND-}" ]; then
  PROMPT_COMMAND="__silc_emit_cwd; ${PROMPT_COMMAND}"
else
  PROMPT_COMMAND="__silc_emit_cwd"
fi

__silc_emit_cwd
