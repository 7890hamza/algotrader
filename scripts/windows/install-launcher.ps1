# Puts an "AlgoTrader" icon on your desktop (and in the Start menu) that opens the launcher window.
#   powershell -ExecutionPolicy Bypass -File scripts\windows\install-launcher.ps1
$Root = (Resolve-Path "$PSScriptRoot\..\..").Path
$Launcher = "$PSScriptRoot\AlgoTrader.ps1"

# icon from the app's logo
$Ico = "$Root\config\algotrader.ico"
try {
  Add-Type -AssemblyName System.Drawing
  $png = [System.Drawing.Bitmap]::FromFile("$Root\frontend\public\logo.png")
  $bmp = New-Object System.Drawing.Bitmap $png, 256, 256
  $icon = [System.Drawing.Icon]::FromHandle($bmp.GetHicon())
  $fs = [System.IO.File]::Create($Ico); $icon.Save($fs); $fs.Close(); $png.Dispose()
} catch { $Ico = "$env:SystemRoot\System32\shell32.dll,13" }

$shell = New-Object -ComObject WScript.Shell
foreach ($dir in @([Environment]::GetFolderPath("Desktop"), "$env:APPDATA\Microsoft\Windows\Start Menu\Programs")) {
  $lnk = $shell.CreateShortcut("$dir\AlgoTrader.lnk")
  $lnk.TargetPath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
  $lnk.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Launcher`""
  $lnk.WorkingDirectory = $Root
  $lnk.IconLocation = $Ico
  $lnk.Description = "Start, watch and stop AlgoTrader"
  $lnk.Save()
}
Write-Host "Done. Double-click 'AlgoTrader' on your desktop (also in the Start menu)."
