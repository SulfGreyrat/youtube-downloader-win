# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: build with `pyinstaller build.spec`

from PyInstaller.utils.hooks import collect_data_files

# CustomTkinter ships its theme JSON + assets as package data; they must be
# bundled or the frozen app crashes on import.
ctk_datas = collect_data_files('customtkinter')

a = Analysis(
    ['src/main.py'],
    pathex=['src'],
    binaries=[],
    datas=ctk_datas,
    hiddenimports=['gui', 'downloader', 'customtkinter'],
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
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
