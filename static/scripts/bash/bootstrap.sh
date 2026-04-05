_silc_bashrc=""
if [ -n "${HOME:-}" ]; then
  _silc_bashrc="${HOME}/.bashrc"
elif [ -n "${USERPROFILE:-}" ]; then
  _silc_bashrc="${USERPROFILE}/.bashrc"
fi

_silc_source_if_readable() {
  if [ -n "$1" ] && [ -r "$1" ]; then
    # shellcheck source=/dev/null
    . "$1"
  fi
}

if shopt -q login_shell; then
  _silc_source_if_readable /etc/profile
  if [ -n "${HOME:-}" ]; then
    for _silc_profile in \
      "${HOME}/.bash_profile" \
      "${HOME}/.bash_login" \
      "${HOME}/.profile"; do
      if [ -r "$_silc_profile" ]; then
        _silc_source_if_readable "$_silc_profile"
        break
      fi
    done
  elif [ -n "${USERPROFILE:-}" ]; then
    for _silc_profile in \
      "${USERPROFILE}/.bash_profile" \
      "${USERPROFILE}/.bash_login" \
      "${USERPROFILE}/.profile"; do
      if [ -r "$_silc_profile" ]; then
        _silc_source_if_readable "$_silc_profile"
        break
      fi
    done
  fi
  _silc_source_if_readable /etc/bash.bashrc
  _silc_source_if_readable /etc/bashrc
  if [ -n "$_silc_bashrc" ] && [ -r "$_silc_bashrc" ]; then
    _silc_source_if_readable "$_silc_bashrc"
  fi
else
  _silc_source_if_readable /etc/bash.bashrc
  _silc_source_if_readable /etc/bashrc
  if [ -n "$_silc_bashrc" ] && [ -r "$_silc_bashrc" ]; then
    _silc_source_if_readable "$_silc_bashrc"
  fi
fi
unset _silc_bashrc

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
