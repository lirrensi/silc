@echo off
setlocal EnableExtensions EnableDelayedExpansion
prompt $E]633;cwd=$P$E\$P$G
doskey __silc_exec=call "%~dp0__silc_exec.bat" $1 $2
