# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['tools\\level_design_studio.py'],
    pathex=[],
    binaries=[],
    datas=[('tools/game_profiles.json', '.')],
    hiddenimports=['PIL', 'PIL.Image', 'PIL._imagingtk', 'numpy', 'tkinter', 'sklearn', 'sklearn.cluster', 'sklearn.cluster._kmeans', 'sqlite3', 'ultralytics', 'ultralytics.nn', 'ultralytics.nn.tasks', 'ultralytics.models', 'ultralytics.models.yolo', 'ultralytics.models.yolo.classify', 'ultralytics.utils', 'torch', 'torchvision', 'cv2', 'diffusers', 'transformers', 'accelerate', 'diffusers.pipelines', 'diffusers.models', 'diffusers.schedulers', 'transformers.models', 'safetensors'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'pandas', 'tensorboard'],
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
    name='LevelDesignStudio',
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
