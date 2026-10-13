import type { NextConfig } from "next";

// 표준 보안 헤더 — 모든 응답에 적용.
// HSTS: 1년 (Tailscale Funnel은 항상 HTTPS이므로 안전)
// CSP: ProjectHub UI는 self + Google OAuth iframe + Slack 이미지만 사용. unsafe-inline은 Next.js 16 dev/prod 호환을 위해 한정 허용.
// X-Frame-Options DENY: clickjacking 차단 (NextAuth iframe도 외부 호스팅 안 하므로 안전)
const SECURITY_HEADERS = [
  { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains; preload" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  // microphone=(self): /voice 녹음·실시간 대화에 필수 (전면 차단이면 getUserMedia가 거부됨)
  { key: "Permissions-Policy", value: "camera=(), microphone=(self), geolocation=(), interest-cohort=()" },
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      "script-src 'self' 'unsafe-inline' 'unsafe-eval'",  // Next.js 16 hydration 필수
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: blob: https://lh3.googleusercontent.com https://avatars.slack-edge.com",
      "font-src 'self' data:",
      "connect-src 'self' https://accounts.google.com https://api.openai.com",  // api.openai.com: Realtime 음성 SDP
      "frame-src 'self' https://accounts.google.com",
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "form-action 'self' https://accounts.google.com",
    ].join("; "),
  },
];

// 플레이어블 미리보기(/playable/*)만 예외 — 광고를 iframe 안에서 실제 크기로 봐야 하는데
// 전역 정책이 frame-ancestors 'none' + X-Frame-Options DENY 라 <b>같은 출처에서도</b> 막힌다
// (브라우저가 "refused to connect" 로 표시한다).
//
// 완화 폭은 <b>동일 출처뿐</b>이다 — 외부 사이트는 여전히 이 페이지를 감쌀 수 없다.
// 나머지 지시문(script-src·connect-src 등)은 손대지 않는다. 유니티 WebGL 은
// 'unsafe-eval'(wasm)과 connect-src 'self'(자기 data/wasm 로드)를 이미 만족한다.
const PLAYABLE_HEADERS = SECURITY_HEADERS.map((h) => {
  if (h.key === "X-Frame-Options") return { ...h, value: "SAMEORIGIN" };
  if (h.key === "Content-Security-Policy") {
    return {
      ...h,
      value: h.value
        .replace("frame-ancestors 'none'", "frame-ancestors 'self'")
        // 유니티 WebGL 은 압축된 프레임워크를 <b>JS 로 풀어</b> blob: URL 로 만든 뒤
        // script 엘리먼트로 실행한다(빌드가 Decompression Fallback 을 켜 둔 탓).
        // blob: 이 없으면 그 script 가 CSP 에 막혀 unityFramework 가 정의되지 않고,
        // 화면은 로딩 바에서 멈춘 채 <b>게임만 안 보인다</b>.
        .replace("script-src 'self'", "script-src 'self' blob:")
        // 워커/자식 컨텍스트도 같은 이유로 blob: 이 필요할 수 있다.
        .replace("default-src 'self'", "default-src 'self' blob:"),
    };
  }
  return h;
});

const nextConfig: NextConfig = {
  // Tailscale로 다른 PC/폰에서 접근할 때 Next.js 16이 cross-origin 리소스를 차단하는 문제 해결.
  // 자리 PC의 Tailscale IP 및 LAN IP를 허용.
  allowedDevOrigins: ["100.77.133.110", "172.31.29.241"],

  experimental: {
    // ⚠️ /voice 녹음 업로드의 실제 상한은 여기다 (2026-07-27 실측 원인규명).
    // Next.js 16은 proxy.ts로 넘길 body를 클론할 때 기본 10MB에서 스트림을 끊는다
    // (node_modules/next/dist/server/config-shared.js: proxyClientMaxBodySize = 10485760).
    // /api/voice는 proxy 매처에 포함되므로 10MB를 넘는 녹음은 multipart가 중간에 잘려
    // 라우트의 req.formData()가 "Failed to parse body as FormData"로 던지고 400이 된다.
    // 실측 실패 2건: content-length 31,426,453 / 13,001,836 — 후자는 라우트 가드(25MB)
    // 안쪽인데도 죽었다. 즉 25MB 가드와 48kbps 비트레이트 튜닝이 전부 무력화돼 있었다.
    // 라우트 가드 STT_MAX_BYTES(25,000,000)보다 크게 잡아야 "25MB 초과" 안내가 제대로 뜬다.
    // 3D source upload: route caps individual files at 100 MiB, plus multipart overhead.
    proxyClientMaxBodySize: 110 * 1024 * 1024,
  },

  async headers() {
    return [
      // 모든 경로에 보안 헤더 일괄 적용
      { source: "/:path*", headers: SECURITY_HEADERS },
      // 플레이어블 미리보기만 <b>동일 출처</b> iframe 허용.
      // 더 구체적인 규칙이 뒤에 와야 같은 키를 덮어쓴다.
      { source: "/playable/:path*", headers: PLAYABLE_HEADERS },
      // GLB embedded textures are fetched as local blob URLs by model-viewer.
      { source: "/asset-studio/:path*", headers: SECURITY_HEADERS.map(h => h.key === "Content-Security-Policy"
        ? { ...h, value: h.value.replace("connect-src 'self'", "connect-src 'self' blob:") } : h) },
    ];
  },

  // PixelForge를 /pixelforge 서브패스로 프록시 (Mother 127.0.0.1:3002)
  // 클라이언트 요청은 모두 projecthub-web의 proxy.ts 인증 게이트 거친 후 전달됨
  async rewrites() {
    return [
      { source: "/pixelforge", destination: "http://127.0.0.1:3002/pixelforge" },
      { source: "/pixelforge/:path*", destination: "http://127.0.0.1:3002/pixelforge/:path*" },
    ];
  },
};

export default nextConfig;
