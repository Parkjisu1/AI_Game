"""
Unity Prefab/Scene UI Metadata Parser
======================================
.prefab and .unity files from Unity projects are parsed to extract
detailed UI component metadata (RectTransform, Canvas, Button, ScrollRect,
LayoutGroup, Text/TMP, Image, ContentSizeFitter, CanvasGroup).

Unity serializes these files as multi-document YAML with custom tags:
    --- !u!{classID} &{fileID}
Standard YAML parsers choke on these tags, so we use regex-based parsing.

Output is saved to E:\\AI\\db\\ui_meta\\{project_name}\\ with per-component
JSON files and a project summary.

CLI:
    python unity_prefab_parser.py <assets_path> <project_name> [genre]
    python unity_prefab_parser.py --aggregate
"""

import os
import re
import json
import sys
import statistics
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from collections import Counter, defaultdict

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DB_UI_META_ROOT = r"E:\AI\db\ui_meta"

CLASS_ID_MAP = {
    1: "GameObject",
    4: "Transform",
    114: "MonoBehaviour",
    222: "CanvasRenderer",
    223: "Canvas",
    224: "RectTransform",
    225: "CanvasGroup",
    226: "CanvasScaler",
}

# Button size classification (based on the larger dimension)
BUTTON_SIZE_RANGES = {
    "large":  (300, 500),
    "medium": (200, 300),
    "small":  (100, 200),
}


# ---------------------------------------------------------------------------
# Low-level parsing helpers
# ---------------------------------------------------------------------------

def _parse_inline_dict(text: str) -> Dict[str, Any]:
    """Parse Unity inline dict format like {x: 0.5, y: 1, z: 0} or {fileID: 123, guid: abc...}."""
    text = text.strip()
    if not text.startswith("{"):
        return {}
    pairs = re.findall(r'(\w+):\s*([^,}]+)', text)
    result = {}
    for k, v in pairs:
        v = v.strip()
        # Try numeric conversion
        try:
            if '.' in v or 'e' in v.lower():
                result[k] = float(v)
            else:
                result[k] = int(v)
        except ValueError:
            result[k] = v
    return result


def _parse_reference(text: str) -> Optional[Dict[str, Any]]:
    """Parse a Unity object reference like {fileID: 12345} or {fileID: 123, guid: abc, type: 3}."""
    d = _parse_inline_dict(text)
    if "fileID" in d:
        return d
    return None


def _extract_field(lines: List[str], field_name: str) -> Optional[str]:
    """Find a top-level or nested field by name and return its raw value string."""
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(field_name + ":"):
            _, _, val = stripped.partition(":")
            return val.strip()
    return None


def _extract_nested_block(lines: List[str], field_name: str) -> List[str]:
    """Extract the indented block below a given field name."""
    collecting = False
    base_indent = 0
    block = []
    for line in lines:
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        if not collecting:
            if stripped.startswith(field_name + ":"):
                collecting = True
                base_indent = indent
                # If there's an inline value, skip block extraction
                _, _, val = stripped.partition(":")
                if val.strip() and val.strip() != "":
                    return []
        else:
            if indent > base_indent:
                block.append(line)
            else:
                break
    return block


def _parse_color(text: str) -> Optional[Dict[str, float]]:
    """Parse {r: 1, g: 1, b: 1, a: 1} color format."""
    d = _parse_inline_dict(text)
    if "r" in d:
        return {k: float(d.get(k, 0)) for k in ("r", "g", "b", "a")}
    return None


def _parse_vector2(text: str) -> Optional[Dict[str, float]]:
    """Parse {x: 0, y: 0} vector format."""
    d = _parse_inline_dict(text)
    if "x" in d:
        return {k: float(d.get(k, 0)) for k in ("x", "y") if k in d}
    return None


# ---------------------------------------------------------------------------
# Document splitting
# ---------------------------------------------------------------------------

_DOC_HEADER_RE = re.compile(r'^--- !u!(\d+) &(\d+)', re.MULTILINE)


def split_unity_documents(content: str) -> List[Tuple[int, str, str]]:
    """Split Unity YAML content into documents.

    Returns list of (classID, fileID, body_text).
    """
    matches = list(_DOC_HEADER_RE.finditer(content))
    docs = []
    for i, m in enumerate(matches):
        class_id = int(m.group(1))
        file_id = m.group(2)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        body = content[start:end]
        docs.append((class_id, file_id, body))
    return docs


# ---------------------------------------------------------------------------
# Component parsers
# ---------------------------------------------------------------------------

def parse_game_object(file_id: str, body: str) -> Dict[str, Any]:
    lines = body.split("\n")
    name = _extract_field(lines, "m_Name") or ""
    is_active = _extract_field(lines, "m_IsActive")
    # Extract component references
    components = []
    in_component_block = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("m_Component:"):
            in_component_block = True
            continue
        if in_component_block:
            if stripped.startswith("- component:"):
                ref = _parse_reference(stripped.split("component:")[1])
                if ref:
                    components.append(ref)
            elif not stripped.startswith("-") and not stripped.startswith("component"):
                if len(stripped) > 0 and not stripped.startswith("{"):
                    in_component_block = False
    return {
        "type": "GameObject",
        "fileID": file_id,
        "name": name,
        "isActive": is_active == "1" if is_active else True,
        "components": components,
    }


def parse_rect_transform(file_id: str, body: str) -> Dict[str, Any]:
    lines = body.split("\n")
    result = {
        "type": "RectTransform",
        "fileID": file_id,
    }
    field_map = {
        "m_AnchorMin": "m_AnchorMin",
        "m_AnchorMax": "m_AnchorMax",
        "m_AnchoredPosition": "m_AnchoredPosition",
        "m_SizeDelta": "m_SizeDelta",
        "m_Pivot": "m_Pivot",
    }
    for field, key in field_map.items():
        val = _extract_field(lines, field)
        if val:
            parsed = _parse_vector2(val)
            if parsed:
                result[key] = parsed

    # Parent reference
    father = _extract_field(lines, "m_Father")
    if father:
        ref = _parse_reference(father)
        if ref:
            result["m_Father"] = ref

    # GameObject reference
    go = _extract_field(lines, "m_GameObject")
    if go:
        ref = _parse_reference(go)
        if ref:
            result["m_GameObject"] = ref

    # Children
    children = []
    in_children = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("m_Children:"):
            in_children = True
            # Check inline empty array
            if "[]" in stripped:
                break
            continue
        if in_children:
            if stripped.startswith("- {"):
                ref = _parse_reference(stripped[2:])
                if ref:
                    children.append(ref)
            elif not stripped.startswith("-"):
                break
    result["m_Children"] = children

    return result


def parse_canvas(file_id: str, body: str) -> Dict[str, Any]:
    lines = body.split("\n")
    result = {
        "type": "Canvas",
        "fileID": file_id,
    }
    render_mode = _extract_field(lines, "m_RenderMode")
    if render_mode is not None:
        try:
            result["m_RenderMode"] = int(render_mode)
        except ValueError:
            result["m_RenderMode"] = render_mode

    sorting_order = _extract_field(lines, "m_SortingOrder")
    if sorting_order is not None:
        try:
            result["m_SortingOrder"] = int(sorting_order)
        except ValueError:
            result["m_SortingOrder"] = sorting_order

    go = _extract_field(lines, "m_GameObject")
    if go:
        ref = _parse_reference(go)
        if ref:
            result["m_GameObject"] = ref

    return result


def parse_canvas_scaler(file_id: str, body: str) -> Dict[str, Any]:
    lines = body.split("\n")
    result = {
        "type": "CanvasScaler",
        "fileID": file_id,
    }
    ref_res = _extract_field(lines, "m_ReferenceResolution")
    if ref_res:
        parsed = _parse_vector2(ref_res)
        if parsed:
            result["m_ReferenceResolution"] = parsed

    match_val = _extract_field(lines, "m_MatchWidthOrHeight")
    if match_val is not None:
        try:
            result["m_MatchWidthOrHeight"] = float(match_val)
        except ValueError:
            pass

    scale_mode = _extract_field(lines, "m_UiScaleMode")
    if scale_mode is not None:
        try:
            result["m_UiScaleMode"] = int(scale_mode)
        except ValueError:
            pass

    go = _extract_field(lines, "m_GameObject")
    if go:
        ref = _parse_reference(go)
        if ref:
            result["m_GameObject"] = ref

    return result


def parse_canvas_group(file_id: str, body: str) -> Dict[str, Any]:
    lines = body.split("\n")
    result = {
        "type": "CanvasGroup",
        "fileID": file_id,
    }
    for field in ("m_Alpha", "m_Interactable", "m_BlocksRaycasts", "m_IgnoreParentGroups"):
        val = _extract_field(lines, field)
        if val is not None:
            try:
                result[field] = float(val) if "." in val else int(val)
            except ValueError:
                pass

    go = _extract_field(lines, "m_GameObject")
    if go:
        ref = _parse_reference(go)
        if ref:
            result["m_GameObject"] = ref

    return result


# ---------------------------------------------------------------------------
# MonoBehaviour type detection and parsing
# ---------------------------------------------------------------------------

def _detect_monobehaviour_type(body: str) -> str:
    """Detect the UI component type of a MonoBehaviour by field pattern matching.

    Returns one of: Button, ScrollRect, Image, Text, LayoutGroup, ContentSizeFitter, Unknown
    """
    # Order matters: check more specific patterns first
    if "m_HorizontalFit:" in body or "m_VerticalFit:" in body:
        return "ContentSizeFitter"
    if "m_CellSize:" in body and "m_Spacing:" in body:
        return "GridLayoutGroup"
    if "m_Spacing:" in body and "m_Padding:" in body and "m_ChildAlignment:" in body:
        # Distinguish Vertical vs Horizontal
        # Both have the same fields; check for m_ReverseArrangement or rely on m_ChildForceExpandWidth pattern
        # Actually in Unity both Vertical and Horizontal LayoutGroup share the same fields.
        # We'll try to detect by m_ChildForceExpandHeight vs Width tendencies, but really
        # both have both fields. We'll mark as LayoutGroup and let context decide.
        return "LayoutGroup"
    if "m_Colors:" in body and "m_NormalColor:" in body:
        return "Button"
    if ("m_Horizontal:" in body or "m_Vertical:" in body) and "m_DecelerationRate:" in body:
        return "ScrollRect"
    if "m_FontSize:" in body and ("m_Alignment:" in body or "m_TextAlignment:" in body):
        return "Text"
    if "m_Sprite:" in body and "m_Type:" in body and "m_Color:" in body:
        return "Image"

    return "Unknown"


def _parse_button(file_id: str, body: str, lines: List[str]) -> Dict[str, Any]:
    result = {
        "type": "Button",
        "fileID": file_id,
    }

    # Parse m_Colors block
    colors_block = _extract_nested_block(lines, "m_Colors")
    if colors_block:
        colors = {}
        for color_field in ("m_NormalColor", "m_HighlightedColor", "m_PressedColor",
                            "m_SelectedColor", "m_DisabledColor"):
            val = _extract_field(colors_block, color_field)
            if val:
                parsed = _parse_color(val)
                if parsed:
                    colors[color_field] = parsed
        if colors:
            result["m_Colors"] = colors

    # Navigation
    nav_block = _extract_nested_block(lines, "m_Navigation")
    if nav_block:
        mode = _extract_field(nav_block, "m_Mode")
        if mode is not None:
            result["m_Navigation"] = {"m_Mode": int(mode) if mode.isdigit() else mode}

    # m_Interactable
    interactable = _extract_field(lines, "m_Interactable")
    if interactable is not None:
        result["m_Interactable"] = int(interactable) if interactable.isdigit() else interactable

    # GameObject reference
    go = _extract_field(lines, "m_GameObject")
    if go:
        ref = _parse_reference(go)
        if ref:
            result["m_GameObject"] = ref

    return result


def _parse_scroll_rect(file_id: str, body: str, lines: List[str]) -> Dict[str, Any]:
    result = {
        "type": "ScrollRect",
        "fileID": file_id,
    }
    for field in ("m_Horizontal", "m_Vertical", "m_Inertia"):
        val = _extract_field(lines, field)
        if val is not None:
            try:
                result[field] = int(val)
            except ValueError:
                pass
    for field in ("m_DecelerationRate", "m_ScrollSensitivity", "m_ElasticitY"):
        val = _extract_field(lines, field)
        if val is not None:
            try:
                result[field] = float(val)
            except ValueError:
                pass

    # Also grab m_DecelerationRate and m_ScrollSensitivity (already handled above)

    go = _extract_field(lines, "m_GameObject")
    if go:
        ref = _parse_reference(go)
        if ref:
            result["m_GameObject"] = ref

    return result


def _parse_image(file_id: str, body: str, lines: List[str]) -> Dict[str, Any]:
    result = {
        "type": "Image",
        "fileID": file_id,
    }
    # m_Type
    m_type = _extract_field(lines, "m_Type")
    if m_type is not None:
        try:
            result["m_Type"] = int(m_type)
        except ValueError:
            pass

    # m_Color
    color = _extract_field(lines, "m_Color")
    if color:
        parsed = _parse_color(color)
        if parsed:
            result["m_Color"] = parsed

    # m_Sprite
    sprite = _extract_field(lines, "m_Sprite")
    if sprite:
        ref = _parse_reference(sprite)
        if ref:
            result["m_Sprite"] = ref

    # m_RaycastTarget
    raycast = _extract_field(lines, "m_RaycastTarget")
    if raycast is not None:
        try:
            result["m_RaycastTarget"] = int(raycast)
        except ValueError:
            pass

    go = _extract_field(lines, "m_GameObject")
    if go:
        ref = _parse_reference(go)
        if ref:
            result["m_GameObject"] = ref

    return result


def _parse_text(file_id: str, body: str, lines: List[str]) -> Dict[str, Any]:
    result = {
        "type": "Text",
        "fileID": file_id,
    }
    font_size = _extract_field(lines, "m_FontSize") or _extract_field(lines, "m_fontSize")
    if font_size is not None:
        try:
            result["m_FontSize"] = float(font_size)
        except ValueError:
            pass

    alignment = (_extract_field(lines, "m_Alignment")
                 or _extract_field(lines, "m_TextAlignment")
                 or _extract_field(lines, "m_textAlignment"))
    if alignment is not None:
        try:
            result["m_Alignment"] = int(alignment)
        except ValueError:
            result["m_Alignment"] = alignment

    color = _extract_field(lines, "m_Color")
    if color:
        parsed = _parse_color(color)
        if parsed:
            result["m_Color"] = parsed

    # Font material / font asset reference
    font_asset = _extract_field(lines, "m_fontAsset")
    if font_asset:
        ref = _parse_reference(font_asset)
        if ref:
            result["m_fontAsset"] = ref

    # m_Text content (may be multiline, just grab the first line)
    text_val = _extract_field(lines, "m_Text") or _extract_field(lines, "m_text")
    if text_val is not None:
        result["m_Text"] = text_val[:200]  # Truncate long text

    go = _extract_field(lines, "m_GameObject")
    if go:
        ref = _parse_reference(go)
        if ref:
            result["m_GameObject"] = ref

    return result


def _parse_layout_group(file_id: str, body: str, lines: List[str], subtype: str) -> Dict[str, Any]:
    """Parse VerticalLayoutGroup, HorizontalLayoutGroup, or GridLayoutGroup."""
    result = {
        "type": subtype if subtype != "LayoutGroup" else "LayoutGroup",
        "fileID": file_id,
    }

    # Spacing - scalar for V/H, vector for Grid (m_CellSize, m_Spacing as vector)
    if subtype == "GridLayoutGroup":
        cell_size = _extract_field(lines, "m_CellSize")
        if cell_size:
            parsed = _parse_vector2(cell_size)
            if parsed:
                result["m_CellSize"] = parsed
        spacing = _extract_field(lines, "m_Spacing")
        if spacing:
            parsed = _parse_vector2(spacing)
            if parsed:
                result["m_Spacing"] = parsed
            else:
                try:
                    result["m_Spacing"] = float(spacing)
                except ValueError:
                    pass
        constraint = _extract_field(lines, "m_Constraint")
        if constraint is not None:
            try:
                result["m_Constraint"] = int(constraint)
            except ValueError:
                pass
        constraint_count = _extract_field(lines, "m_ConstraintCount")
        if constraint_count is not None:
            try:
                result["m_ConstraintCount"] = int(constraint_count)
            except ValueError:
                pass
    else:
        spacing = _extract_field(lines, "m_Spacing")
        if spacing is not None:
            try:
                result["m_Spacing"] = float(spacing)
            except ValueError:
                pass

    # Padding
    padding_block = _extract_nested_block(lines, "m_Padding")
    if padding_block:
        padding = {}
        for p_field in ("m_Left", "m_Right", "m_Top", "m_Bottom"):
            val = _extract_field(padding_block, p_field)
            if val is not None:
                try:
                    padding[p_field] = int(val)
                except ValueError:
                    pass
        if padding:
            result["m_Padding"] = padding

    # ChildAlignment
    child_align = _extract_field(lines, "m_ChildAlignment")
    if child_align is not None:
        try:
            result["m_ChildAlignment"] = int(child_align)
        except ValueError:
            pass

    go = _extract_field(lines, "m_GameObject")
    if go:
        ref = _parse_reference(go)
        if ref:
            result["m_GameObject"] = ref

    return result


def _parse_content_size_fitter(file_id: str, body: str, lines: List[str]) -> Dict[str, Any]:
    result = {
        "type": "ContentSizeFitter",
        "fileID": file_id,
    }
    for field in ("m_HorizontalFit", "m_VerticalFit"):
        val = _extract_field(lines, field)
        if val is not None:
            try:
                result[field] = int(val)
            except ValueError:
                pass

    go = _extract_field(lines, "m_GameObject")
    if go:
        ref = _parse_reference(go)
        if ref:
            result["m_GameObject"] = ref

    return result


def parse_monobehaviour(file_id: str, body: str) -> Dict[str, Any]:
    """Parse a MonoBehaviour document and detect its UI component type."""
    lines = body.split("\n")
    mb_type = _detect_monobehaviour_type(body)

    if mb_type == "Button":
        return _parse_button(file_id, body, lines)
    elif mb_type == "ScrollRect":
        return _parse_scroll_rect(file_id, body, lines)
    elif mb_type == "Image":
        return _parse_image(file_id, body, lines)
    elif mb_type == "Text":
        return _parse_text(file_id, body, lines)
    elif mb_type == "GridLayoutGroup":
        return _parse_layout_group(file_id, body, lines, "GridLayoutGroup")
    elif mb_type == "LayoutGroup":
        return _parse_layout_group(file_id, body, lines, "LayoutGroup")
    elif mb_type == "ContentSizeFitter":
        return _parse_content_size_fitter(file_id, body, lines)
    else:
        # Unknown MonoBehaviour - skip for UI metadata purposes
        return {
            "type": "Unknown",
            "fileID": file_id,
        }


# ---------------------------------------------------------------------------
# File-level parser
# ---------------------------------------------------------------------------

class ParsedFile:
    """Holds all parsed components from a single .prefab or .unity file."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.file_name = os.path.splitext(os.path.basename(file_path))[0]
        self.file_ext = os.path.splitext(file_path)[1].lower()
        self.is_prefab = self.file_ext == ".prefab"
        self.is_scene = self.file_ext == ".unity"

        # Indexed by fileID
        self.game_objects: Dict[str, Dict] = {}
        self.rect_transforms: Dict[str, Dict] = {}
        self.canvases: List[Dict] = []
        self.canvas_scalers: List[Dict] = []
        self.canvas_groups: List[Dict] = []
        self.buttons: List[Dict] = []
        self.scroll_rects: List[Dict] = []
        self.images: List[Dict] = []
        self.texts: List[Dict] = []
        self.layout_groups: List[Dict] = []
        self.content_size_fitters: List[Dict] = []

    def _resolve_game_object_name(self, component: Dict) -> str:
        """Given a component dict with m_GameObject ref, resolve the GO name."""
        go_ref = component.get("m_GameObject", {})
        go_fid = str(go_ref.get("fileID", ""))
        go = self.game_objects.get(go_fid)
        if go:
            return go.get("name", "")
        return ""

    def _resolve_rect_transform_for_go(self, go_file_id: str) -> Optional[Dict]:
        """Find the RectTransform that belongs to a given GameObject fileID."""
        for rt in self.rect_transforms.values():
            rt_go = rt.get("m_GameObject", {})
            if str(rt_go.get("fileID", "")) == str(go_file_id):
                return rt
        return None

    def enrich_components(self):
        """After all documents are parsed, attach GO names and RT sizes to components."""
        component_lists = [
            self.buttons, self.scroll_rects, self.images, self.texts,
            self.layout_groups, self.content_size_fitters,
            self.canvases, self.canvas_scalers, self.canvas_groups,
        ]
        for comp_list in component_lists:
            for comp in comp_list:
                go_name = self._resolve_game_object_name(comp)
                if go_name:
                    comp["gameObjectName"] = go_name

                # Attach RectTransform size
                go_ref = comp.get("m_GameObject", {})
                go_fid = str(go_ref.get("fileID", ""))
                if go_fid:
                    rt = self._resolve_rect_transform_for_go(go_fid)
                    if rt:
                        size = rt.get("m_SizeDelta")
                        if size:
                            comp["rectSize"] = size
                        anchored_pos = rt.get("m_AnchoredPosition")
                        if anchored_pos:
                            comp["anchoredPosition"] = anchored_pos
                        anchor_min = rt.get("m_AnchorMin")
                        if anchor_min:
                            comp["anchorMin"] = anchor_min
                        anchor_max = rt.get("m_AnchorMax")
                        if anchor_max:
                            comp["anchorMax"] = anchor_max

                # Remove internal m_GameObject reference from output (already resolved)
                comp.pop("m_GameObject", None)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fileName": self.file_name,
            "filePath": self.file_path,
            "fileType": "prefab" if self.is_prefab else "scene",
            "gameObjectCount": len(self.game_objects),
            "canvases": self.canvases,
            "canvasScalers": self.canvas_scalers,
            "canvasGroups": self.canvas_groups,
            "buttons": self.buttons,
            "scrollRects": self.scroll_rects,
            "images": self.images,
            "texts": self.texts,
            "layoutGroups": self.layout_groups,
            "contentSizeFitters": self.content_size_fitters,
            "rectTransformCount": len(self.rect_transforms),
        }


def parse_unity_file(file_path: str) -> Optional[ParsedFile]:
    """Parse a single .prefab or .unity file and return a ParsedFile."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                content = f.read()
        except Exception:
            return None
    except Exception:
        return None

    pf = ParsedFile(file_path)
    documents = split_unity_documents(content)

    for class_id, file_id, body in documents:
        if class_id == 1:
            go = parse_game_object(file_id, body)
            pf.game_objects[file_id] = go

        elif class_id == 224:
            rt = parse_rect_transform(file_id, body)
            pf.rect_transforms[file_id] = rt

        elif class_id == 223:
            canvas = parse_canvas(file_id, body)
            pf.canvases.append(canvas)

        elif class_id == 226:
            scaler = parse_canvas_scaler(file_id, body)
            pf.canvas_scalers.append(scaler)

        elif class_id == 225:
            cg = parse_canvas_group(file_id, body)
            pf.canvas_groups.append(cg)

        elif class_id == 114:
            comp = parse_monobehaviour(file_id, body)
            comp_type = comp.get("type", "Unknown")
            if comp_type == "Button":
                pf.buttons.append(comp)
            elif comp_type == "ScrollRect":
                pf.scroll_rects.append(comp)
            elif comp_type == "Image":
                pf.images.append(comp)
            elif comp_type == "Text":
                pf.texts.append(comp)
            elif comp_type in ("LayoutGroup", "GridLayoutGroup"):
                pf.layout_groups.append(comp)
            elif comp_type == "ContentSizeFitter":
                pf.content_size_fitters.append(comp)
            # Unknown MonoBehaviours are silently skipped

    pf.enrich_components()
    return pf


# ---------------------------------------------------------------------------
# Directory scanner
# ---------------------------------------------------------------------------

def scan_assets_directory(assets_path: str) -> List[ParsedFile]:
    """Recursively find and parse all .prefab and .unity files under a path."""
    results = []
    extensions = {".prefab", ".unity"}

    for root, dirs, files in os.walk(assets_path):
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext in extensions:
                fpath = os.path.join(root, fname)
                pf = parse_unity_file(fpath)
                if pf:
                    results.append(pf)

    return results


# ---------------------------------------------------------------------------
# Output generation
# ---------------------------------------------------------------------------

def _classify_button_size(width: float, height: float) -> str:
    """Classify a button by its larger dimension."""
    larger = max(abs(width), abs(height))
    for label, (lo, hi) in BUTTON_SIZE_RANGES.items():
        if lo <= larger < hi:
            return label
    if larger >= 500:
        return "large"
    if larger < 100:
        return "small"
    return "medium"


def generate_project_output(parsed_files: List[ParsedFile], project_name: str,
                            genre: str = "Generic") -> Dict[str, Any]:
    """Generate all output JSON files for a project.

    Returns the summary dict.
    """
    output_root = os.path.join(DB_UI_META_ROOT, project_name)
    prefabs_dir = os.path.join(output_root, "prefabs")
    os.makedirs(prefabs_dir, exist_ok=True)

    # Aggregate collections
    all_buttons = []
    all_scrolls = []
    all_layouts = []
    all_texts = []
    all_images = []
    all_canvas_settings = []
    all_content_size_fitters = []

    total_prefabs = 0
    total_scenes = 0

    for pf in parsed_files:
        if pf.is_prefab:
            total_prefabs += 1
        elif pf.is_scene:
            total_scenes += 1

        # Tag each component with source file
        for btn in pf.buttons:
            btn["sourceFile"] = pf.file_name
            all_buttons.append(btn)
        for sr in pf.scroll_rects:
            sr["sourceFile"] = pf.file_name
            all_scrolls.append(sr)
        for lg in pf.layout_groups:
            lg["sourceFile"] = pf.file_name
            all_layouts.append(lg)
        for txt in pf.texts:
            txt["sourceFile"] = pf.file_name
            all_texts.append(txt)
        for img in pf.images:
            img["sourceFile"] = pf.file_name
            all_images.append(img)
        for csf in pf.content_size_fitters:
            csf["sourceFile"] = pf.file_name
            all_content_size_fitters.append(csf)

        # Canvas settings: pair Canvas with CanvasScaler from same file
        for canvas in pf.canvases:
            entry = {
                "sourceFile": pf.file_name,
                "canvas": canvas,
                "canvasScalers": pf.canvas_scalers,
            }
            all_canvas_settings.append(entry)

        # Per-prefab/scene detail file
        detail_path = os.path.join(prefabs_dir, f"{pf.file_name}.json")
        _write_json(detail_path, pf.to_dict())

    # Button size distribution
    btn_size_dist = {
        "large": {"range": list(BUTTON_SIZE_RANGES["large"]), "count": 0},
        "medium": {"range": list(BUTTON_SIZE_RANGES["medium"]), "count": 0},
        "small": {"range": list(BUTTON_SIZE_RANGES["small"]), "count": 0},
    }
    for btn in all_buttons:
        rs = btn.get("rectSize", {})
        w = rs.get("x", 0)
        h = rs.get("y", 0)
        category = _classify_button_size(w, h)
        if category in btn_size_dist:
            btn_size_dist[category]["count"] += 1

    # Summary
    summary = {
        "project": project_name,
        "genre": genre,
        "totalPrefabs": total_prefabs,
        "totalScenes": total_scenes,
        "buttonCount": len(all_buttons),
        "scrollRectCount": len(all_scrolls),
        "layoutGroupCount": len(all_layouts),
        "textCount": len(all_texts),
        "imageCount": len(all_images),
        "contentSizeFitterCount": len(all_content_size_fitters),
        "canvasSettings": [
            {
                "sourceFile": cs["sourceFile"],
                "renderMode": cs["canvas"].get("m_RenderMode"),
                "sortingOrder": cs["canvas"].get("m_SortingOrder"),
                "scalers": [
                    {
                        "referenceResolution": s.get("m_ReferenceResolution"),
                        "matchWidthOrHeight": s.get("m_MatchWidthOrHeight"),
                        "uiScaleMode": s.get("m_UiScaleMode"),
                    }
                    for s in cs.get("canvasScalers", [])
                ],
            }
            for cs in all_canvas_settings
        ],
        "buttonSizeDistribution": btn_size_dist,
    }

    # Write all JSON files
    _write_json(os.path.join(output_root, "summary.json"), summary)
    _write_json(os.path.join(output_root, "canvas_settings.json"), all_canvas_settings)
    _write_json(os.path.join(output_root, "buttons.json"), all_buttons)
    _write_json(os.path.join(output_root, "scrolls.json"), all_scrolls)
    _write_json(os.path.join(output_root, "layouts.json"), all_layouts)
    _write_json(os.path.join(output_root, "texts.json"), all_texts)

    return summary


def _write_json(path: str, data: Any):
    """Write data to a JSON file with UTF-8 encoding."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# Aggregation across projects
# ---------------------------------------------------------------------------

def _collect_numeric_field(items: List[Dict], field_path: str) -> List[float]:
    """Collect numeric values from a nested field path like 'rectSize.x'."""
    parts = field_path.split(".")
    values = []
    for item in items:
        obj = item
        for p in parts:
            if isinstance(obj, dict):
                obj = obj.get(p)
            else:
                obj = None
                break
        if obj is not None:
            try:
                values.append(float(obj))
            except (ValueError, TypeError):
                pass
    return values


def _compute_stats(values: List[float]) -> Dict[str, Any]:
    """Compute min, max, avg, median, mode for a list of values."""
    if not values:
        return {"min": None, "max": None, "avg": None, "median": None, "mode": None, "count": 0}

    rounded = [round(v, 2) for v in values]
    counter = Counter(rounded)
    mode_val = counter.most_common(1)[0][0] if counter else None

    return {
        "min": round(min(values), 2),
        "max": round(max(values), 2),
        "avg": round(statistics.mean(values), 2),
        "median": round(statistics.median(values), 2),
        "mode": mode_val,
        "count": len(values),
    }


def aggregate_all_projects():
    """Read all project outputs under DB_UI_META_ROOT and create aggregated standards."""
    agg_dir = os.path.join(DB_UI_META_ROOT, "aggregated")
    os.makedirs(agg_dir, exist_ok=True)

    all_buttons = []
    all_scrolls = []
    all_texts = []
    all_layouts = []

    # Scan all project directories
    if not os.path.exists(DB_UI_META_ROOT):
        print(f"[Aggregate] No ui_meta root found at {DB_UI_META_ROOT}")
        return

    for entry in os.listdir(DB_UI_META_ROOT):
        project_dir = os.path.join(DB_UI_META_ROOT, entry)
        if not os.path.isdir(project_dir) or entry == "aggregated":
            continue

        # Load per-project JSON files
        buttons_path = os.path.join(project_dir, "buttons.json")
        scrolls_path = os.path.join(project_dir, "scrolls.json")
        texts_path = os.path.join(project_dir, "texts.json")
        layouts_path = os.path.join(project_dir, "layouts.json")

        if os.path.exists(buttons_path):
            with open(buttons_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for item in data:
                    item["project"] = entry
                all_buttons.extend(data)

        if os.path.exists(scrolls_path):
            with open(scrolls_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for item in data:
                    item["project"] = entry
                all_scrolls.extend(data)

        if os.path.exists(texts_path):
            with open(texts_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for item in data:
                    item["project"] = entry
                all_texts.extend(data)

        if os.path.exists(layouts_path):
            with open(layouts_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for item in data:
                    item["project"] = entry
                all_layouts.extend(data)

    # Button standards
    button_standards = {
        "totalButtons": len(all_buttons),
        "width": _compute_stats(_collect_numeric_field(all_buttons, "rectSize.x")),
        "height": _compute_stats(_collect_numeric_field(all_buttons, "rectSize.y")),
        "sizeDistribution": {
            "large": 0, "medium": 0, "small": 0,
        },
        "projectBreakdown": defaultdict(int),
    }
    for btn in all_buttons:
        rs = btn.get("rectSize", {})
        cat = _classify_button_size(rs.get("x", 0), rs.get("y", 0))
        button_standards["sizeDistribution"][cat] += 1
        button_standards["projectBreakdown"][btn.get("project", "unknown")] += 1
    button_standards["projectBreakdown"] = dict(button_standards["projectBreakdown"])

    # Scroll standards
    scroll_standards = {
        "totalScrollRects": len(all_scrolls),
        "horizontalCount": sum(1 for s in all_scrolls if s.get("m_Horizontal") == 1),
        "verticalCount": sum(1 for s in all_scrolls if s.get("m_Vertical") == 1),
        "inertiaEnabled": sum(1 for s in all_scrolls if s.get("m_Inertia") == 1),
        "decelerationRate": _compute_stats(
            _collect_numeric_field(all_scrolls, "m_DecelerationRate")
        ),
        "scrollSensitivity": _compute_stats(
            _collect_numeric_field(all_scrolls, "m_ScrollSensitivity")
        ),
    }

    # Text standards
    text_standards = {
        "totalTexts": len(all_texts),
        "fontSize": _compute_stats(_collect_numeric_field(all_texts, "m_FontSize")),
        "alignmentDistribution": dict(Counter(
            t.get("m_Alignment") for t in all_texts if t.get("m_Alignment") is not None
        )),
    }

    # Layout standards
    layout_standards = {
        "totalLayoutGroups": len(all_layouts),
        "typeDistribution": dict(Counter(lg.get("type", "Unknown") for lg in all_layouts)),
        "spacing": _compute_stats(_collect_numeric_field(all_layouts, "m_Spacing")),
        "childAlignmentDistribution": dict(Counter(
            lg.get("m_ChildAlignment") for lg in all_layouts if lg.get("m_ChildAlignment") is not None
        )),
    }

    _write_json(os.path.join(agg_dir, "button_standards.json"), button_standards)
    _write_json(os.path.join(agg_dir, "scroll_standards.json"), scroll_standards)
    _write_json(os.path.join(agg_dir, "text_standards.json"), text_standards)
    _write_json(os.path.join(agg_dir, "layout_standards.json"), layout_standards)

    print(f"[Aggregate] Aggregated {len(all_buttons)} buttons, {len(all_scrolls)} scrolls, "
          f"{len(all_texts)} texts, {len(all_layouts)} layouts across all projects.")
    print(f"[Aggregate] Output: {agg_dir}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Unity Prefab/Scene UI Metadata Parser")
        print()
        print("Usage:")
        print("  python unity_prefab_parser.py <assets_path> <project_name> [genre]")
        print("  python unity_prefab_parser.py --aggregate")
        print()
        print("Examples:")
        print("  python unity_prefab_parser.py E:\\Projects\\MyGame\\Assets MyGame RPG")
        print("  python unity_prefab_parser.py --aggregate")
        print()
        print(f"Output: {DB_UI_META_ROOT}\\<project_name>\\")
        sys.exit(1)

    if sys.argv[1] == "--aggregate":
        aggregate_all_projects()
        return

    assets_path = sys.argv[1]
    if len(sys.argv) < 3:
        print("Error: project_name is required.")
        print("Usage: python unity_prefab_parser.py <assets_path> <project_name> [genre]")
        sys.exit(1)

    project_name = sys.argv[2]
    genre = sys.argv[3] if len(sys.argv) > 3 else "Generic"

    if not os.path.isdir(assets_path):
        print(f"Error: '{assets_path}' is not a valid directory.")
        sys.exit(1)

    print(f"[Parser] Scanning: {assets_path}")
    print(f"[Parser] Project: {project_name}, Genre: {genre}")

    parsed_files = scan_assets_directory(assets_path)
    print(f"[Parser] Found {len(parsed_files)} files "
          f"({sum(1 for pf in parsed_files if pf.is_prefab)} prefabs, "
          f"{sum(1 for pf in parsed_files if pf.is_scene)} scenes)")

    if not parsed_files:
        print("[Parser] No .prefab or .unity files found. Exiting.")
        sys.exit(0)

    summary = generate_project_output(parsed_files, project_name, genre)

    output_dir = os.path.join(DB_UI_META_ROOT, project_name)
    print(f"[Parser] Output written to: {output_dir}")
    print(f"[Parser] Summary: {summary['buttonCount']} buttons, "
          f"{summary['scrollRectCount']} scrolls, "
          f"{summary['layoutGroupCount']} layouts, "
          f"{summary['textCount']} texts, "
          f"{summary['imageCount']} images")
    print(f"[Parser] Button size distribution: "
          f"L={summary['buttonSizeDistribution']['large']['count']}, "
          f"M={summary['buttonSizeDistribution']['medium']['count']}, "
          f"S={summary['buttonSizeDistribution']['small']['count']}")


if __name__ == "__main__":
    main()
