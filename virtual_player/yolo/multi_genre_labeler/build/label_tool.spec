# PyInstaller spec for Multi-Genre Label Editor.
# Build:  pyinstaller --clean build/label_tool.spec
# Output: dist/LabelEditor.exe (single file)

from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

SPEC_DIR = Path(SPECPATH).resolve()        # build/
PROJECT_DIR = SPEC_DIR.parent              # multi_genre_labeler/
ENTRY = PROJECT_DIR / "label_editor.py"
CLASSES = PROJECT_DIR / "classes"

# Bundle classes/{genre}.txt as data
datas = [(str(CLASSES), "classes")]

hidden = collect_submodules("PySide6.QtCore") + \
         collect_submodules("PySide6.QtGui") + \
         collect_submodules("PySide6.QtWidgets")

block_cipher = None

a = Analysis(
    [str(ENTRY)],
    pathex=[str(PROJECT_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "torch", "cv2", "ultralytics"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="LabelEditor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
