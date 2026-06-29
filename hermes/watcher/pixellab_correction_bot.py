"""PixelLab Pixel Art Correction — headless browser automation.

PixelLab 공식 v2 API에 노출되지 않은 "Pixel Art Correction" 도구를
Playwright로 자동화. 사용자가 export한 storage_state(쿠키+localStorage)
를 로드해 로그인 세션을 그대로 사용한다.

흐름:
  1. storage_state.json 로드
  2. https://www.pixellab.ai/create?tool=pixel_art_correction 이동
  3. input[type=file]에 입력 이미지 업로드
  4. Correction strength slider 값 설정 (기본 0.1)
  5. "Generate" 버튼 클릭
  6. 결과 이미지 element 등장 대기
  7. 결과 이미지 src를 page.evaluate로 fetch → base64 stdout 출력

CLI:
  python pixellab_correction_bot.py \
    --image /tmp/in.png \
    --strength 0.1 \
    --auth ~/.hermes/watcher/pixellab_auth.json \
    --output /tmp/out.png

선택자(SELECTORS_*)는 best-guess. 실제 PixelLab UI 변경 시 보정 필요.
첫 실행 후 안 되면 SELECTORS_* 상수만 갱신.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

DEFAULT_AUTH = "/home/aimed/.hermes/watcher/pixellab_auth.json"
TOOL_URL = "https://www.pixellab.ai/create?tool=pixel_art_correction"

# ─── 선택자 후보들 (실제 UI 보면 정확히 1개만 남기면 됨) ───
# 파일 업로드: 보통 dropzone 아래 hidden input[type=file]
SELECTORS_FILE_INPUT = [
    'input[type="file"]',
]
# strength slider: 단일 range input (스크린샷 기준 유일)
SELECTORS_STRENGTH = [
    'input[type="range"]',
]
# Generate 버튼: 텍스트 "Generate" + button 또는 link role
SELECTORS_GENERATE_BTN = [
    'button:has-text("Generate")',
    '[role="button"]:has-text("Generate")',
]
# 결과 이미지: 스크린샷의 "Generated image will appear here" 자리에 들어가는 img
# 좌측 패널의 업로드 미리보기와 구분 필요 — 가장 큰 alt/data-* 또는 main 영역 img
SELECTORS_RESULT_IMG = [
    'main img[src*="blob"]',
    'main img[src*="https://"]',
    '[data-testid*="result"] img',
    'img[alt*="generated" i]',
]


def log(msg: str) -> None:
    print(f"[bot] {msg}", file=sys.stderr, flush=True)


def first_match(page, selectors: list[str], timeout_ms: int = 5000):
    """후보 셀렉터들을 순서대로 시도해서 처음 매칭되는 locator 반환."""
    for sel in selectors:
        loc = page.locator(sel).first
        try:
            loc.wait_for(state="visible", timeout=timeout_ms)
            log(f"  matched selector: {sel!r}")
            return loc
        except Exception:
            log(f"  no match: {sel!r}")
    return None


def first_match_attached(page, selectors: list[str], timeout_ms: int = 5000):
    """visible 보장 안 되는 element(예: hidden file input)용."""
    for sel in selectors:
        loc = page.locator(sel).first
        try:
            loc.wait_for(state="attached", timeout=timeout_ms)
            log(f"  attached selector: {sel!r}")
            return loc
        except Exception:
            log(f"  no attach: {sel!r}")
    return None


def set_strength(page, value: float) -> bool:
    """Strength slider를 value로 설정. React controlled input이라 단순 fill로는 안 먹어서
    네이티브 setter + input/change 이벤트 dispatch 필요."""
    slider = first_match(page, SELECTORS_STRENGTH, timeout_ms=8000)
    if not slider:
        log("strength slider 못 찾음")
        return False
    handle = slider.element_handle()
    if not handle:
        log("slider element_handle 실패")
        return False
    page.evaluate(
        """([el, v]) => {
            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            setter.call(el, String(v));
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }""",
        [handle, value],
    )
    return True


def fetch_image_as_base64(page, src: str) -> str:
    """페이지 컨텍스트에서 이미지 src를 fetch → base64 변환."""
    return page.evaluate(
        """async (url) => {
            const r = await fetch(url);
            const blob = await r.blob();
            const buf = await blob.arrayBuffer();
            let bin = '';
            const bytes = new Uint8Array(buf);
            for (let i = 0; i < bytes.byteLength; i++) bin += String.fromCharCode(bytes[i]);
            return btoa(bin);
        }""",
        src,
    )


def run(image_path: str, strength: float, auth_path: str, output_path: str | None,
        timeout_total_ms: int = 120_000, debug_dir: str | None = None) -> int:
    if not Path(image_path).exists():
        log(f"input image not found: {image_path}")
        return 2
    if not Path(auth_path).exists():
        log(f"auth file not found: {auth_path}")
        log("  → run pixellab_login_export.py on user PC and scp to Mother first")
        return 2

    from playwright.sync_api import sync_playwright

    log(f"launch headless chromium")
    started = time.time()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(storage_state=auth_path)
            page = context.new_page()

            log(f"goto {TOOL_URL}")
            page.goto(TOOL_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)  # SPA hydration 대기
            if debug_dir:
                page.screenshot(path=str(Path(debug_dir) / "01_loaded.png"), full_page=True)

            # 로그인 만료 감지 — signin 페이지로 리디렉트됐는지
            cur = page.url
            if "/signin" in cur or "/login" in cur or "/auth" in cur:
                log(f"세션 만료 또는 로그인 페이지 리디렉트: {cur}")
                log("  → storage_state(auth.json)가 만료됨. 사용자 PC에서 다시 export 후 scp 업로드 필요.")
                if debug_dir:
                    page.screenshot(path=str(Path(debug_dir) / "redirect.png"), full_page=True)
                return 3

            # 1) 파일 업로드
            log("upload file")
            file_input = first_match_attached(page, SELECTORS_FILE_INPUT, timeout_ms=10000)
            if not file_input:
                log("file input 못 찾음")
                if debug_dir:
                    page.screenshot(path=str(Path(debug_dir) / "no_input.png"), full_page=True)
                    Path(debug_dir, "page.html").write_text(page.content(), encoding="utf-8")
                return 4
            file_input.set_input_files(image_path)
            page.wait_for_timeout(2000)  # 업로드 미리보기 등장 대기
            if debug_dir:
                page.screenshot(path=str(Path(debug_dir) / "02_uploaded.png"), full_page=True)

            # 2) strength 설정
            log(f"set strength = {strength}")
            if not set_strength(page, strength):
                log("strength 설정 실패 (default 유지하고 진행)")
            if debug_dir:
                page.screenshot(path=str(Path(debug_dir) / "03_strength_set.png"), full_page=True)

            # 3) 결과 영역 변화 감지 — 단순 카운트가 아니라 src set으로 기록.
            #    PixelLab Gallery는 사용자 계정에 누적되므로 페이지 로드 시 이미 이전 결과들이
            #    DOM에 있음. "새로 등장한 src"만 후보로 잡아야 Gallery 이전 항목을 잘못
            #    추출하지 않는다 (이전에 망가진 일괄 결과의 원인).
            # 또한 input PNG 자체의 base64를 비교 대상으로 두어 단순 업로드 미리보기 제외.
            input_b64_str = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
            initial_data = page.evaluate(
                """() => Array.from(document.querySelectorAll('img')).map(i => ({
                    src: i.src || '',
                    inMain: !!i.closest('main'),
                }))"""
            )
            initial_srcs = set(d["src"] for d in initial_data if d["src"])
            log(f"initial img count (whole page) = {len(initial_srcs)}, in main = {sum(1 for d in initial_data if d['inMain'])}")

            # 4) Generate 클릭
            log("click Generate")
            gen_btn = first_match(page, SELECTORS_GENERATE_BTN, timeout_ms=8000)
            if not gen_btn:
                log("Generate 버튼 못 찾음")
                if debug_dir:
                    page.screenshot(path=str(Path(debug_dir) / "no_gen.png"), full_page=True)
                return 5
            gen_btn.click()
            page.wait_for_timeout(2000)
            if debug_dir:
                page.screenshot(path=str(Path(debug_dir) / "04_generate_clicked.png"), full_page=True)

            # 4.5) Chakra spinner가 사라질 때까지 명시적 대기 (PixelLab 결과 처리 중 표시)
            # 결과는 spinner가 사라진 직후 등장. 우리 첫 polling 실패는 spinner 도중 종료가 원인.
            log("wait for spinner to disappear…")
            spinner_appeared = False
            try:
                page.locator(".chakra-spinner").first.wait_for(state="visible", timeout=8000)
                spinner_appeared = True
                log("  spinner visible — processing")
            except Exception:
                log("  spinner not seen (already done or fast path)")
            if spinner_appeared:
                try:
                    page.locator(".chakra-spinner").first.wait_for(state="hidden", timeout=240_000)
                    log("  spinner hidden — result should be ready")
                except Exception:
                    log("  spinner wait timeout 240s — proceeding anyway")
            page.wait_for_timeout(1500)
            if debug_dir:
                page.screenshot(path=str(Path(debug_dir) / "04b_after_spinner.png"), full_page=True)

            # 5) 결과 이미지 등장 대기 — 페이지 전체에서 새로 등장한 img 중 main 영역 + input과 다른 것만 후보
            log("wait for result image…")
            elapsed = (time.time() - started) * 1000
            remain = max(20_000, timeout_total_ms - int(elapsed))
            deadline = time.time() + remain / 1000
            result_src: str | None = None

            while time.time() < deadline:
                page.wait_for_timeout(2000)
                current = page.evaluate(
                    """() => Array.from(document.querySelectorAll('img')).map(i => ({
                        src: i.src || '',
                        inMain: !!i.closest('main'),
                        w: i.offsetWidth, h: i.offsetHeight,
                        nw: i.naturalWidth, nh: i.naturalHeight,
                    }))"""
                )
                candidates: list[tuple[float, str]] = []
                for d in current:
                    s = d["src"]
                    if not s or s in initial_srcs:
                        continue
                    if not d.get("inMain"):
                        continue  # Gallery(aside) 등 main 밖은 제외
                    # data: URL이면 input과 base64 비교 — 같으면 업로드 미리보기로 간주
                    if s.startswith("data:"):
                        comma = s.find(",")
                        this_b64 = s[comma + 1:] if comma >= 0 else ""
                        if this_b64 == input_b64_str:
                            continue
                    elif not (s.startswith("blob:") or s.startswith("http")):
                        continue
                    area = float((d.get("w") or 0) * (d.get("h") or 0))
                    candidates.append((area, s))
                if candidates:
                    candidates.sort(reverse=True)
                    result_src = candidates[0][1]
                    log(f"result candidate: area={candidates[0][0]:.0f}, src[:80]={result_src[:80]}")
                    break

            if not result_src:
                log("결과 이미지 시간 안에 못 찾음 (새로 등장 + main 안 + input과 다른 src 없음)")
                if debug_dir:
                    page.screenshot(path=str(Path(debug_dir) / "05_no_result.png"), full_page=True)
                    Path(debug_dir, "05_no_result.html").write_text(page.content(), encoding="utf-8")
                return 6
            if debug_dir:
                page.screenshot(path=str(Path(debug_dir) / "05_result_found.png"), full_page=True)

            # 6) base64 추출
            if result_src.startswith("data:"):
                # data URL이면 그대로 split
                b64 = result_src.split(",", 1)[1]
            else:
                log("fetch result image as base64")
                b64 = fetch_image_as_base64(page, result_src)

            log(f"result base64 len = {len(b64):,}")

            # ★ 최종 안전 검증: 결과가 input과 동일 base64이면 추출 실패로 간주.
            #    Correction strength > 0이면 결과는 input과 다를 수밖에 없음. 동일하면 selector 오류.
            if b64 == input_b64_str:
                log("결과 base64가 input과 동일 — 추출 실패로 간주 (selector 오류 가능성)")
                if debug_dir:
                    page.screenshot(path=str(Path(debug_dir) / "05_b64_equals_input.png"), full_page=True)
                return 7

            # 7) 출력
            if output_path:
                Path(output_path).write_bytes(base64.b64decode(b64))
                log(f"saved → {output_path}")
                # JSON 응답 stdout
                print(json.dumps({"ok": True, "output": output_path, "base64_len": len(b64)}))
            else:
                # stdout으로 base64만 출력 (caller가 파싱)
                sys.stdout.write(b64)
                sys.stdout.flush()

            return 0
        finally:
            browser.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True, help="input PNG/JPG path")
    ap.add_argument("--strength", type=float, default=0.1)
    ap.add_argument("--auth", default=DEFAULT_AUTH)
    ap.add_argument("--output", default=None, help="output PNG path. omit → stdout base64")
    ap.add_argument("--timeout", type=int, default=120_000, help="overall timeout ms")
    ap.add_argument("--debug-dir", default=None, help="save screenshots/html on failure")
    args = ap.parse_args()

    if args.debug_dir:
        Path(args.debug_dir).mkdir(parents=True, exist_ok=True)

    return run(
        image_path=args.image,
        strength=max(0.0, min(1.0, args.strength)),
        auth_path=os.path.expanduser(args.auth),
        output_path=args.output,
        timeout_total_ms=args.timeout,
        debug_dir=args.debug_dir,
    )


if __name__ == "__main__":
    sys.exit(main())
