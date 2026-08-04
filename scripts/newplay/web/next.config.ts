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
      // newplay.store: /platform "앱 화면" 탭에서 실제 서비스를 미리보기로 띄운다.
      // 우리 앱이 프레임에 담기는 것은 여전히 금지(frame-ancestors none / X-Frame-Options DENY)라
      // clickjacking 방어는 그대로다 — 여기는 우리가 담는 대상의 허용 목록이다.
      "frame-src 'self' https://accounts.google.com https://newplay.store",
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "form-action 'self' https://accounts.google.com",
    ].join("; "),
  },
];

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
    proxyClientMaxBodySize: 30 * 1024 * 1024,
  },

  async headers() {
    return [
      // 모든 경로에 보안 헤더 일괄 적용
      { source: "/:path*", headers: SECURITY_HEADERS },
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
