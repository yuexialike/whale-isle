@echo off
setlocal
rem 2026-11-21: start from THIS folder, not D:\fish\home.
rem Why: D:\fish\home kept an 11-04 config.json (qq 8080, no daily plugin, ears on).
rem This file used to copy *.py there but never overwrote an existing config, so a
rem double-click started "new code + old config" and qq fought Coop for 8080.
rem Running in place uses this folder's code and this folder's config; no copy step.
rem NOTE: keep this file pure ASCII. cmd.exe reads .bat in the system codepage and
rem UTF-8 Chinese comments in here broke it twice (2026-11-04 17:53).
set SRC=%~dp0
cd /d "%SRC%"
set PY=%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe
if not exist "%PY%" set PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe
rem 2026-11-04 18:24: do NOT redirect here. The child inherits the handle and keeps
rem launch.log open for its whole life, so the NEXT run of this bat dies with a
rem sharing violation before it ever starts anything. main.py points stdout/stderr
rem at data\stdout.log when pythonw gives it None, so a bare start is correct.
start "" "%PY%" "%SRC%main.py"
