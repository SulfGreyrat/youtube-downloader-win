$WshShell = New-Object -ComObject WScript.Shell
$Desktop = [Environment]::GetFolderPath('Desktop')
$Programs = [Environment]::GetFolderPath('Programs')
$Exe = 'D:\Hermes\youtube-downloader-win\dist\YouTubeDownloader.exe'
foreach ($dir in @($Desktop, $Programs)) {
    $LinkPath = Join-Path $dir 'YouTube Downloader.lnk'
    $Shortcut = $WshShell.CreateShortcut($LinkPath)
    $Shortcut.TargetPath = $Exe
    $Shortcut.WorkingDirectory = 'D:\Hermes\youtube-downloader-win\dist'
    $Shortcut.IconLocation = "$Exe,0"
    $Shortcut.Description = 'YT Downloader'
    $Shortcut.Save()
    Write-Output "Shortcut: $LinkPath"
}
# refresh Explorer icon cache so the new icon shows immediately
ie4uinit.exe -show
