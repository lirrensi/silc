@echo off
setlocal
echo __SILC_BEGIN_%2__
call %1
echo __SILC_END_%2__:%ERRORLEVEL%
