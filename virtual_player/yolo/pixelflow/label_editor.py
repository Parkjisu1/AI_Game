"""
Label Editor v2 (PySide6) — labelImg 호환 고급 편집 도구
============================================================

labelImg의 모든 핵심 기능 + 다중 선택/일괄 편집 기능 제공.

=== 모드 ===
  [S] 선택 (드래그=영역 선택 / 클릭=단일 선택 / 핸들 드래그=크기조정 / 중앙 드래그=이동)
  [W] 그리기 (드래그=새 bbox)
  [R] 영역 페인트 (드래그 영역 내 bbox를 현재 클래스로 일괄 변경)
  [E] 영역 삭제 (드래그 영역 내 bbox 일괄 삭제)

=== 전역 ===
  우클릭 드래그 = 모드 무관 즉시 영역 삭제

=== 단축키 ===
  이동      D/A : 다음/이전 이미지
  저장      Ctrl+S
  삭제      Delete, Backspace : 선택 bbox 삭제
  전체선택   Ctrl+A
  복제      Ctrl+D : 선택 bbox 복제
  Undo      Ctrl+Z
  Redo      Ctrl+Y / Ctrl+Shift+Z
  확대/축소  +/-, Ctrl+Wheel
  Fit       F : 창 맞춤
  1:1       Ctrl+1 : 원본 크기
  모드      S/W/R/E
  선택해제   Esc
"""
from __future__ import annotations
import sys
import copy
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

from PySide6.QtCore import Qt, QRect, QPoint, QSize, Signal, QTimer
from PySide6.QtGui import (
    QPixmap, QPainter, QPen, QColor, QBrush, QAction, QKeySequence, QFont,
    QCursor, QIcon,
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QListWidget, QFileDialog, QMessageBox, QScrollArea,
    QInputDialog, QStatusBar, QListWidgetItem, QSplitter, QMenuBar,
    QCheckBox, QToolBar, QAbstractItemView,
)


# ══════════════════════════════════════════════════════════════
#  Data Model
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
        w = int(root.find("size/width").text)
        h = int(root.find("size/height").text)
        bboxes = []
        for obj in root.findall("object"):
            name = (obj.find("name").text or "").strip()
            bb = obj.find("bndbox")
            bboxes.append(BBox(
                name=name,
                xmin=int(float(bb.find("xmin").text)),
                ymin=int(float(bb.find("ymin").text)),
                xmax=int(float(bb.find("xmax").text)),
                ymax=int(float(bb.find("ymax").text)),
            ))
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
#  Class Colors
# ══════════════════════════════════════════════════════════════
CLASS_COLORS: dict[str, tuple[int, int, int]] = {
    "pink cell": (252, 106, 175), "hot pink cell": (252, 56, 165),
    "cyan cell": (80, 232, 246), "purple cell": (137, 80, 248),
    "yellow cell": (254, 213, 85), "green cell": (115, 254, 102),
    "orange cell": (253, 161, 76), "white cell": (255, 255, 255),
    "black cell": (50, 50, 50), "blue cell": (50, 107, 248),
    "dark green cell": (57, 174, 46), "red cell": (252, 94, 94),
    "brown cell": (106, 74, 48), "white blue cell": (183, 199, 251),
    "white yellow cell": (254, 227, 169), "white green cell": (167, 221, 148),
    "gray cell": (111, 114, 127), "dark gray cell": (70, 70, 90),
    "brown red cell": (137, 10, 8),
    "block gimik": (255, 0, 255), "cannon gimik": (200, 0, 100),
    "door gimik": (150, 100, 50), "egg gimik": (255, 255, 200),
    "hidden gimik": (100, 100, 100), "ice gimik": (200, 230, 255),
    "key gimik": (255, 215, 0), "pinata gimik": (255, 100, 200),
    "snake gimik": (50, 200, 50), "wall gimik": (100, 50, 50),
}


def class_color(name: str) -> QColor:
    r, g, b = CLASS_COLORS.get(name, (200, 200, 200))
    return QColor(r, g, b)


# ══════════════════════════════════════════════════════════════
#  Modes
# ══════════════════════════════════════════════════════════════
MODE_SELECT = "select"
MODE_DRAW = "draw"
MODE_GRID_PAINT = "grid"
MODE_ERASE = "erase"
MODE_BOARD = "board"

# Resize handles
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

HANDLE_SIZE_PX = 8  # widget px


# ══════════════════════════════════════════════════════════════
#  Canvas Widget
# ══════════════════════════════════════════════════════════════

class Canvas(QLabel):
    doc_changed = Signal()
    status_msg = Signal(str)
    snapshot_request = Signal(str)  # undo stack용

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self.doc: Optional[Document] = None
        self.pixmap_orig: Optional[QPixmap] = None
        self.zoom: float = 0.6

        self.mode: str = MODE_SELECT
        self.current_class: str = "pink cell"

        # drag state
        self._drag_start: Optional[QPoint] = None
        self._drag_end: Optional[QPoint] = None
        self._dragging = False
        self._right_drag = False

        # bbox editing state
        self._edit_target: Optional[BBox] = None   # 편집 대상 bbox
        self._edit_handle: int = HANDLE_NONE        # 조작 핸들
        self._edit_origin: Optional[tuple[int, int, int, int]] = None
        self._edit_mouse_start: Optional[tuple[int, int]] = None

        # 보드 영역 (사용자 지정, 이미지 좌표계 x,y,w,h)
        self.board_rect: Optional[tuple[int, int, int, int]] = None

    # ---------- API ----------
    def set_document(self, doc: Document, pixmap: QPixmap) -> None:
        self.doc = doc
        self.pixmap_orig = pixmap
        self._update_display()

    def set_zoom(self, zoom: float, anchor: Optional[QPoint] = None) -> None:
        old = self.zoom
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

    # ---------- 좌표 변환 ----------
    def _w2i(self, x: int, y: int) -> tuple[int, int]:
        return int(x / self.zoom), int(y / self.zoom)

    def _i2w(self, x: int, y: int) -> tuple[int, int]:
        return int(x * self.zoom), int(y * self.zoom)

    # ---------- Update ----------
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

    # ---------- Handle detection ----------
    def _hit_handle(self, ix: int, iy: int) -> tuple[Optional[BBox], int]:
        """선택된 bbox의 핸들 히트테스트. 위젯 기준 HANDLE_SIZE_PX 반경."""
        if self.doc is None or self.zoom <= 0:
            return None, HANDLE_NONE
        margin = max(4, int(HANDLE_SIZE_PX / self.zoom))

        # 선택된 것 우선
        selected = [b for b in self.doc.bboxes if b.selected]
        pool = selected if selected else self.doc.bboxes

        # 위에서 아래로 (최근 추가 우선)
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
            # Move: bbox 내부
            if bb.contains(ix, iy):
                return bb, HANDLE_MOVE
        return None, HANDLE_NONE

    # ---------- Render ----------
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

        # 보드 영역 표시 (cyan 굵은 dashed 테두리)
        if self.board_rect is not None:
            bx, by, bw, bh = self.board_rect
            wx0, wy0 = self._i2w(bx, by)
            wx1, wy1 = self._i2w(bx + bw, by + bh)
            pen = QPen(QColor(0, 255, 255), 3, Qt.DashLine)
            p.setPen(pen)
            p.drawRect(wx0, wy0, wx1 - wx0, wy1 - wy0)
            # 라벨
            p.fillRect(wx0, wy0 - 22, 110, 20, QBrush(QColor(0, 120, 140, 220)))
            p.setPen(QPen(QColor(255, 255, 255)))
            p.drawText(wx0 + 4, wy0 - 6, "BOARD REGION")

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

            # 클래스명 라벨 (선택된 bbox 또는 hover 중인 것)
            if bb.selected:
                text = bb.name
                fm = p.fontMetrics()
                tw = fm.horizontalAdvance(text) + 8
                th = fm.height() + 4
                tx = x0
                ty = max(0, y0 - th)
                # 배경
                p.fillRect(tx, ty, tw, th, QBrush(QColor(0, 0, 0, 200)))
                p.setPen(QPen(QColor(255, 255, 0), 1))
                p.drawRect(tx, ty, tw, th)
                p.setPen(QPen(QColor(255, 255, 255)))
                p.drawText(tx + 4, ty + fm.ascent() + 2, text)

            # 선택된 bbox: 핸들 8개 그리기
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

        # 드래그 박스
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
            elif self.mode == MODE_BOARD:
                p.setPen(QPen(QColor(0, 255, 255), 3, Qt.DashLine))
                p.fillRect(rect, QBrush(QColor(0, 255, 255, 50)))
            if self._right_drag:
                p.setPen(QPen(QColor(255, 0, 0), 2, Qt.DashLine))
                p.fillRect(rect, QBrush(QColor(255, 0, 0, 60)))
            p.drawRect(rect)

    # ---------- Mouse ----------
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

            # SELECT 모드에서 Ctrl 없을 때만 핸들 편집
            if self.mode == MODE_SELECT and not ctrl_held:
                target, handle = self._hit_handle(ix, iy)
                if target is not None and handle != HANDLE_NONE:
                    # 단일 대상만 편집 중이면 다른 선택 해제
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

                # 핸들 아니면 일반 클릭 선택: 기존 선택 초기화 + 클릭한 bbox 선택
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

            # SELECT 모드에서 Ctrl 누른 경우: 기존 선택 유지, 드래그 박스로 영역 추가 선택만
            # (핸들 편집, 클릭 선택 초기화 둘 다 건너뜀)

            self._drag_start = pos
            self._drag_end = pos
            self._dragging = True
            self.update()

    def mouseMoveEvent(self, event):
        if self.doc is None:
            return
        pos = event.position().toPoint()
        ix, iy = self._w2i(pos.x(), pos.y())

        # bbox 편집 중
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
            # hover cursor
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

        # 편집 종료
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

        # 작은 드래그는 클릭 취급
        if w_pix < 4 and h_pix < 4:
            self._drag_start = None
            self._drag_end = None
            self._right_drag = False
            self.update()
            return

        # 우클릭 드래그는 모드 무관 삭제
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
            # 영역 선택 (교차)
            for bb in self.doc.bboxes:
                if bb.intersects(x0, y0, x1, y1):
                    bb.selected = True
            count = sum(1 for b in self.doc.bboxes if b.selected)
            self.status_msg.emit(f"{count} bbox selected")
            self.doc_changed.emit()
        elif self.mode == MODE_DRAW:
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
                self.status_msg.emit(f"{count} cells → {self.current_class}")
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
        elif self.mode == MODE_BOARD:
            # 보드 영역 설정
            self.board_rect = (x0, y0, x1 - x0, y1 - y0)
            self.doc_changed.emit()
            self.status_msg.emit(
                f"📐 Board region set: ({x0},{y0}) {x1-x0}x{y1-y0}px"
            )

        self._drag_start = None
        self._drag_end = None
        self.update()

    def wheelEvent(self, event):
        # Ctrl+Wheel: Zoom
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            factor = 1.15 if delta > 0 else 1 / 1.15
            self.set_zoom(self.zoom * factor)
            event.accept()
        else:
            super().wheelEvent(event)


# ══════════════════════════════════════════════════════════════
#  Main Window
# ══════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self, image_dir: Path, label_dir: Path, classes_file: Path):
        super().__init__()
        self.setWindowTitle("PixelFlow Label Editor v2")
        self.resize(1800, 1100)

        self.image_dir = image_dir
        self.label_dir = label_dir
        self.label_dir.mkdir(parents=True, exist_ok=True)
        self.classes_file = classes_file
        self.classes = self._load_classes(classes_file)

        self.images = self._scan_images(image_dir)
        self.current_idx = 0
        self.doc: Optional[Document] = None

        # 보드 영역 저장 (이미지명 → (x,y,w,h))
        self.board_regions_path = label_dir.parent / "board_regions.json"
        self.board_regions: dict[str, list[int]] = self._load_board_regions()

        # Undo/Redo: (label, snapshot)
        self.undo_stack: list[tuple[str, list[BBox]]] = []
        self.redo_stack: list[tuple[str, list[BBox]]] = []
        self.undo_limit = 50

        self.auto_save = True

        self._build_menubar()
        self._build_ui()
        self._install_shortcuts()

        if self.images:
            self._load_index(0)

    def _scan_images(self, d: Path) -> list[Path]:
        return sorted(
            p for p in d.iterdir()
            if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp"}
        )

    def _load_board_regions(self) -> dict[str, list[int]]:
        import json
        if self.board_regions_path.exists():
            try:
                return json.loads(self.board_regions_path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_board_regions(self):
        import json
        self.board_regions_path.write_text(
            json.dumps(self.board_regions, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _load_classes(self, path: Path) -> list[str]:
        if path.exists():
            return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        return list(CLASS_COLORS.keys())

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

        import hashlib
        h = hashlib.md5(name.encode("utf-8")).digest()
        color = (60 + h[0] % 180, 60 + h[1] % 180, 60 + h[2] % 180)
        CLASS_COLORS[name] = color

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
        swatch = QPixmap(16, 16)
        swatch.fill(QColor(*color))
        painter = QPainter(swatch)
        painter.setPen(QPen(QColor(0, 0, 0), 1))
        painter.drawRect(0, 0, 15, 15)
        painter.end()
        item.setIcon(QIcon(swatch))
        self.class_list.addItem(item)
        self.class_list.setCurrentItem(item)
        self._set_status(f"Added class: {name}")

    # ---------- UI ----------
    def _build_menubar(self):
        mb = self.menuBar()

        m_file = mb.addMenu("&File")
        m_file.addAction(self._make_action("Open Image Dir...", self._open_image_dir, None))
        m_file.addAction(self._make_action("Change Save Dir...", self._change_save_dir, None))
        m_file.addSeparator()
        m_file.addAction(self._make_action("Save", self._save, "Ctrl+S"))
        m_file.addAction(self._make_action("Save As...", self._save_as, None))
        m_file.addSeparator()
        m_file.addAction(self._make_action("Exit", self.close, None))

        m_edit = mb.addMenu("&Edit")
        m_edit.addAction(self._make_action("Undo", self._undo, "Ctrl+Z"))
        m_edit.addAction(self._make_action("Redo", self._redo, "Ctrl+Y"))
        m_edit.addSeparator()
        m_edit.addAction(self._make_action("Select All", self._select_all, "Ctrl+A"))
        m_edit.addAction(self._make_action(
            "Select Same Class (from current selection)", self._select_same_class, "Ctrl+Shift+A"))
        m_edit.addAction(self._make_action(
            "Select by Class (prompt)...", self._select_by_class_prompt, None))
        m_edit.addAction(self._make_action("Duplicate", self._duplicate, "Ctrl+D"))
        m_edit.addAction(self._make_action("Delete", self._delete_selected, "Delete"))
        m_edit.addSeparator()
        m_edit.addAction(self._make_action(
            "Delete All of Class (prompt)...", self._delete_by_class_prompt, None))

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
            "🗑 Trash Current Image (move to trash)",
            self._trash_current_image, "Ctrl+Shift+X"))

        m_auto = mb.addMenu("&Auto")
        m_auto.addAction(self._make_action(
            "Auto-Detect Cells (Hybrid - replace)", self._auto_label_replace, "Ctrl+L"))
        m_auto.addAction(self._make_action(
            "Auto-Detect Cells (Hybrid - append)", self._auto_label_append, "Ctrl+Shift+L"))
        m_auto.addSeparator()
        m_auto.addAction(self._make_action(
            "Detect with Trained YOLO (replace)", self._yolo_detect_replace, "Ctrl+M"))
        m_auto.addAction(self._make_action(
            "Compare: My Labels vs Model Predictions", self._compare_with_model, None))
        m_auto.addSeparator()
        m_auto.addAction(self._make_action(
            "Auto-Label ALL Unlabeled Images...", self._auto_label_batch, None))

        m_board = mb.addMenu("&Board")
        m_board.addAction(self._make_action(
            "Set Board Region Mode", lambda: self._set_mode(MODE_BOARD), "B"))
        m_board.addAction(self._make_action(
            "Clear Board Region", self._clear_board_region, None))
        m_board.addSeparator()
        m_board.addAction(self._make_action(
            "Apply Current Board to ALL Images", self._apply_board_to_all, None))

    def _make_action(self, text: str, handler, shortcut) -> QAction:
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

        # 좌측: 이미지 리스트
        left = QListWidget()
        left.setStyleSheet("""
            QListWidget {
                background: #fafafa;
                color: #111;
                font-size: 11px;
                border: 1px solid #cccccc;
                outline: 0;
            }
            QListWidget::item {
                padding: 4px 6px;
            }
            QListWidget::item:selected {
                background: #2a5d9e;
                color: #ffffff;
            }
            QListWidget::item:hover {
                background: #d6e4f5;
            }
        """)
        left.addItems([p.name for p in self.images])
        left.setMaximumWidth(240)
        left.currentRowChanged.connect(self._on_image_selected)
        self.image_list = left

        # 중앙: 캔버스
        self.canvas = Canvas()
        self.canvas.doc_changed.connect(self._on_doc_changed)
        self.canvas.status_msg.connect(self._set_status)
        self.canvas.snapshot_request.connect(self._push_undo)
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.canvas)
        self.scroll.setWidgetResizable(False)

        # 우측: 패널
        right = QWidget()
        right.setMaximumWidth(280)
        rlayout = QVBoxLayout(right)

        rlayout.addWidget(QLabel("<b>Mode</b>"))
        self.mode_btns = {}
        for key, mode, tip in [
            ("S", MODE_SELECT, "[S] Select / Edit"),
            ("W", MODE_DRAW, "[W] Draw new bbox"),
            ("R", MODE_GRID_PAINT, "[R] Grid paint (bulk reclassify)"),
            ("E", MODE_ERASE, "[E] Erase (area delete)"),
            ("B", MODE_BOARD, "[B] Board Region (Auto-Detect 범위)"),
        ]:
            b = QPushButton(tip)
            b.setCheckable(True)
            b.clicked.connect(lambda _c=False, m=mode: self._set_mode(m))
            rlayout.addWidget(b)
            self.mode_btns[mode] = b

        # Auto-save checkbox
        self.auto_save_cb = QCheckBox("Auto save on image change")
        self.auto_save_cb.setChecked(True)
        self.auto_save_cb.stateChanged.connect(self._on_autosave_toggle)
        rlayout.addWidget(self.auto_save_cb)

        rlayout.addWidget(QLabel("<b>Class</b>"))
        self.class_list = QListWidget()
        self.class_list.setStyleSheet("""
            QListWidget {
                background: #fafafa;
                color: #111;
                font-size: 12px;
                border: 1px solid #cccccc;
                outline: 0;
            }
            QListWidget::item {
                padding: 5px 6px;
                border-bottom: 1px solid #eeeeee;
            }
            QListWidget::item:selected {
                background: #2a5d9e;
                color: #ffffff;
            }
            QListWidget::item:hover {
                background: #d6e4f5;
            }
        """)
        for c in self.classes:
            item = QListWidgetItem(c)
            # 컬러 박스 아이콘
            r, g, b = CLASS_COLORS.get(c, (200, 200, 200))
            swatch = QPixmap(16, 16)
            swatch.fill(QColor(r, g, b))
            # 테두리
            painter = QPainter(swatch)
            painter.setPen(QPen(QColor(0, 0, 0), 1))
            painter.drawRect(0, 0, 15, 15)
            painter.end()
            item.setIcon(QIcon(swatch))
            # 텍스트 색은 기본 유지 (검정)
            self.class_list.addItem(item)
        self.class_list.currentTextChanged.connect(self._on_class_selected)
        rlayout.addWidget(self.class_list)

        btn_new_class = QPushButton("+ New Class")
        btn_new_class.setToolTip("새 클래스 추가 (classes.txt에 저장됨)")
        btn_new_class.setStyleSheet("background: #2e7d32; color: white; padding: 6px;")
        btn_new_class.clicked.connect(self._add_new_class)
        rlayout.addWidget(btn_new_class)

        self.current_class_label = QLabel("Current: pink cell")
        self.current_class_label.setStyleSheet("font-weight: bold; padding: 4px;")
        rlayout.addWidget(self.current_class_label)

        # 선택된 bbox 정보
        rlayout.addWidget(QLabel("<b>Selected</b>"))
        self.selection_info = QLabel("-")
        self.selection_info.setWordWrap(True)
        self.selection_info.setStyleSheet(
            "padding: 6px; background: #f0f0f0; border: 1px solid #ccc; font-size: 11px;"
        )
        rlayout.addWidget(self.selection_info)

        # Board Region
        rlayout.addWidget(QLabel("<b>Board Region</b>"))
        btn_board_mode = QPushButton("📐 Set Board Region (B)")
        btn_board_mode.setToolTip("[B] 드래그로 보드 영역 지정 — Auto-Detect가 이 안에서만 셀 탐지")
        btn_board_mode.setStyleSheet("background: #008ca0; color: white; padding: 6px;")
        btn_board_mode.clicked.connect(lambda: self._set_mode(MODE_BOARD))
        rlayout.addWidget(btn_board_mode)

        btn_apply_all = QPushButton("↗ Apply to All Images")
        btn_apply_all.setToolTip("현재 보드 영역을 모든 이미지에 적용")
        btn_apply_all.clicked.connect(self._apply_board_to_all)
        rlayout.addWidget(btn_apply_all)

        btn_clear_board = QPushButton("✖ Clear Board Region")
        btn_clear_board.clicked.connect(self._clear_board_region)
        rlayout.addWidget(btn_clear_board)

        # Auto-detect 버튼
        rlayout.addWidget(QLabel("<b>Auto Detect</b>"))
        btn_auto_replace = QPushButton("🔍 Auto-Detect Cells (Replace)")
        btn_auto_replace.setToolTip("Ctrl+L — 현재 이미지의 모든 셀을 자동 탐지 (기존 bbox 교체)")
        btn_auto_replace.clicked.connect(self._auto_label_replace)
        rlayout.addWidget(btn_auto_replace)
        btn_auto_append = QPushButton("➕ Auto-Detect Cells (Append)")
        btn_auto_append.setToolTip("Ctrl+Shift+L — 자동 탐지한 셀을 기존 bbox에 추가")
        btn_auto_append.clicked.connect(self._auto_label_append)
        rlayout.addWidget(btn_auto_append)

        # Image management
        rlayout.addWidget(QLabel("<b>Image</b>"))
        btn_trash = QPushButton("🗑 Trash This Image (Ctrl+Shift+X)")
        btn_trash.setToolTip("현재 이미지를 images_trash/로 이동 (라벨도 함께, 복구 가능)")
        btn_trash.setStyleSheet("background: #c44a4a; color: white; padding: 6px;")
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

        # 모드 전환
        mk("W", lambda: self._set_mode(MODE_DRAW))
        mk("S", lambda: self._set_mode(MODE_SELECT))
        mk("R", lambda: self._set_mode(MODE_GRID_PAINT))
        mk("E", lambda: self._set_mode(MODE_ERASE))
        mk("B", lambda: self._set_mode(MODE_BOARD))

        # 이미지 전환
        mk("D", self._next_image)
        mk("A", self._prev_image)

        # 삭제
        mk("Delete", self._delete_selected)
        mk("Backspace", self._delete_selected)

        # 기타
        mk("Esc", self._clear_selection)
        mk("+", lambda: self._zoom(1.2))
        mk("-", lambda: self._zoom(1 / 1.2))

    # ---------- Actions ----------
    def _load_index(self, idx: int):
        if self.doc and self.doc.dirty and self.auto_save:
            self._save()
        # 보드 영역도 저장
        if self.doc and self.canvas.board_rect is not None:
            prev_name = self.doc.image_path.name
            self.board_regions[prev_name] = list(self.canvas.board_rect)
            self._save_board_regions()

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
        # 보드 영역 복원 (저장된 것 or 마지막 사용된 것)
        saved = self.board_regions.get(img_path.name)
        if saved and len(saved) == 4:
            self.canvas.board_rect = tuple(int(v) for v in saved)
        else:
            self.canvas.board_rect = None
        self.canvas.update()

        self.image_list.setCurrentRow(idx)
        self._update_title()
        self._update_stats()

    def _update_title(self):
        if not self.doc:
            return
        self.setWindowTitle(
            f"Label Editor v2 — [{self.current_idx+1}/{len(self.images)}] "
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
        d = QFileDialog.getExistingDirectory(self, "Select Image Directory", str(self.image_dir))
        if not d:
            return
        self.image_dir = Path(d)
        self.images = self._scan_images(self.image_dir)
        self.image_list.clear()
        self.image_list.addItems([p.name for p in self.images])
        if self.images:
            self._load_index(0)

    def _change_save_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select Save Directory", str(self.label_dir))
        if not d:
            return
        self.label_dir = Path(d)
        self.label_dir.mkdir(parents=True, exist_ok=True)
        self._set_status(f"Save dir: {self.label_dir}")
        self._load_index(self.current_idx)

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
        """현재 선택된 bbox와 같은 클래스의 모든 bbox 선택."""
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
        self._set_status(f"Selected {count} bbox of class: {', '.join(target_classes)}")

    def _select_by_class_prompt(self):
        """클래스 이름 입력받아 해당 bbox 모두 선택."""
        if self.doc is None:
            return
        class_name, ok = QInputDialog.getItem(
            self, "Select by Class", "클래스 선택:",
            self.classes, 0, editable=False,
        )
        if not ok or not class_name:
            return
        count = 0
        for bb in self.doc.bboxes:
            if bb.name == class_name:
                bb.selected = True
                count += 1
            else:
                bb.selected = False
        self._on_doc_changed()
        self._set_status(f"Selected {count} bbox of '{class_name}'")

    def _delete_by_class_prompt(self):
        """클래스 이름 선택 → 해당 bbox 모두 삭제 (확인 다이얼로그 포함)."""
        if self.doc is None:
            return
        class_name, ok = QInputDialog.getItem(
            self, "Delete All of Class", "삭제할 클래스:",
            self.classes, 0, editable=False,
        )
        if not ok or not class_name:
            return
        count = sum(1 for bb in self.doc.bboxes if bb.name == class_name)
        if count == 0:
            self._set_status(f"No bbox of '{class_name}'")
            return
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"'{class_name}' 클래스의 {count}개 bbox를 모두 삭제합니다.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._push_undo(f"delete all '{class_name}'")
        self.doc.bboxes = [bb for bb in self.doc.bboxes if bb.name != class_name]
        self.doc.dirty = True
        self._on_doc_changed()
        self._set_status(f"Deleted {count} bbox of '{class_name}'")

    def _clear_selection(self):
        if self.doc is None:
            return
        for bb in self.doc.bboxes:
            bb.selected = False
        self.canvas.update()

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
            nb = BBox(
                name=bb.name,
                xmin=bb.xmin + dx, ymin=bb.ymin + dy,
                xmax=bb.xmax + dx, ymax=bb.ymax + dy,
                selected=True,
            )
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

    # ---------- Board Region ----------
    def _clear_board_region(self):
        if self.doc is None:
            return
        self.canvas.board_rect = None
        # 저장에서도 제거
        name = self.doc.image_path.name
        if name in self.board_regions:
            del self.board_regions[name]
            self._save_board_regions()
        self.canvas.update()
        self._set_status("Board region cleared")

    def _apply_board_to_all(self):
        if self.doc is None or self.canvas.board_rect is None:
            QMessageBox.information(
                self, "Apply Board",
                "먼저 [B] 모드에서 보드 영역을 드래그로 지정해주세요.",
            )
            return
        reply = QMessageBox.question(
            self, "Apply Board to All",
            f"현재 보드 영역을 {len(self.images)}개 이미지 전체에 적용할까요?\n\n"
            f"기존에 개별 설정된 보드 영역도 덮어씁니다.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        rect = list(self.canvas.board_rect)
        for p in self.images:
            self.board_regions[p.name] = rect
        self._save_board_regions()
        self._set_status(f"Board region applied to {len(self.images)} images")

    # ---------- Image Management ----------
    def _trash_current_image(self):
        """현재 이미지를 images_trash/로 이동 (라벨도 함께)."""
        if self.doc is None or self.current_idx < 0:
            return
        img_path = self.images[self.current_idx]
        xml_path = self.label_dir / f"{img_path.stem}.xml"

        # 확인 (체크 후 끄는 옵션 제공)
        reply = QMessageBox.question(
            self, "Trash Image",
            f"다음 이미지를 휴지통으로 이동:\n\n"
            f"  {img_path.name}\n\n"
            f"(images_trash/ 로 이동되며 복구 가능합니다)\n"
            f"계속할까요?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            return

        # 이동 대상 폴더
        trash_img_dir = self.image_dir.parent / "images_trash"
        trash_xml_dir = self.label_dir.parent / "labels_trash"
        trash_img_dir.mkdir(exist_ok=True)
        trash_xml_dir.mkdir(exist_ok=True)

        import shutil
        # 현재 doc 상태(dirty)를 무시하고 삭제 진행 (저장 안 함)
        self.doc.dirty = False

        try:
            shutil.move(str(img_path), str(trash_img_dir / img_path.name))
            if xml_path.exists():
                shutil.move(str(xml_path), str(trash_xml_dir / xml_path.name))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"이동 실패:\n{e}")
            return

        # 리스트에서 제거
        removed_idx = self.current_idx
        self.images.pop(removed_idx)
        self.image_list.takeItem(removed_idx)

        # 다음 이미지 로드 (없으면 이전)
        if not self.images:
            self.doc = None
            self.canvas.set_document(None, QPixmap())  # clear
            self.setWindowTitle("Label Editor v2 — (no images)")
            return

        next_idx = min(removed_idx, len(self.images) - 1)
        self.current_idx = -1  # force reload
        self._load_index(next_idx)
        self._set_status(f"🗑 Trashed: {img_path.name} → images_trash/")

    # ---------- YOLO Model Detect ----------
    def _yolo_detect_replace(self):
        """학습된 YOLO 모델로 현재 이미지 자동 탐지 (기존 라벨 대체)."""
        if self.doc is None:
            return
        try:
            from _paths import LEVELS_MODEL_WEIGHTS
        except Exception:
            return
        if not LEVELS_MODEL_WEIGHTS.exists():
            QMessageBox.warning(
                self, "Model Not Found",
                f"학습된 모델이 없습니다:\n{LEVELS_MODEL_WEIGHTS}\n\n"
                "먼저 run_train.bat 으로 학습하세요.",
            )
            return

        try:
            import cv2
            from ultralytics import YOLO
        except Exception as e:
            QMessageBox.critical(self, "Error", f"YOLO 로드 실패: {e}")
            return

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        model = YOLO(str(LEVELS_MODEL_WEIGHTS))
        img = cv2.imread(str(self.doc.image_path))
        r = model(img, imgsz=1920, conf=0.35, iou=0.5, verbose=False)[0]
        QApplication.restoreOverrideCursor()

        self._push_undo("yolo predict")
        self.doc.bboxes = []
        for box in r.boxes:
            cid = int(box.cls)
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            self.doc.bboxes.append(BBox(
                name=r.names[cid],
                xmin=int(x1), ymin=int(y1), xmax=int(x2), ymax=int(y2),
            ))
        self.doc.dirty = True
        self._on_doc_changed()
        self._set_status(f"🤖 YOLO predicted: {len(self.doc.bboxes)} bboxes")

    def _compare_with_model(self):
        """현재 라벨 vs 모델 예측 비교 (정보 다이얼로그)."""
        if self.doc is None:
            return
        try:
            from _paths import LEVELS_MODEL_WEIGHTS
        except Exception:
            return
        if not LEVELS_MODEL_WEIGHTS.exists():
            QMessageBox.warning(self, "No Model", "학습된 모델 없음")
            return

        from collections import Counter
        try:
            import cv2
            from ultralytics import YOLO
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            return

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        model = YOLO(str(LEVELS_MODEL_WEIGHTS))
        img = cv2.imread(str(self.doc.image_path))
        r = model(img, imgsz=1920, conf=0.35, iou=0.5, verbose=False)[0]
        QApplication.restoreOverrideCursor()

        my_count = Counter(b.name for b in self.doc.bboxes)
        model_count = Counter(r.names[int(b.cls)] for b in r.boxes)
        all_classes = sorted(set(my_count) | set(model_count))

        lines = [f"{'Class':<22s} {'My':>5s} {'Model':>6s} {'Diff':>6s}", "-" * 45]
        for c in all_classes:
            m = my_count.get(c, 0)
            p = model_count.get(c, 0)
            d = p - m
            mark = "✓" if d == 0 else ("+" if d > 0 else "-")
            lines.append(f"{c:<22s} {m:>5d} {p:>6d} {mark}{abs(d):>5d}")
        lines.append("-" * 45)
        lines.append(f"{'TOTAL':<22s} {sum(my_count.values()):>5d} {sum(model_count.values()):>6d}")

        QMessageBox.information(self, "My Labels vs Model", "\n".join(lines))

    # ---------- Auto-Label ----------
    def _run_auto_detect(self) -> list[BBox]:
        """현재 이미지에 대해 auto_label_v2 실행, BBox 리스트 반환."""
        if self.doc is None:
            return []
        try:
            import cv2
            sys.path.insert(0, str(Path(__file__).parent))
            from auto_label_v2 import generate_bboxes
            from _paths import TOOLS_DIR, PROFILE_PATH
            sys.path.insert(0, str(TOOLS_DIR))
            from cell_aware_analyzer import load_profile
            profile = load_profile(str(PROFILE_PATH))
        except Exception as e:
            QMessageBox.critical(self, "Import Error", f"Auto-label 모듈 로드 실패:\n{e}")
            return []

        img = cv2.imread(str(self.doc.image_path))
        if img is None:
            QMessageBox.critical(self, "Read Error", "이미지를 읽을 수 없음")
            return []

        # 사용자 지정 보드 영역 있으면 사용
        board_rect = self.canvas.board_rect

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        try:
            raw = generate_bboxes(img, profile, board_rect=board_rect)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Auto-Detect Error", f"탐지 실패:\n{e}")
            return []
        QApplication.restoreOverrideCursor()

        return [
            BBox(
                name=r["name"],
                xmin=r["xmin"], ymin=r["ymin"],
                xmax=r["xmax"], ymax=r["ymax"],
            )
            for r in raw
        ]

    def _auto_label_replace(self):
        """자동 탐지 → 기존 bbox 전부 대체."""
        if self.doc is None:
            return
        self._push_undo("auto-label replace")
        new_boxes = self._run_auto_detect()
        if not new_boxes:
            self._set_status("자동 탐지 결과 0개")
            return
        self.doc.bboxes = new_boxes
        self.doc.dirty = True
        self._on_doc_changed()
        self._set_status(f"🔍 Auto-Detect Replace: {len(new_boxes)} bboxes")

    def _auto_label_append(self):
        """자동 탐지 → 기존 bbox에 추가."""
        if self.doc is None:
            return
        self._push_undo("auto-label append")
        new_boxes = self._run_auto_detect()
        if not new_boxes:
            self._set_status("자동 탐지 결과 0개")
            return
        self.doc.bboxes.extend(new_boxes)
        self.doc.dirty = True
        self._on_doc_changed()
        self._set_status(f"➕ Auto-Detect Append: +{len(new_boxes)} bboxes")

    def _auto_label_batch(self):
        """라벨 없는 이미지들에 일괄 auto-label."""
        # 미라벨 이미지 찾기
        unlabeled = []
        for img in self.images:
            xml = self.label_dir / f"{img.stem}.xml"
            if not xml.exists():
                unlabeled.append(img)

        if not unlabeled:
            QMessageBox.information(self, "Auto-Label Batch",
                                    "모든 이미지에 이미 라벨이 있습니다.")
            return

        reply = QMessageBox.question(
            self, "Auto-Label Batch",
            f"{len(unlabeled)}개의 미라벨 이미지에 자동 라벨을 생성합니다.\n"
            f"기존 라벨은 건드리지 않습니다. 계속할까요?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            import cv2
            sys.path.insert(0, str(Path(__file__).parent))
            from auto_label_v2 import generate_bboxes, save_pascal_voc_xml
            from _paths import TOOLS_DIR, PROFILE_PATH
            sys.path.insert(0, str(TOOLS_DIR))
            from cell_aware_analyzer import load_profile
            profile = load_profile(str(PROFILE_PATH))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"모듈 로드 실패:\n{e}")
            return

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        total_bbox = 0
        ok = 0
        err = 0
        for img_path in unlabeled:
            img = cv2.imread(str(img_path))
            if img is None:
                err += 1
                continue
            try:
                raw = generate_bboxes(img, profile)
                h, w = img.shape[:2]
                xml_path = self.label_dir / f"{img_path.stem}.xml"
                save_pascal_voc_xml(img_path, (w, h), raw, xml_path)
                total_bbox += len(raw)
                ok += 1
            except Exception:
                err += 1
        QApplication.restoreOverrideCursor()

        # 현재 이미지 reload (새 XML 있을 수 있음)
        self._load_index(self.current_idx)
        QMessageBox.information(
            self, "Batch Complete",
            f"완료!\n\nOK: {ok}\nError: {err}\nTotal bboxes: {total_bbox:,}",
        )

    def closeEvent(self, event):
        # 현재 보드 영역 저장
        if self.doc and self.canvas.board_rect is not None:
            self.board_regions[self.doc.image_path.name] = list(self.canvas.board_rect)
            self._save_board_regions()
        if self.doc and self.doc.dirty:
            r = QMessageBox.question(
                self, "Unsaved changes",
                "Unsaved changes exist. Save before closing?",
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
    # 자동 경로 탐지
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _paths import LABEL_IMAGES_DIR, LABEL_XML_DIR, CLASSES_FILE

    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, default=LABEL_IMAGES_DIR)
    ap.add_argument("--labels", type=Path, default=LABEL_XML_DIR)
    ap.add_argument("--classes", type=Path, default=CLASSES_FILE)
    args = ap.parse_args()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow(args.dir, args.labels, args.classes)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
