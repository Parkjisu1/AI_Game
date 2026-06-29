#!/usr/bin/env python3
"""PixelLab 1회 로그인 → storage_state.json 저장 (Mother SSH에서 실행).

사용법 (Mother에 SSH 접속 후):
  ~/.hermes/watcher/venv/bin/python ~/.hermes/watcher/setup_pixellab_login.py

이메일/비밀번호는 stdin → 메모리에만 사용 → 즉시 폐기. 디스크 저장 X.
성공 시 ~/.hermes/watcher/pixellab_auth.json (chmod 600) 생성.

전제: PixelLab 계정이 이메일+비밀번호 로그인 지원.
Google OAuth-only 계정이면 이 스크립트로 자동 로그인 불가 — 대신 사용자 PC에서
playwright codegen으로 storage_state.json을 만들어 scp 업로드해야 함.
"""
import getpass
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path.home() / ".hermes" / "watcher" / "pixellab_auth.json"
LOGIN_URL = "https://www.pixellab.ai/signin"
TIMEOUT_MS = 20_000

print("PixelLab 로그인 (이메일/비밀번호는 메모리에서만 사용, 디스크 저장 안 함)")
email = input("Email: ").strip()
password = getpass.getpass("Password (입력 표시 안 됨): ")
if not email or not password:
    print("입력 비었음. 종료.", file=sys.stderr)
    sys.exit(2)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    try:
        context = browser.new_context()
        page = context.new_page()
        print(f"[1/4] goto {LOGIN_URL}")
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # 이메일/비밀번호 입력
        print("[2/4] fill credentials")
        try:
            page.locator('input[type="email"], input[name="email"]').first.fill(email, timeout=TIMEOUT_MS)
            page.locator('input[type="password"]').first.fill(password, timeout=TIMEOUT_MS)
        except Exception as e:
            print(f"  ✗ 로그인 필드 못 찾음: {e}", file=sys.stderr)
            try:
                page.screenshot(path="/tmp/pixellab_login_form_fail.png", full_page=True)
                print(f"  → 스크린샷: /tmp/pixellab_login_form_fail.png", file=sys.stderr)
            except Exception:
                pass
            sys.exit(3)

        # 즉시 패스워드 변수 폐기
        password = "x" * 32
        del password

        # 제출 버튼 클릭 — form 안의 submit 버튼만. 헤더의 Sign in nav나 OAuth Google 버튼 제외.
        print("[3/4] submit")
        try:
            # 우선순위 1: form 안의 submit type 버튼
            submit = page.locator('form button[type="submit"]').first
            if submit.count() > 0:
                submit.click(timeout=TIMEOUT_MS)
            else:
                # 폴백: 텍스트 "Sign in"인데 Google이 안 붙은 버튼
                page.locator('button:has-text("Sign in"):not(:has-text("Google"))').last.click(timeout=TIMEOUT_MS)
        except Exception as e:
            print(f"  ✗ 제출 버튼 못 찾음: {e}", file=sys.stderr)
            sys.exit(4)

        # 로그인 성공 — login/signin 페이지 아닌 URL로 변경 대기
        print("[4/4] wait for redirect after login")
        try:
            page.wait_for_function(
                "() => !location.pathname.includes('/login') && !location.pathname.includes('/signin') && !location.pathname.includes('/auth')",
                timeout=20_000,
            )
            print(f"  ✓ logged in — current URL: {page.url}")
        except Exception:
            print(f"  ✗ 로그인 후 redirect 못 잡음. current URL: {page.url}", file=sys.stderr)
            print("    가능한 원인: 비밀번호 오류 / 2FA / CAPTCHA / OAuth-only 계정", file=sys.stderr)
            try:
                page.screenshot(path="/tmp/pixellab_login_after_fail.png", full_page=True)
                print(f"    → 스크린샷: /tmp/pixellab_login_after_fail.png", file=sys.stderr)
            except Exception:
                pass
            sys.exit(5)

        # storage_state 저장
        OUT.parent.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(OUT))
        OUT.chmod(0o600)
        print(f"\n✓ {OUT} 저장됨 (chmod 600)")
        print("  다음: PixelForge 갤러리에서 🩹 Correction 버튼 테스트")
    finally:
        browser.close()
