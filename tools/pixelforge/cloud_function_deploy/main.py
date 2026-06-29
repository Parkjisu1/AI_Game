"""
PixelForge Cloud Function — 이미지 → FieldMap 변환
===================================================
PNG base64 → 28색 팔레트 매핑 → FieldMap 텍스트 반환.
Google Cloud Functions에 배포.
"""

import base64
import json
import math
from io import BytesIO

import functions_framework
from PIL import Image
import numpy as np

# 인게임 28색 팔레트
PALETTE = {
    1:[252,106,175],2:[80,232,246],3:[137,80,248],4:[254,213,85],5:[115,254,102],
    6:[253,161,76],7:[255,255,255],8:[65,65,65],9:[110,168,250],10:[57,174,46],
    11:[252,94,94],12:[50,107,248],13:[58,165,139],14:[231,167,250],15:[183,199,251],
    16:[106,74,48],17:[254,227,169],18:[253,183,193],19:[158,61,94],20:[167,221,148],
    21:[89,46,126],22:[220,120,129],23:[217,217,231],24:[111,114,127],25:[252,56,165],
    26:[253,180,88],27:[137,10,8],28:[111,175,177],
}
PAL_ARR = np.array(list(PALETTE.values()), dtype=np.float32)
PAL_IDS = list(PALETTE.keys())


def image_to_fieldmap(img_bytes, cols, rows, allowed_colors=None):
    """PNG bytes → FieldMap 텍스트.

    Args:
        img_bytes: PNG 바이너리 데이터
        cols: 목표 가로 셀 수
        rows: 목표 세로 셀 수
        allowed_colors: 사용 가능한 색상 ID 리스트 (None=전체 28색)

    Returns:
        FieldMap 텍스트 ("01 02 ..\n03 01 ..")
    """
    img = Image.open(BytesIO(img_bytes)).convert("RGB")

    # 목표 크기로 리사이즈 (NEAREST — 블러 없이)
    if img.size != (cols, rows):
        img = img.resize((cols, rows), Image.NEAREST)

    arr = np.array(img).astype(np.float32)

    # 허용 색상 필터
    if allowed_colors and len(allowed_colors) > 0:
        pal = np.array([PALETTE[c] for c in allowed_colors if c in PALETTE], dtype=np.float32)
        ids = [c for c in allowed_colors if c in PALETTE]
    else:
        pal = PAL_ARR
        ids = PAL_IDS

    # 각 픽셀 → 가장 가까운 색상 ID
    lines = []
    for y in range(rows):
        line = []
        for x in range(cols):
            pixel = arr[y, x]
            dists = np.sum((pal - pixel) ** 2, axis=1)
            color_id = ids[int(np.argmin(dists))]
            line.append(f"{color_id:02d}")
        lines.append(" ".join(line))

    return "\n".join(lines)


@functions_framework.http
def convert(request):
    """HTTP 엔드포인트: POST { image_base64, cols, rows, allowed_colors? }"""

    # CORS
    if request.method == "OPTIONS":
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Max-Age": "3600",
        }
        return ("", 204, headers)

    headers = {"Access-Control-Allow-Origin": "*"}

    try:
        data = request.get_json(silent=True)
        if not data:
            return (json.dumps({"error": "JSON body required"}), 400, headers)

        img_b64 = data.get("image_base64", "")
        cols = int(data.get("cols", 20))
        rows = int(data.get("rows", 20))
        allowed = data.get("allowed_colors", None)

        if not img_b64:
            return (json.dumps({"error": "image_base64 required"}), 400, headers)

        # base64 디코딩
        clean_b64 = img_b64.replace("data:image/png;base64,", "").replace("data:image/jpeg;base64,", "")
        img_bytes = base64.b64decode(clean_b64)

        # 변환
        fieldmap = image_to_fieldmap(img_bytes, cols, rows, allowed)

        return (json.dumps({
            "fieldmap": fieldmap,
            "cols": cols,
            "rows": rows,
        }), 200, headers)

    except Exception as e:
        return (json.dumps({"error": str(e)}), 500, headers)
