# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: build with `pyinstaller build.spec`

from PyInstaller.utils.hooks import collect_all, collect_data_files

# CustomTkinter ships its theme JSON + assets as package data; yt-dlp-ejs ships
# the JS challenge solver YouTube needs for 1080p+ formats.
datas = collect_data_files('customtkinter') + [('assets', 'assets')]
binaries, hidden = [], []
for pkg in ('yt_dlp', 'yt_dlp_ejs'):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hidden += h

a = Analysis(
    ['src/main.py'],
    pathex=['src'],
    binaries=binaries,
    datas=datas,
    hiddenimports=['gui', 'downloader', 'customtkinter', 'config', 'stats',
                   'queue_manager'] + hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='YouTubeDownloader',
    icon='assets/icon.ico',
    version=None,
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
