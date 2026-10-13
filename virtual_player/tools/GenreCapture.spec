# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_submodules

datas = [('E:\\AI\\virtual_player\\tools\\capture', 'capture')]
hiddenimports = ['PIL', 'PIL.Image', 'PIL.ImageTk', 'numpy', 'pytesseract', 'certifi', 'ssl', 'ctypes', 'ctypes.wintypes', 'zipfile', 'urllib.request', 'urllib.error', 'tkinter', 'tkinter.ttk', 'tkinter.filedialog', 'tkinter.messagebox']
datas += collect_data_files('certifi')
hiddenimports += collect_submodules('PIL')


a = Analysis(
    ['E:\\AI\\virtual_player\\tools\\genre_capture_entry.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'tensorflow', 'paddle', 'paddleocr', 'easyocr', 'ultralytics', 'matplotlib', 'scipy', 'cv2', 'pandas', 'IPython', 'jupyter'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='GenreCapture',
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
