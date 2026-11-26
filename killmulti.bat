@echo off
rem Kill our body instances by window title (only windows titled "python").
taskkill /F /FI "WINDOWTITLE eq python"
echo.
echo ==== left ====
tasklist /FI "IMAGENAME eq python.exe"
pause
