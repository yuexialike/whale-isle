@echo off
rem Read-only: list USB / serial devices Windows can see. Nothing is written to the device.
rem Result -> data\usb.txt
cd /d "%~dp0"
powershell -NoProfile -Command "$ErrorActionPreference='SilentlyContinue'; Get-PnpDevice -PresentOnly | Where-Object { $_.Class -in @('Ports','USB','AndroidUsbDeviceClass','Net') } | Select-Object Status,Class,FriendlyName,InstanceId | Sort-Object Class,FriendlyName | Format-Table -AutoSize | Out-String -Width 220" > data\usb.txt 2>&1
powershell -NoProfile -Command "'--- serial ports ---'; [System.IO.Ports.SerialPort]::GetPortNames()" >> data\usb.txt 2>&1
powershell -NoProfile -Command "'--- usb hubs (tree) ---'; Get-PnpDevice -PresentOnly -Class USB | ForEach-Object { $_.FriendlyName }" >> data\usb.txt 2>&1
