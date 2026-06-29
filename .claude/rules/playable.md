---
description: Playable ad rules for playable HTML output
globs: projects/*/output/playable.html
---

# Playable Ad Rules (HTML5)

## SINGLE FILE
- Everything in ONE `.html` file (no external files)
- CSS inline or in `<style>` tag
- JS inline or in `<script>` tag
- Assets: Base64 inline or Canvas-drawn shapes

## SIZE LIMITS
| Network | Max Size | Max Duration |
|---------|----------|-------------|
| Facebook/Meta | 2MB | unlimited |
| Google Ads | 5MB | 60s |
| IronSource | 5MB | 30s |
| AppLovin | 5MB | 30s |

## REQUIRED ELEMENTS
- Touch AND mouse event handlers (dual input)
- CTA button (Install/Download/Play Now)
- CTA URL placeholder: `window.open(CTA_URL)` or `mraid.open(CTA_URL)`
- CTA trigger: visible after gameplay OR timer OR interaction count
- Viewport meta tag for mobile scaling
- `<!DOCTYPE html>` declaration

## FORBIDDEN
- External HTTP requests (fetch, XMLHttpRequest, CDN links, external images)
- `<img src="http...">` or `<link href="http...">`
- `<script src="http...">`
- localStorage/sessionStorage (sandboxed environment)
- alert/confirm/prompt dialogs
- window.open except for CTA

## PERFORMANCE
- requestAnimationFrame for game loop (not setInterval)
- Object pooling for particles/projectiles
- Canvas 2D preferred over WebGL for compatibility
- Limit DOM elements (prefer Canvas rendering)

## SUPPORTED MECHANICS
pin_pull, match3, merge, choice, runner

## TESTING CHECKLIST
1. Isolation: zero external requests
2. Interaction: touch + mouse both work
3. CTA: button visible + URL functional
4. Size: under target network limit
