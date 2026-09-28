# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the background download agent (no window, no console).
# Build with: pyinstaller server.spec

from PyInstaller.utils.hooks import collect_all

datas, binaries, hidden = [], [], []
for pkg in ('yt_dlp', 'yt_dlp_ejs'):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hidden += h

a = Analysis(
    ['src/server_agent.py'],
    pathex=['src'],
    binaries=binaries,
    datas=datas,
    hiddenimports=['config', 'downloader', 'stats'] + hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'customtkinter', 'PIL'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='YouTubeDownloaderAgent',
    icon='assets/icon.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
