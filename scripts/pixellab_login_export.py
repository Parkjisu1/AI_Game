"""PixelLab 로그인 세션 1회 export.

Windows에서 1회 실행:
  1) pip install playwright
  2) playwright install chromium
  3) python pixellab_login_export.py
  4) 열린 Chromium에서 PixelLab 로그인 (Google OAuth 등 다 OK)
  5) 콘솔로 돌아와 ENTER 1번 누르기
  6) pixellab_auth.json 생성됨 → Mother로 scp:
     scp pixellab_auth.json aimed@100.77.190.68:~/.hermes/watcher/pixellab_auth.json
"""
from playwright.sync_api import sync_playwright

OUT = "pixellab_auth.json"

print("Chromium을 엽니다. PixelLab에 'Sign in with Google'로 로그인한 뒤 콘솔로 돌아오세요.")
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    # OAuth 흐름을 위해 메인 페이지에서 시작 — /signin로 가면 OAuth redirect가 깨질 수 있음
    page.goto("https://www.pixellab.ai/signin")
    print("\n→ 브라우저에서 'Sign in with Google' 클릭 → Google 로그인 완료")
    print("→ PixelLab 홈/dashboard로 돌아왔으면 이 콘솔에서 ENTER 키를 누르세요...")
    input()
    context.storage_state(path=OUT)
    browser.close()

print(f"\n✓ {OUT} 저장됨.")
print(f"  다음: scp {OUT} aimed@100.77.190.68:~/.hermes/watcher/pixellab_auth.json")
