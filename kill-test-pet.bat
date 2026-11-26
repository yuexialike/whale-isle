@echo off
rem Close ONLY the test instance (pid in dist\YuYu\data\pid.txt at 14:13 = 48924).
rem Wrote it as a .bat so the pid is exact and I never touch the live pet's process.
taskkill /pid 48924 /f
echo.
pause
