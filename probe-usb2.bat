@echo off
rem Read-only: who is VID_3277 (device 200901010001)? Any audio endpoints? Nothing is written to it.
rem Result -> data\usb2.txt
cd /d "%~dp0"
set OUT=data\usb2.txt
powershell -NoProfile -Command "$ErrorActionPreference='SilentlyContinue'; Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like '*VID_3277*' -or $_.InstanceId -like '*VID_0B05*' } | Select-Object Status,Class,FriendlyName,Problem,InstanceId | Format-List | Out-String -Width 240" > "%OUT%" 2>&1
powershell -NoProfile -Command "$ErrorActionPreference='SilentlyContinue'; foreach ($d in (Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like '*VID_3277*' })) { '--- ' + $d.InstanceId; Get-PnpDeviceProperty -InstanceId $d.InstanceId | Where-Object { $_.KeyName -match 'BusReportedDeviceDesc|DeviceDesc|Manufacturer|HardwareIds|CompatibleIds' } | ForEach-Object { $_.KeyName + ' = ' + ($_.Data -join ',') } }" >> "%OUT%" 2>&1
powershell -NoProfile -Command "$ErrorActionPreference='SilentlyContinue'; '=== audio endpoints ==='; Get-PnpDevice -PresentOnly -Class AudioEndpoint | Select-Object Status,FriendlyName | Format-Table -AutoSize | Out-String -Width 240; '=== media ==='; Get-PnpDevice -PresentOnly -Class MEDIA | Select-Object Status,FriendlyName | Format-Table -AutoSize | Out-String -Width 240; '=== all usb devices now ==='; Get-PnpDevice -PresentOnly -Class USB,USBDevice,Ports | Select-Object Status,Class,FriendlyName | Format-Table -AutoSize | Out-String -Width 240" >> "%OUT%" 2>&1
echo done >> "%OUT%"
