$WshShell = New-Object -ComObject WScript.Shell
$Desktop = [Environment]::GetFolderPath('Desktop')
$LinkPath = Join-Path $Desktop 'YouTube Downloader.lnk'
$Shortcut = $WshShell.CreateShortcut($LinkPath)
$Shortcut.TargetPath = 'D:\Hermes\youtube-downloader-win\dist\YouTubeDownloader.exe'
$Shortcut.WorkingDirectory = 'D:\Hermes\youtube-downloader-win\dist'
$Shortcut.Description = 'YouTube Downloader'
$Shortcut.Save()
Write-Output "Shortcut created at: $LinkPath"
Test-Path $LinkPath
