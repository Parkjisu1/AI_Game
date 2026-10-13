"""
Multi-Genre Label Editor — based on virtual_player/yolo/pixelflow/label_editor.py.

Same GUI / shortcuts / modes / save format as the original PixelFlow editor.

Differences from the puzzle-only original:
  * No dependency on _paths.py, auto_label_v2, or cell_aware_analyzer.
  * Starts with a small Genre selector → loads classes/{genre}.txt.
  * No "Auto-Detect Cells" / "YOLO Predict" / "Board Region" menus
    (those are puzzle-specific algorithms that don't apply to SLG/Idle).
  * Everything else — Pascal VOC XML output, classes.txt format, modes,
    shortcuts, undo/redo, mode buttons — is identical so existing puzzle
    labels keep working.

=== Modes ===
  [S] Select  (drag = area select / click = single / handle drag = resize / center drag = move)
  [W] Draw    (drag = new bbox with current class)
  [R] Reclassify  (drag area → all bbox inside become current class)
  [E] Erase   (drag area → all bbox inside deleted)

=== Global ===
  Right-click drag = immediate erase (any mode)

=== Shortcuts ===
  Navigate: D/A           Save: Ctrl+S
  Delete: Del/Backspace   Select all: Ctrl+A
  Duplicate: Ctrl+D       Undo: Ctrl+Z   Redo: Ctrl+Y
  Zoom: +/- / Ctrl+Wheel  Fit: F   1:1: Ctrl+1
  Mode: S/W/R/E           Deselect: Esc
"""
from __future__ import annotations

import sys
import hashlib
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

from PySide6.QtCore import Qt, QRect, QPoint, QSize, Signal
from PySide6.QtGui import (
    QPixmap, QPainter, QPen, QColor, QBrush, QAction, QKeySequence, QFont,
    QCursor, QIcon,
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QListWidget, QFileDialog, QMessageBox, QScrollArea,
    QInputDialog, QStatusBar, QListWidgetItem, QSplitter,
    QCheckBox, QDialog, QFormLayout, QComboBox, QLineEdit, QDialogButtonBox,
)


# ══════════════════════════════════════════════════════════════
#  Paths — bundled classes/{genre}.txt
# ══════════════════════════════════════════════════════════════
def app_dir() -> Path:
    """Return the directory containing classes/ — works for source + PyInstaller."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
    return Path(__file__).resolve().parent


def classes_dir() -> Path:
    return app_dir() / "classes"


GENRES = ["puzzle", "slg", "idle"]


# ══════════════════════════════════════════════════════════════
#  Data Model — same as PixelFlow label_editor
# ══════════════════════════════════════════════════════════════
@dataclass
class BBox:
    name: str
    xmin: int
    ymin: int
    xmax: int
    ymax: int
    selected: bool = False

    def contains(self, x: int, y: int) -> bool:
        return self.xmin <= x <= self.xmax and self.ymin <= y <= self.ymax

    def intersects(self, x0: int, y0: int, x1: int, y1: int) -> bool:
        return not (self.xmax < x0 or self.xmin > x1 or
                    self.ymax < y0 or self.ymin > y1)

    def normalize(self):
        if self.xmin > self.xmax:
            self.xmin, self.xmax = self.xmax, self.xmin
        if self.ymin > self.ymax:
            self.ymin, self.ymax = self.ymax, self.ymin


@dataclass
class Document:
    image_path: Path
    width: int
    height: int
    bboxes: list[BBox] = field(default_factory=list)
    dirty: bool = False

    @classmethod
    def load(cls, image_path: Path, xml_path: Path) -> "Document":
        if not xml_path.exists():
            from PIL import Image as PIL_Image
            with PIL_Image.open(image_path) as im:
                w, h = im.size
            return cls(image_path=image_path, width=w, height=h)

        tree = ET.parse(xml_path)
        root = tree.getroot()
        w = int(root.findtext("size/width", "0"))
        h = int(root.findtext("size/height", "0"))
        if w == 0 or h == 0:
            from PIL import Image as PIL_Image
            with PIL_Image.open(image_path) as im:
                w, h = im.size
        bboxes = []
        for obj in root.findall("object"):
            name = (obj.findtext("name") or "").strip()
            bb = obj.find("bndbox")
            if bb is None:
                continue
            try:
                bboxes.append(BBox(
                    name=name,
                    xmin=int(float(bb.findtext("xmin", "0"))),
                    ymin=int(float(bb.findtext("ymin", "0"))),
                    xmax=int(float(bb.findtext("xmax", "0"))),
                    ymax=int(float(bb.findtext("ymax", "0"))),
                ))
            except ValueError:
                continue
        return cls(image_path=image_path, width=w, height=h, bboxes=bboxes)

    def save(self, xml_path: Path) -> None:
        root = ET.Element("annotation")
        ET.SubElement(root, "folder").text = self.image_path.parent.name
        ET.SubElement(root, "filename").text = self.image_path.name
        ET.SubElement(root, "path").text = str(self.image_path)
        src = ET.SubElement(root, "source")
        ET.SubElement(src, "database").text = "Unknown"
        sz = ET.SubElement(root, "size")
        ET.SubElement(sz, "width").text = str(self.width)
        ET.SubElement(sz, "height").text = str(self.height)
        ET.SubElement(sz, "depth").text = "3"
        ET.SubElement(root, "segmented").text = "0"

        for bb in self.bboxes:
            obj = ET.SubElement(root, "object")
            ET.SubElement(obj, "name").text = bb.name
            ET.SubElement(obj, "pose").text = "Unspecified"
            ET.SubElement(obj, "truncated").text = "0"
            ET.SubElement(obj, "difficult").text = "0"
            box = ET.SubElement(obj, "bndbox")
            ET.SubElement(box, "xmin").text = str(bb.xmin)
            ET.SubElement(box, "ymin").text = str(bb.ymin)
            ET.SubElement(box, "xmax").text = str(bb.xmax)
            ET.SubElement(box, "ymax").text = str(bb.ymax)

        _indent(root)
        ET.ElementTree(root).write(xml_path, encoding="utf-8", xml_declaration=False)
        self.dirty = False

    def snapshot(self) -> list[BBox]:
        return [BBox(**asdict(b)) for b in self.bboxes]


def _indent(elem, level=0):
    i = "\n" + level * "\t"
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "\t"
        for child in elem:
            _indent(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = i
    if not elem.tail or not elem.tail.strip():
        elem.tail = i


# ══════════════════════════════════════════════════════════════
#  Class Colors — same scheme as original label_editor
# ══════════════════════════════════════════════════════════════
# Known puzzle colors (copied from original CLASS_COLORS so puzzle XMLs stay
# visually identical to existing labels).
CLASS_COLORS: dict[str, tuple[int, int, int]] = {
    "block_pink": (252, 106, 175), "block_cyan": (80, 232, 246),
    "block_purple": (137, 80, 248), "block_yellow": (254, 213, 85),
    "block_green": (115, 254, 102), "block_orange": (253, 161, 76),
    "block_white": (240, 240, 240), "block_black": (50, 50, 50),
    "block_blue": (50, 107, 248), "block_red": (252, 94, 94),
    "block_brown": (106, 74, 48),
    "gimmick": (255, 100, 200),
}


def _ensure_color(name: str) -> tuple[int, int, int]:
    if name in CLASS_COLORS:
        return CLASS_COLORS[name]
    h = hashlib.md5(name.encode("utf-8")).digest()
    color = (60 + h[0] % 180, 60 + h[1] % 180, 60 + h[2] % 180)
    CLASS_COLORS[name] = color
    return color


def class_color(name: str) -> QColor:
    r, g, b = _ensure_color(name)
    return QColor(r, g, b)


# ══════════════════════════════════════════════════════════════
#  Modes / Handles — same as original
# ══════════════════════════════════════════════════════════════
MODE_SELECT = "select"
MODE_DRAW = "draw"
MODE_GRID_PAINT = "grid"
MODE_ERASE = "erase"

HANDLE_NONE = 0
HANDLE_TL = 1
HANDLE_TR = 2
HANDLE_BL = 3
HANDLE_BR = 4
HANDLE_T = 5
HANDLE_B = 6
HANDLE_L = 7
HANDLE_R = 8
HANDLE_MOVE = 9

HANDLE_SIZE_PX = 8


# ══════════════════════════════════════════════════════════════
#  Canvas — same as original (with puzzle "board region" mode removed)
# ══════════════════════════════════════════════════════════════
class Canvas(QLabel):
    doc_changed = Signal()
    status_msg = Signal(str)
    snapshot_request = Signal(str)

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self.doc: Optional[Document] = None
        self.pixmap_orig: Optional[QPixmap] = None
        self.zoom: float = 0.6

        self.mode: str = MODE_SELECT
        self.current_class: str = ""

        self._drag_start: Optional[QPoint] = None
        self._drag_end: Optional[QPoint] = None
        self._dragging = False
        self._right_drag = False

        self._edit_target: Optional[BBox] = None
        self._edit_handle: int = HANDLE_NONE
        self._edit_origin: Optional[tuple[int, int, int, int]] = None
        self._edit_mouse_start: Optional[tuple[int, int]] = None

    def set_document(self, doc: Document, pixmap: QPixmap) -> None:
        self.doc = doc
        self.pixmap_orig = pixmap
        self._update_display()

    def set_zoom(self, zoom: float, anchor: Optional[QPoint] = None) -> None:
        self.zoom = max(0.1, min(5.0, zoom))
        self._update_display()

    def fit_to_window(self, view_size: QSize):
        if self.pixmap_orig is None:
            return
        w = view_size.width() - 20
        h = view_size.height() - 20
        if w <= 0 or h <= 0:
            return
        zw = w / self.pixmap_orig.width()
        zh = h / self.pixmap_orig.height()
        self.set_zoom(min(zw, zh))

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self._dragging = False
        self._drag_start = None
        self._drag_end = None
        self._edit_target = None
        self._edit_handle = HANDLE_NONE
        self.status_msg.emit(f"Mode: {mode} (class={self.current_class})")
        self._update_cursor()
        self.update()

    def set_class(self, name: str) -> None:
        self.current_class = name
        self.status_msg.emit(f"Class → {name}")

    def _w2i(self, x: int, y: int) -> tuple[int, int]:
        return int(x / self.zoom), int(y / self.zoom)

    def _i2w(self, x: int, y: int) -> tuple[int, int]:
        return int(x * self.zoom), int(y * self.zoom)

    def _update_display(self) -> None:
        if self.pixmap_orig is None:
            return
        w = int(self.pixmap_orig.width() * self.zoom)
        h = int(self.pixmap_orig.height() * self.zoom)
        self.setFixedSize(w, h)
        self.update()

    def _update_cursor(self):
        if self.mode == MODE_DRAW:
            self.setCursor(Qt.CrossCursor)
        elif self.mode == MODE_ERASE:
            self.setCursor(Qt.ForbiddenCursor)
        elif self.mode == MODE_GRID_PAINT:
            self.setCursor(Qt.PointingHandCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def _hit_handle(self, ix: int, iy: int) -> tuple[Optional[BBox], int]:
        if self.doc is None or self.zoom <= 0:
            return None, HANDLE_NONE
        margin = max(4, int(HANDLE_SIZE_PX / self.zoom))
        selected = [b for b in self.doc.bboxes if b.selected]
        pool = selected if selected else self.doc.bboxes
        for bb in reversed(pool):
            handles = {
                HANDLE_TL: (bb.xmin, bb.ymin),
                HANDLE_TR: (bb.xmax, bb.ymin),
                HANDLE_BL: (bb.xmin, bb.ymax),
                HANDLE_BR: (bb.xmax, bb.ymax),
                HANDLE_T:  ((bb.xmin + bb.xmax) // 2, bb.ymin),
                HANDLE_B:  ((bb.xmin + bb.xmax) // 2, bb.ymax),
                HANDLE_L:  (bb.xmin, (bb.ymin + bb.ymax) // 2),
                HANDLE_R:  (bb.xmax, (bb.ymin + bb.ymax) // 2),
            }
            for h_id, (hx, hy) in handles.items():
                if abs(ix - hx) <= margin and abs(iy - hy) <= margin:
                    return bb, h_id
            if bb.contains(ix, iy):
                return bb, HANDLE_MOVE
        return None, HANDLE_NONE

    def paintEvent(self, event):
        if self.pixmap_orig is None or self.doc is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        scaled = self.pixmap_orig.scaled(
            self.size(), Qt.IgnoreAspectRatio, Qt.FastTransformation
        )
        p.drawPixmap(0, 0, scaled)

        font = QFont("Consolas", max(7, int(8 * self.zoom)))
        p.setFont(font)

        for bb in self.doc.bboxes:
            x0, y0 = self._i2w(bb.xmin, bb.ymin)
            x1, y1 = self._i2w(bb.xmax, bb.ymax)
            color = class_color(bb.name)
            if bb.selected:
                pen = QPen(QColor(255, 255, 0), 2)
                p.fillRect(x0, y0, x1 - x0, y1 - y0, QBrush(QColor(255, 255, 0, 60)))
            else:
                pen = QPen(color, 1)
            p.setPen(pen)
            p.drawRect(x0, y0, x1 - x0, y1 - y0)

            if bb.selected:
                text = bb.name
                fm = p.fontMetrics()
                tw = fm.horizontalAdvance(text) + 8
                th = fm.height() + 4
                tx = x0
                ty = max(0, y0 - th)
                p.fillRect(tx, ty, tw, th, QBrush(QColor(0, 0, 0, 200)))
                p.setPen(QPen(QColor(255, 255, 0), 1))
                p.drawRect(tx, ty, tw, th)
                p.setPen(QPen(QColor(255, 255, 255)))
                p.drawText(tx + 4, ty + fm.ascent() + 2, text)

            if bb.selected and self.mode == MODE_SELECT:
                handles_xy = [
                    (bb.xmin, bb.ymin), (bb.xmax, bb.ymin),
                    (bb.xmin, bb.ymax), (bb.xmax, bb.ymax),
                    ((bb.xmin + bb.xmax) // 2, bb.ymin),
                    ((bb.xmin + bb.xmax) // 2, bb.ymax),
                    (bb.xmin, (bb.ymin + bb.ymax) // 2),
                    (bb.xmax, (bb.ymin + bb.ymax) // 2),
                ]
                p.setBrush(QBrush(QColor(255, 255, 255)))
                p.setPen(QPen(QColor(0, 0, 0), 1))
                for (hx, hy) in handles_xy:
                    wx, wy = self._i2w(hx, hy)
                    p.drawRect(wx - HANDLE_SIZE_PX // 2, wy - HANDLE_SIZE_PX // 2,
                               HANDLE_SIZE_PX, HANDLE_SIZE_PX)

        if self._dragging and self._drag_start and self._drag_end and not self._edit_target:
            rect = QRect(self._drag_start, self._drag_end).normalized()
            if self.mode == MODE_SELECT:
                p.setPen(QPen(QColor(100, 200, 255), 1, Qt.DashLine))
                p.fillRect(rect, QBrush(QColor(100, 200, 255, 40)))
            elif self.mode == MODE_DRAW:
                p.setPen(QPen(QColor(0, 255, 0), 2))
                p.fillRect(rect, QBrush(QColor(0, 255, 0, 40)))
            elif self.mode == MODE_GRID_PAINT:
                p.setPen(QPen(QColor(255, 100, 100), 2, Qt.DashLine))
                p.fillRect(rect, QBrush(QColor(255, 100, 100, 40)))
            elif self.mode == MODE_ERASE:
                p.setPen(QPen(QColor(255, 0, 0), 2, Qt.DashLine))
                p.fillRect(rect, QBrush(QColor(255, 0, 0, 60)))
            if self._right_drag:
                p.setPen(QPen(QColor(255, 0, 0), 2, Qt.DashLine))
                p.fillRect(rect, QBrush(QColor(255, 0, 0, 60)))
            p.drawRect(rect)

    def mousePressEvent(self, event):
        if self.doc is None:
            return
        pos = event.position().toPoint()
        ix, iy = self._w2i(pos.x(), pos.y())

        if event.button() == Qt.RightButton:
            self._drag_start = pos
            self._drag_end = pos
            self._dragging = True
            self._right_drag = True
            return

        if event.button() == Qt.LeftButton:
            self._right_drag = False
            modifier = event.modifiers()
            ctrl_held = bool(modifier & Qt.ControlModifier)

            if self.mode == MODE_SELECT and not ctrl_held:
                target, handle = self._hit_handle(ix, iy)
                if target is not None and handle != HANDLE_NONE:
                    if not target.selected:
                        for bb in self.doc.bboxes:
                            bb.selected = False
                        target.selected = True
                    self.snapshot_request.emit("edit_start")
                    self._edit_target = target
                    self._edit_handle = handle
                    self._edit_origin = (target.xmin, target.ymin, target.xmax, target.ymax)
                    self._edit_mouse_start = (ix, iy)
                    self.update()
                    return

                for bb in self.doc.bboxes:
                    bb.selected = False
                hit = None
                for bb in reversed(self.doc.bboxes):
                    if bb.contains(ix, iy):
                        hit = bb
                        break
                if hit:
                    hit.selected = True
                self.doc_changed.emit()

            self._drag_start = pos
            self._drag_end = pos
            self._dragging = True
            self.update()

    def mouseMoveEvent(self, event):
        if self.doc is None:
            return
        pos = event.position().toPoint()
        ix, iy = self._w2i(pos.x(), pos.y())

        if self._edit_target is not None:
            bb = self._edit_target
            ox0, oy0, ox1, oy1 = self._edit_origin
            mx, my = self._edit_mouse_start
            dx, dy = ix - mx, iy - my
            if self._edit_handle == HANDLE_MOVE:
                bb.xmin = ox0 + dx; bb.ymin = oy0 + dy
                bb.xmax = ox1 + dx; bb.ymax = oy1 + dy
            elif self._edit_handle == HANDLE_TL:
                bb.xmin = ox0 + dx; bb.ymin = oy0 + dy
            elif self._edit_handle == HANDLE_TR:
                bb.xmax = ox1 + dx; bb.ymin = oy0 + dy
            elif self._edit_handle == HANDLE_BL:
                bb.xmin = ox0 + dx; bb.ymax = oy1 + dy
            elif self._edit_handle == HANDLE_BR:
                bb.xmax = ox1 + dx; bb.ymax = oy1 + dy
            elif self._edit_handle == HANDLE_T:
                bb.ymin = oy0 + dy
            elif self._edit_handle == HANDLE_B:
                bb.ymax = oy1 + dy
            elif self._edit_handle == HANDLE_L:
                bb.xmin = ox0 + dx
            elif self._edit_handle == HANDLE_R:
                bb.xmax = ox1 + dx
            bb.normalize()
            self.doc.dirty = True
            self.update()
            return

        if self._dragging:
            self._drag_end = pos
            self.update()
        else:
            if self.mode == MODE_SELECT:
                target, handle = self._hit_handle(ix, iy)
                if handle in (HANDLE_TL, HANDLE_BR):
                    self.setCursor(Qt.SizeFDiagCursor)
                elif handle in (HANDLE_TR, HANDLE_BL):
                    self.setCursor(Qt.SizeBDiagCursor)
                elif handle in (HANDLE_T, HANDLE_B):
                    self.setCursor(Qt.SizeVerCursor)
                elif handle in (HANDLE_L, HANDLE_R):
                    self.setCursor(Qt.SizeHorCursor)
                elif handle == HANDLE_MOVE:
                    self.setCursor(Qt.SizeAllCursor)
                else:
                    self.setCursor(Qt.ArrowCursor)

    def mouseReleaseEvent(self, event):
        if self.doc is None:
            return

        if self._edit_target is not None:
            self._edit_target = None
            self._edit_handle = HANDLE_NONE
            self._edit_origin = None
            self._edit_mouse_start = None
            self.doc_changed.emit()
            self.update()
            return

        if not self._dragging:
            return
        self._drag_end = event.position().toPoint()
        self._dragging = False

        start = self._drag_start
        end = self._drag_end
        if start is None or end is None:
            return

        x0, y0 = self._w2i(min(start.x(), end.x()), min(start.y(), end.y()))
        x1, y1 = self._w2i(max(start.x(), end.x()), max(start.y(), end.y()))
        w_pix = abs(end.x() - start.x())
        h_pix = abs(end.y() - start.y())

        if w_pix < 4 and h_pix < 4:
            self._drag_start = None
            self._drag_end = None
            self._right_drag = False
            self.update()
            return

        if self._right_drag:
            self.snapshot_request.emit("right_erase")
            before = len(self.doc.bboxes)
            self.doc.bboxes = [
                bb for bb in self.doc.bboxes if not bb.intersects(x0, y0, x1, y1)
            ]
            removed = before - len(self.doc.bboxes)
            if removed > 0:
                self.doc.dirty = True
                self.doc_changed.emit()
                self.status_msg.emit(f"[우클릭] Erased {removed} bbox")
            self._drag_start = None
            self._drag_end = None
            self._right_drag = False
            self.update()
            return

        if self.mode == MODE_SELECT:
            for bb in self.doc.bboxes:
                if bb.intersects(x0, y0, x1, y1):
                    bb.selected = True
            count = sum(1 for b in self.doc.bboxes if b.selected)
            self.status_msg.emit(f"{count} bbox selected")
            self.doc_changed.emit()
        elif self.mode == MODE_DRAW:
            if not self.current_class:
                self.status_msg.emit("클래스를 먼저 선택하세요.")
            else:
                self.snapshot_request.emit("draw")
                self.doc.bboxes.append(BBox(
                    name=self.current_class, xmin=x0, ymin=y0, xmax=x1, ymax=y1,
                ))
                self.doc.dirty = True
                self.doc_changed.emit()
                self.status_msg.emit(f"Added: {self.current_class}")
        elif self.mode == MODE_GRID_PAINT:
            self.snapshot_request.emit("grid_paint")
            count = 0
            for bb in self.doc.bboxes:
                if bb.intersects(x0, y0, x1, y1):
                    bb.name = self.current_class
                    count += 1
            if count > 0:
                self.doc.dirty = True
                self.doc_changed.emit()
                self.status_msg.emit(f"{count} bbox → {self.current_class}")
        elif self.mode == MODE_ERASE:
            self.snapshot_request.emit("erase")
            before = len(self.doc.bboxes)
            self.doc.bboxes = [
                bb for bb in self.doc.bboxes if not bb.intersects(x0, y0, x1, y1)
            ]
            removed = before - len(self.doc.bboxes)
            if removed > 0:
                self.doc.dirty = True
                self.doc_changed.emit()
                self.status_msg.emit(f"Erased {removed} bbox")

        self._drag_start = None
        self._drag_end = None
        self.update()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            factor = 1.15 if delta > 0 else 1 / 1.15
            self.set_zoom(self.zoom * factor)
            event.accept()
        else:
            super().wheelEvent(event)


# ══════════════════════════════════════════════════════════════
#  Startup dialog — pick genre + image dir + label dir
# ══════════════════════════════════════════════════════════════
class StartupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Label Editor — Session Setup")
        self.setMinimumWidth(560)

        self.classes_file: Optional[Path] = None
        self.image_dir: Optional[Path] = None
        self.label_dir: Optional[Path] = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "<h2>Label Editor — 장르 선택</h2>"
            "<p>장르를 선택하면 해당 classes.txt가 로드됩니다.<br>"
            "이미지 폴더와 라벨 저장 폴더를 지정하세요.</p>"
        ))

        form = QFormLayout()
        layout.addLayout(form)

        # genre
        self.genre_combo = QComboBox()
        for g in GENRES:
            p = classes_dir() / f"{g}.txt"
            n = 0
            if p.exists():
                n = sum(1 for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip())
            self.genre_combo.addItem(f"{g}  ({n} classes)", g)
        self.genre_combo.addItem("Custom classes.txt...", "__custom__")
        self.genre_combo.currentIndexChanged.connect(self._on_genre_changed)
        form.addRow("장르:", self.genre_combo)

        # custom classes
        self.custom_row = QWidget()
        cl = QHBoxLayout(self.custom_row)
        cl.setContentsMargins(0, 0, 0, 0)
        self.custom_edit = QLineEdit()
        self.custom_edit.setPlaceholderText("classes.txt 경로")
        btn_c = QPushButton("Browse...")
        btn_c.clicked.connect(self._pick_custom)
        cl.addWidget(self.custom_edit); cl.addWidget(btn_c)
        form.addRow("커스텀:", self.custom_row)
        self.custom_row.setVisible(False)

        # image dir
        self.img_row = QWidget()
        il = QHBoxLayout(self.img_row); il.setContentsMargins(0, 0, 0, 0)
        self.img_edit = QLineEdit()
        btn_i = QPushButton("Browse...")
        btn_i.clicked.connect(self._pick_img)
        il.addWidget(self.img_edit); il.addWidget(btn_i)
        form.addRow("이미지 폴더:", self.img_row)

        # label dir
        self.lbl_row = QWidget()
        ll = QHBoxLayout(self.lbl_row); ll.setContentsMargins(0, 0, 0, 0)
        self.lbl_edit = QLineEdit()
        btn_l = QPushButton("Browse...")
        btn_l.clicked.connect(self._pick_lbl)
        ll.addWidget(self.lbl_edit); ll.addWidget(btn_l)
        form.addRow("라벨 저장 폴더:", self.lbl_row)

        # buttons
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        # restore last session
        last = _load_last_session()
        if last:
            g = last.get("genre", "")
            for i in range(self.genre_combo.count()):
                if self.genre_combo.itemData(i) == g:
                    self.genre_combo.setCurrentIndex(i)
                    break
            self.custom_edit.setText(last.get("custom_path", ""))
            self.img_edit.setText(last.get("image_dir", ""))
            self.lbl_edit.setText(last.get("label_dir", ""))

    def _on_genre_changed(self, _i):
        self.custom_row.setVisible(self.genre_combo.currentData() == "__custom__")

    def _pick_custom(self):
        p, _ = QFileDialog.getOpenFileName(self, "Pick classes.txt", "", "Text (*.txt)")
        if p:
            self.custom_edit.setText(p)

    def _pick_img(self):
        cur = self.img_edit.text() or str(Path.home())
        d = QFileDialog.getExistingDirectory(self, "Image directory", cur)
        if d:
            self.img_edit.setText(d)
            if not self.lbl_edit.text():
                self.lbl_edit.setText(str(Path(d).parent / "labels"))

    def _pick_lbl(self):
        cur = self.lbl_edit.text() or self.img_edit.text() or str(Path.home())
        d = QFileDialog.getExistingDirectory(self, "Label save dir", cur)
        if d:
            self.lbl_edit.setText(d)

    def _accept(self):
        data = self.genre_combo.currentData()
        if data == "__custom__":
            p = self.custom_edit.text().strip()
            if not p or not Path(p).exists():
                QMessageBox.warning(self, "Invalid", "classes.txt 파일 경로가 잘못되었습니다.")
                return
            self.classes_file = Path(p)
        else:
            self.classes_file = classes_dir() / f"{data}.txt"
            if not self.classes_file.exists():
                QMessageBox.warning(self, "Missing",
                                    f"번들된 classes/{data}.txt 가 없습니다.")
                return
        img = self.img_edit.text().strip()
        if not img or not Path(img).exists():
            QMessageBox.warning(self, "Invalid", "이미지 폴더가 존재하지 않습니다.")
            return
        lbl = self.lbl_edit.text().strip()
        if not lbl:
            QMessageBox.warning(self, "Invalid", "라벨 폴더를 지정하세요.")
            return
        Path(lbl).mkdir(parents=True, exist_ok=True)
        self.image_dir = Path(img)
        self.label_dir = Path(lbl)
        _save_last_session({
            "genre": data,
            "custom_path": self.custom_edit.text(),
            "image_dir": img,
            "label_dir": lbl,
        })
        self.accept()


def _session_file() -> Path:
    import os
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home())) / "label_editor"
    else:
        base = Path.home() / ".config" / "label_editor"
    base.mkdir(parents=True, exist_ok=True)
    return base / "last.json"


def _save_last_session(d: dict):
    import json
    try:
        _session_file().write_text(json.dumps(d, indent=2), encoding="utf-8")
    except Exception:
        pass


def _load_last_session() -> dict:
    import json
    f = _session_file()
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


# ══════════════════════════════════════════════════════════════
#  Main Window — copied from PixelFlow label_editor (auto-detect removed)
# ══════════════════════════════════════════════════════════════
class MainWindow(QMainWindow):
    def __init__(self, image_dir: Path, label_dir: Path, classes_file: Path):
        super().__init__()
        self.setWindowTitle("Label Editor")
        self.resize(1800, 1100)

        self.image_dir = image_dir
        self.label_dir = label_dir
        self.label_dir.mkdir(parents=True, exist_ok=True)
        self.classes_file = classes_file
        self.classes = self._load_classes(classes_file)

        self.images = self._scan_images(image_dir)
        self.current_idx = 0
        self.doc: Optional[Document] = None

        self.undo_stack: list[tuple[str, list[BBox]]] = []
        self.redo_stack: list[tuple[str, list[BBox]]] = []
        self.undo_limit = 50
        self.auto_save = True

        self._build_menubar()
        self._build_ui()
        self._install_shortcuts()
        # Mirror classes.txt next to the labels dir so YOLO export tools find it
        try:
            (self.label_dir / "classes.txt").write_text(
                "\n".join(self.classes) + "\n", encoding="utf-8"
            )
        except Exception:
            pass

        if self.images:
            self._load_index(0)
        # Default-select first class so DRAW mode works immediately
        if self.classes:
            self.class_list.setCurrentRow(0)

    def _scan_images(self, d: Path) -> list[Path]:
        return sorted(
            p for p in d.iterdir()
            if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp"}
        )

    def _load_classes(self, path: Path) -> list[str]:
        if path.exists():
            return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        return []

    def _add_new_class(self):
        name, ok = QInputDialog.getText(self, "New Class", "Class name:")
        if not ok:
            return
        name = name.strip()
        if not name:
            QMessageBox.warning(self, "Invalid", "Class name is empty.")
            return
        if name in self.classes:
            QMessageBox.information(self, "Exists", f"'{name}' already exists.")
            for i in range(self.class_list.count()):
                if self.class_list.item(i).text() == name:
                    self.class_list.setCurrentRow(i)
                    break
            return
        _ensure_color(name)
        self.classes.append(name)
        try:
            existing = ""
            if self.classes_file.exists():
                existing = self.classes_file.read_text(encoding="utf-8")
            if existing and not existing.endswith("\n"):
                existing += "\n"
            self.classes_file.write_text(existing + name + "\n", encoding="utf-8")
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", f"classes.txt write error:\n{e}")
            return
        item = QListWidgetItem(name)
        r, g, b = CLASS_COLORS[name]
        swatch = QPixmap(16, 16)
        swatch.fill(QColor(r, g, b))
        painter = QPainter(swatch)
        painter.setPen(QPen(QColor(0, 0, 0), 1))
        painter.drawRect(0, 0, 15, 15)
        painter.end()
        item.setIcon(QIcon(swatch))
        self.class_list.addItem(item)
        self.class_list.setCurrentItem(item)
        self._set_status(f"Added class: {name}")

    def _build_menubar(self):
        mb = self.menuBar()

        m_file = mb.addMenu("&File")
        m_file.addAction(self._make_action("Open Image Dir...", self._open_image_dir, None))
        m_file.addAction(self._make_action("Change Save Dir...", self._change_save_dir, None))
        m_file.addAction(self._make_action("Open classes.txt...", self._open_classes_file, None))
        m_file.addSeparator()
        m_file.addAction(self._make_action("Save", self._save, "Ctrl+S"))
        m_file.addAction(self._make_action("Save As...", self._save_as, None))
        m_file.addSeparator()
        m_file.addAction(self._make_action("Export to YOLO labels...", self._export_yolo, None))
        m_file.addSeparator()
        m_file.addAction(self._make_action("Exit", self.close, None))

        m_edit = mb.addMenu("&Edit")
        m_edit.addAction(self._make_action("Undo", self._undo, "Ctrl+Z"))
        m_edit.addAction(self._make_action("Redo", self._redo, "Ctrl+Y"))
        m_edit.addSeparator()
        m_edit.addAction(self._make_action("Select All", self._select_all, "Ctrl+A"))
        m_edit.addAction(self._make_action(
            "Select Same Class", self._select_same_class, "Ctrl+Shift+A"))
        m_edit.addAction(self._make_action(
            "Select by Class...", self._select_by_class_prompt, None))
        m_edit.addAction(self._make_action("Duplicate", self._duplicate, "Ctrl+D"))
        m_edit.addAction(self._make_action("Delete", self._delete_selected, "Delete"))
        m_edit.addSeparator()
        m_edit.addAction(self._make_action(
            "Delete All of Class...", self._delete_by_class_prompt, None))

        m_view = mb.addMenu("&View")
        m_view.addAction(self._make_action("Fit to Window", self._fit_window, "F"))
        m_view.addAction(self._make_action("100% (1:1)", self._zoom_100, "Ctrl+1"))
        m_view.addAction(self._make_action("Zoom In", lambda: self._zoom(1.2), "Ctrl++"))
        m_view.addAction(self._make_action("Zoom Out", lambda: self._zoom(1 / 1.2), "Ctrl+-"))

        m_go = mb.addMenu("&Go")
        m_go.addAction(self._make_action("Next Image", self._next_image, "D"))
        m_go.addAction(self._make_action("Prev Image", self._prev_image, "A"))
        m_go.addSeparator()
        m_go.addAction(self._make_action(
            "Trash Current Image", self._trash_current_image, "Ctrl+Shift+X"))

    def _make_action(self, text, handler, shortcut) -> QAction:
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
            a.setShortcutContext(Qt.ApplicationShortcut)
        a.triggered.connect(handler)
        return a

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)

        # Left: image list
        left = QListWidget()
        left.setStyleSheet("""
            QListWidget { background:#fafafa; color:#111; font-size:11px;
                          border:1px solid #cccccc; outline:0; }
            QListWidget::item { padding:4px 6px; }
            QListWidget::item:selected { background:#2a5d9e; color:#ffffff; }
            QListWidget::item:hover { background:#d6e4f5; }
        """)
        left.addItems([p.name for p in self.images])
        left.setMaximumWidth(240)
        left.currentRowChanged.connect(self._on_image_selected)
        self.image_list = left

        # Center: canvas
        self.canvas = Canvas()
        self.canvas.doc_changed.connect(self._on_doc_changed)
        self.canvas.status_msg.connect(self._set_status)
        self.canvas.snapshot_request.connect(self._push_undo)
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.canvas)
        self.scroll.setWidgetResizable(False)

        # Right: panel
        right = QWidget()
        right.setMaximumWidth(280)
        rlayout = QVBoxLayout(right)

        rlayout.addWidget(QLabel("<b>Mode</b>"))
        self.mode_btns = {}
        for key, mode, tip in [
            ("S", MODE_SELECT, "[S] Select / Edit"),
            ("W", MODE_DRAW, "[W] Draw new bbox"),
            ("R", MODE_GRID_PAINT, "[R] Reclassify (bulk)"),
            ("E", MODE_ERASE, "[E] Erase (area delete)"),
        ]:
            b = QPushButton(tip)
            b.setCheckable(True)
            b.clicked.connect(lambda _c=False, m=mode: self._set_mode(m))
            rlayout.addWidget(b)
            self.mode_btns[mode] = b

        self.auto_save_cb = QCheckBox("Auto save on image change")
        self.auto_save_cb.setChecked(True)
        self.auto_save_cb.stateChanged.connect(self._on_autosave_toggle)
        rlayout.addWidget(self.auto_save_cb)

        rlayout.addWidget(QLabel("<b>Class</b>"))
        self.class_list = QListWidget()
        self.class_list.setStyleSheet("""
            QListWidget { background:#fafafa; color:#111; font-size:12px;
                          border:1px solid #cccccc; outline:0; }
            QListWidget::item { padding:5px 6px; border-bottom:1px solid #eeeeee; }
            QListWidget::item:selected { background:#2a5d9e; color:#ffffff; }
            QListWidget::item:hover { background:#d6e4f5; }
        """)
        for c in self.classes:
            r, g, b = _ensure_color(c)
            item = QListWidgetItem(c)
            swatch = QPixmap(16, 16)
            swatch.fill(QColor(r, g, b))
            painter = QPainter(swatch)
            painter.setPen(QPen(QColor(0, 0, 0), 1))
            painter.drawRect(0, 0, 15, 15)
            painter.end()
            item.setIcon(QIcon(swatch))
            self.class_list.addItem(item)
        self.class_list.currentTextChanged.connect(self._on_class_selected)
        rlayout.addWidget(self.class_list)

        btn_new_class = QPushButton("+ New Class")
        btn_new_class.setToolTip("새 클래스 추가 (classes.txt에 저장됨)")
        btn_new_class.setStyleSheet("background:#2e7d32; color:white; padding:6px;")
        btn_new_class.clicked.connect(self._add_new_class)
        rlayout.addWidget(btn_new_class)

        self.current_class_label = QLabel("Current: -")
        self.current_class_label.setStyleSheet("font-weight:bold; padding:4px;")
        rlayout.addWidget(self.current_class_label)

        rlayout.addWidget(QLabel("<b>Selected</b>"))
        self.selection_info = QLabel("-")
        self.selection_info.setWordWrap(True)
        self.selection_info.setStyleSheet(
            "padding:6px; background:#f0f0f0; border:1px solid #ccc; font-size:11px;"
        )
        rlayout.addWidget(self.selection_info)

        rlayout.addWidget(QLabel("<b>Image</b>"))
        btn_trash = QPushButton("Trash This Image (Ctrl+Shift+X)")
        btn_trash.setToolTip("현재 이미지를 images_trash/로 이동")
        btn_trash.setStyleSheet("background:#c44a4a; color:white; padding:6px;")
        btn_trash.clicked.connect(self._trash_current_image)
        rlayout.addWidget(btn_trash)

        rlayout.addWidget(QLabel("<b>Statistics</b>"))
        self.stats_label = QLabel("-")
        self.stats_label.setWordWrap(True)
        rlayout.addWidget(self.stats_label)
        rlayout.addStretch()

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(self.scroll)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self._set_mode(MODE_SELECT)

    def _install_shortcuts(self):
        def mk(seq, handler):
            a = QAction(self)
            a.setShortcut(QKeySequence(seq))
            a.setShortcutContext(Qt.ApplicationShortcut)
            a.triggered.connect(handler)
            self.addAction(a)
            return a

        mk("W", lambda: self._set_mode(MODE_DRAW))
        mk("S", lambda: self._set_mode(MODE_SELECT))
        mk("R", lambda: self._set_mode(MODE_GRID_PAINT))
        mk("E", lambda: self._set_mode(MODE_ERASE))
        mk("D", self._next_image)
        mk("A", self._prev_image)
        mk("Delete", self._delete_selected)
        mk("Backspace", self._delete_selected)
        mk("Esc", self._clear_selection)
        mk("+", lambda: self._zoom(1.2))
        mk("-", lambda: self._zoom(1 / 1.2))

    # ---------- Actions ----------
    def _load_index(self, idx: int):
        if self.doc and self.doc.dirty and self.auto_save:
            self._save()
        if not (0 <= idx < len(self.images)):
            return
        self.current_idx = idx
        img_path = self.images[idx]
        xml_path = self.label_dir / f"{img_path.stem}.xml"
        self.doc = Document.load(img_path, xml_path)
        self.undo_stack.clear()
        self.redo_stack.clear()
        pix = QPixmap(str(img_path))
        self.canvas.set_document(self.doc, pix)
        self.image_list.blockSignals(True)
        self.image_list.setCurrentRow(idx)
        self.image_list.blockSignals(False)
        self._update_title()
        self._update_stats()

    def _update_title(self):
        if not self.doc:
            return
        self.setWindowTitle(
            f"Label Editor — [{self.current_idx+1}/{len(self.images)}] "
            f"{self.doc.image_path.name} ({len(self.doc.bboxes)} bboxes)"
            + (" *" if self.doc.dirty else "")
        )

    def _on_image_selected(self, idx: int):
        if idx != self.current_idx and 0 <= idx < len(self.images):
            self._load_index(idx)

    def _next_image(self):
        self._load_index(min(self.current_idx + 1, len(self.images) - 1))

    def _prev_image(self):
        self._load_index(max(self.current_idx - 1, 0))

    def _save(self):
        if self.doc is None:
            return
        xml_path = self.label_dir / f"{self.doc.image_path.stem}.xml"
        self.doc.save(xml_path)
        self._set_status(f"Saved: {xml_path.name}")
        self._update_title()

    def _save_as(self):
        if self.doc is None:
            return
        default = str(self.label_dir / f"{self.doc.image_path.stem}.xml")
        path, _ = QFileDialog.getSaveFileName(self, "Save XML", default, "XML (*.xml)")
        if path:
            self.doc.save(Path(path))
            self._set_status(f"Saved: {path}")

    def _open_image_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Image dir", str(self.image_dir))
        if not d:
            return
        self.image_dir = Path(d)
        self.images = self._scan_images(self.image_dir)
        self.image_list.clear()
        self.image_list.addItems([p.name for p in self.images])
        if self.images:
            self._load_index(0)

    def _change_save_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Save dir", str(self.label_dir))
        if not d:
            return
        self.label_dir = Path(d)
        self.label_dir.mkdir(parents=True, exist_ok=True)
        self._set_status(f"Save dir: {self.label_dir}")
        self._load_index(self.current_idx)

    def _open_classes_file(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "Open classes.txt", str(classes_dir()), "Text (*.txt)"
        )
        if not p:
            return
        self.classes_file = Path(p)
        self.classes = self._load_classes(self.classes_file)
        self.class_list.clear()
        for c in self.classes:
            r, g, b = _ensure_color(c)
            it = QListWidgetItem(c)
            sw = QPixmap(16, 16); sw.fill(QColor(r, g, b))
            painter = QPainter(sw); painter.setPen(QPen(QColor(0, 0, 0), 1))
            painter.drawRect(0, 0, 15, 15); painter.end()
            it.setIcon(QIcon(sw))
            self.class_list.addItem(it)
        if self.classes:
            self.class_list.setCurrentRow(0)
        self._set_status(f"Loaded {len(self.classes)} classes from {Path(p).name}")

    def _delete_selected(self):
        if self.doc is None:
            return
        before = len(self.doc.bboxes)
        self._push_undo("delete")
        self.doc.bboxes = [b for b in self.doc.bboxes if not b.selected]
        removed = before - len(self.doc.bboxes)
        if removed > 0:
            self.doc.dirty = True
            self._on_doc_changed()
            self._set_status(f"Deleted {removed} bbox")

    def _select_all(self):
        if self.doc is None:
            return
        for bb in self.doc.bboxes:
            bb.selected = True
        self.canvas.update()
        self._on_doc_changed()

    def _select_same_class(self):
        if self.doc is None:
            return
        selected = [b for b in self.doc.bboxes if b.selected]
        if not selected:
            self._set_status("선택된 bbox 없음")
            return
        target_classes = {b.name for b in selected}
        count = 0
        for bb in self.doc.bboxes:
            if bb.name in target_classes:
                bb.selected = True
                count += 1
        self._on_doc_changed()
        self._set_status(f"Selected {count} of '{', '.join(target_classes)}'")

    def _select_by_class_prompt(self):
        if self.doc is None:
            return
        name, ok = QInputDialog.getItem(
            self, "Select by Class", "Class:", self.classes, 0, editable=False,
        )
        if not ok or not name:
            return
        count = 0
        for bb in self.doc.bboxes:
            if bb.name == name:
                bb.selected = True
                count += 1
            else:
                bb.selected = False
        self._on_doc_changed()
        self._set_status(f"Selected {count} of '{name}'")

    def _delete_by_class_prompt(self):
        if self.doc is None:
            return
        name, ok = QInputDialog.getItem(
            self, "Delete All of Class", "Class:", self.classes, 0, editable=False,
        )
        if not ok or not name:
            return
        count = sum(1 for bb in self.doc.bboxes if bb.name == name)
        if count == 0:
            self._set_status(f"No bbox of '{name}'")
            return
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"'{name}' 클래스의 {count}개 bbox 삭제.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._push_undo(f"delete all '{name}'")
        self.doc.bboxes = [bb for bb in self.doc.bboxes if bb.name != name]
        self.doc.dirty = True
        self._on_doc_changed()
        self._set_status(f"Deleted {count} of '{name}'")

    def _clear_selection(self):
        if self.doc is None:
            return
        for bb in self.doc.bboxes:
            bb.selected = False
        self.canvas.update()
        self._on_doc_changed()

    def _duplicate(self):
        if self.doc is None:
            return
        selected = [b for b in self.doc.bboxes if b.selected]
        if not selected:
            return
        self._push_undo("duplicate")
        for bb in self.doc.bboxes:
            bb.selected = False
        dx = dy = 10
        for bb in selected:
            nb = BBox(name=bb.name,
                      xmin=bb.xmin + dx, ymin=bb.ymin + dy,
                      xmax=bb.xmax + dx, ymax=bb.ymax + dy,
                      selected=True)
            self.doc.bboxes.append(nb)
        self.doc.dirty = True
        self._on_doc_changed()
        self._set_status(f"Duplicated {len(selected)}")

    def _set_mode(self, mode: str):
        self.canvas.set_mode(mode)
        for m, btn in self.mode_btns.items():
            btn.setChecked(m == mode)

    def _on_class_selected(self, name: str):
        if not name:
            return
        self.canvas.set_class(name)
        self.current_class_label.setText(f"Current: {name}")
        if self.doc:
            selected = [b for b in self.doc.bboxes if b.selected]
            if selected:
                self._push_undo("class change")
                for bb in selected:
                    bb.name = name
                self.doc.dirty = True
                self._on_doc_changed()
                self._set_status(f"{len(selected)} bbox → {name}")

    def _on_doc_changed(self):
        self.canvas.update()
        self._update_stats()
        self._update_selection_info()
        self._update_title()

    def _update_selection_info(self):
        if self.doc is None:
            self.selection_info.setText("-")
            return
        from collections import Counter
        selected = [b for b in self.doc.bboxes if b.selected]
        if not selected:
            self.selection_info.setText("선택 없음")
            return
        c = Counter(b.name for b in selected)
        if len(c) == 1:
            name, cnt = next(iter(c.items()))
            self.selection_info.setText(f"{cnt} bbox ({name})")
        else:
            lines = [f"{sum(c.values())} bbox (mixed):"]
            for name, cnt in c.most_common():
                lines.append(f"  • {name}: {cnt}")
            self.selection_info.setText("\n".join(lines))

    def _update_stats(self):
        if self.doc is None:
            self.stats_label.setText("-")
            return
        from collections import Counter
        c = Counter(b.name for b in self.doc.bboxes)
        lines = [f"Total: {sum(c.values())}"]
        for name, cnt in c.most_common(15):
            lines.append(f"  {name}: {cnt}")
        self.stats_label.setText("\n".join(lines))

    def _set_status(self, msg: str):
        self.status.showMessage(msg, 5000)

    def _on_autosave_toggle(self, state):
        self.auto_save = bool(state)

    def _zoom(self, factor: float):
        self.canvas.set_zoom(self.canvas.zoom * factor)

    def _zoom_100(self):
        self.canvas.set_zoom(1.0)

    def _fit_window(self):
        self.canvas.fit_to_window(self.scroll.viewport().size())

    # ---------- Undo/Redo ----------
    def _push_undo(self, label: str):
        if self.doc is None:
            return
        self.undo_stack.append((label, self.doc.snapshot()))
        if len(self.undo_stack) > self.undo_limit:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def _undo(self):
        if self.doc is None or not self.undo_stack:
            return
        label, snap = self.undo_stack.pop()
        self.redo_stack.append((label, self.doc.snapshot()))
        self.doc.bboxes = snap
        self.doc.dirty = True
        self._on_doc_changed()
        self._set_status(f"Undo: {label}")

    def _redo(self):
        if self.doc is None or not self.redo_stack:
            return
        label, snap = self.redo_stack.pop()
        self.undo_stack.append((label, self.doc.snapshot()))
        self.doc.bboxes = snap
        self.doc.dirty = True
        self._on_doc_changed()
        self._set_status(f"Redo: {label}")

    # ---------- Trash ----------
    def _trash_current_image(self):
        if self.doc is None or self.current_idx < 0:
            return
        img_path = self.images[self.current_idx]
        xml_path = self.label_dir / f"{img_path.stem}.xml"
        reply = QMessageBox.question(
            self, "Trash Image",
            f"{img_path.name} 을(를) images_trash/로 이동하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            return
        trash_img = self.image_dir.parent / "images_trash"
        trash_xml = self.label_dir.parent / "labels_trash"
        trash_img.mkdir(exist_ok=True)
        trash_xml.mkdir(exist_ok=True)
        import shutil
        self.doc.dirty = False
        try:
            shutil.move(str(img_path), str(trash_img / img_path.name))
            if xml_path.exists():
                shutil.move(str(xml_path), str(trash_xml / xml_path.name))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"이동 실패:\n{e}")
            return
        removed_idx = self.current_idx
        self.images.pop(removed_idx)
        self.image_list.takeItem(removed_idx)
        if not self.images:
            self.doc = None
            self.canvas.set_document(None, QPixmap())
            self.setWindowTitle("Label Editor — (no images)")
            return
        next_idx = min(removed_idx, len(self.images) - 1)
        self.current_idx = -1
        self._load_index(next_idx)
        self._set_status(f"Trashed: {img_path.name}")

    # ---------- YOLO export ----------
    def _export_yolo(self):
        if not any(self.label_dir.glob("*.xml")):
            QMessageBox.information(self, "Export", "라벨 XML이 없습니다.")
            return
        out_dir = QFileDialog.getExistingDirectory(
            self, "YOLO output dir", str(self.label_dir),
        )
        if not out_dir:
            return
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        name_to_idx = {n: i for i, n in enumerate(self.classes)}
        (out / "classes.txt").write_text(
            "\n".join(self.classes) + "\n", encoding="utf-8"
        )
        n_files = 0
        n_box = 0
        from collections import Counter as _C
        skipped: _C = _C()
        for xml in self.label_dir.glob("*.xml"):
            try:
                tree = ET.parse(xml)
            except ET.ParseError:
                continue
            root = tree.getroot()
            w = int(root.findtext("size/width", "0"))
            h = int(root.findtext("size/height", "0"))
            if w == 0 or h == 0:
                continue
            lines = []
            for obj in root.findall("object"):
                name = (obj.findtext("name") or "").strip()
                if name not in name_to_idx:
                    skipped[name] += 1
                    continue
                bb = obj.find("bndbox")
                if bb is None:
                    continue
                xmin = float(bb.findtext("xmin", "0"))
                ymin = float(bb.findtext("ymin", "0"))
                xmax = float(bb.findtext("xmax", "0"))
                ymax = float(bb.findtext("ymax", "0"))
                cx = (xmin + xmax) / 2 / w
                cy = (ymin + ymax) / 2 / h
                bw = (xmax - xmin) / w
                bh = (ymax - ymin) / h
                lines.append(f"{name_to_idx[name]} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
                n_box += 1
            (out / f"{xml.stem}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
            n_files += 1
        msg = f"YOLO 변환 완료\nFiles: {n_files}\nBoxes: {n_box}\nClasses: {len(name_to_idx)}"
        if skipped:
            top = ", ".join(f"{n}:{c}" for n, c in skipped.most_common(5))
            msg += f"\n\n경고 — classes.txt에 없는 클래스 스킵: {top}"
        QMessageBox.information(self, "Export YOLO", msg)

    def closeEvent(self, event):
        if self.doc and self.doc.dirty:
            r = QMessageBox.question(
                self, "Unsaved changes",
                "저장하지 않은 변경이 있습니다. 저장하고 종료?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            )
            if r == QMessageBox.Save:
                self._save()
            elif r == QMessageBox.Cancel:
                event.ignore()
                return
        event.accept()


# ══════════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--genre", choices=GENRES, help="puzzle | slg | idle (skip startup dialog)")
    ap.add_argument("--classes", type=Path, help="classes.txt path (overrides --genre)")
    ap.add_argument("--dir", type=Path, help="image directory")
    ap.add_argument("--labels", type=Path, help="label save directory")
    args = ap.parse_args()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    classes_file: Optional[Path] = None
    image_dir: Optional[Path] = None
    label_dir: Optional[Path] = None

    if args.classes:
        classes_file = args.classes
    elif args.genre:
        classes_file = classes_dir() / f"{args.genre}.txt"
    if args.dir:
        image_dir = args.dir
    if args.labels:
        label_dir = args.labels

    if not (classes_file and image_dir and label_dir):
        dlg = StartupDialog()
        if dlg.exec() != QDialog.Accepted:
            return 0
        classes_file = dlg.classes_file
        image_dir = dlg.image_dir
        label_dir = dlg.label_dir

    win = MainWindow(image_dir, label_dir, classes_file)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
