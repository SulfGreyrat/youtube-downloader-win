$WshShell = New-Object -ComObject WScript.Shell
$Startup = [Environment]::GetFolderPath('Startup')
$LinkPath = Join-Path $Startup 'YouTube Downloader Agent.lnk'
$Shortcut = $WshShell.CreateShortcut($LinkPath)
$Shortcut.TargetPath = 'D:\Hermes\youtube-downloader-win\dist\YouTubeDownloaderAgent.exe'
$Shortcut.WorkingDirectory = 'D:\Hermes\youtube-downloader-win\dist'
$Shortcut.Description = 'YouTube Downloader background agent (for the Chrome extension)'
$Shortcut.WindowStyle = 7
$Shortcut.Save()
Write-Output "Startup shortcut created at: $LinkPath"
Test-Path $LinkPath
