# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['E:\\AI\\virtual_player\\tester\\pipeline\\main.py'],
    pathex=['E:\\AI\\virtual_player'],
    binaries=[],
    datas=[('E:\\AI\\virtual_player\\tester\\db\\schema.sql', 'tester/db'), ('E:\\AI\\virtual_player\\tools\\game_profiles.json', '.')],
    hiddenimports=['PIL', 'PIL.Image', 'numpy', 'sqlite3', 'tester', 'tester.db', 'tester.db.play_db', 'tester.db.sync_manager', 'tester.pipeline', 'tester.pipeline.ai_player', 'ultralytics', 'ultralytics.nn', 'ultralytics.nn.tasks', 'ultralytics.models', 'ultralytics.models.yolo', 'ultralytics.models.yolo.classify', 'ultralytics.utils', 'torch', 'torchvision', 'cv2'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'scipy', 'pandas', 'IPython', 'jupyter', 'tensorboard'],
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
    name='AIGameTester',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
