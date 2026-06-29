# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['E:\\AI\\virtual_player\\tools\\level_design_extractor_gui.py'],
    pathex=[],
    binaries=[],
    datas=[('E:\\AI\\virtual_player\\tools\\game_profiles.json', '.')],
    hiddenimports=['PIL', 'PIL._imagingtk', 'PIL.Image', 'numpy', 'ultralytics', 'ultralytics.nn', 'ultralytics.nn.tasks', 'ultralytics.models', 'ultralytics.models.yolo', 'ultralytics.models.yolo.classify', 'ultralytics.utils', 'torch', 'torchvision', 'cv2', 'base64', 'concurrent.futures', 'hashlib', 'io'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'scipy', 'pandas', 'IPython', 'jupyter', 'notebook', 'tensorboard'],
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
    name='LevelDesignExtractor',
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
