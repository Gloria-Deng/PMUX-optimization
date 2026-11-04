@echo off
if exist "%~dp0..\binary\formal\lib\python3.exe" goto bundled
if defined OSS_CAD_SUITE if exist "%OSS_CAD_SUITE%\lib\python3.exe" goto suite
python -B -X utf8 %*
exit /b %errorlevel%
:bundled
"%~dp0..\binary\formal\lib\python3.exe" -B -X utf8 %*
exit /b %errorlevel%
:suite
"%OSS_CAD_SUITE%\lib\python3.exe" -B -X utf8 %*
exit /b %errorlevel%
