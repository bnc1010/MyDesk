# stop_viewer.ps1 -- used by stop_viewer.bat. ASCII only (PowerShell 5.1 reads
# BOM-less files as the system ANSI codepage, so non-ASCII text would garble).
$ErrorActionPreference = 'SilentlyContinue'
$procs = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'"
$targets = $procs | Where-Object { $_.CommandLine -match 'watch\.py|viewer\.py' }
if (-not $targets) {
    Write-Host '[stop] no viewer/watchdog process found'
    exit 0
}
foreach ($p in $targets) {
    Write-Host ('[stop] killing pid ' + $p.ProcessId + ' : ' + $p.CommandLine)
    Stop-Process -Id $p.ProcessId -Force
}
Write-Host '[stop] done. It will not restart unless someone runs start_viewer.bat again.'
