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
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), interest-cohort=()" },
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      "script-src 'self' 'unsafe-inline' 'unsafe-eval'",  // Next.js 16 hydration 필수
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: blob: https://lh3.googleusercontent.com https://avatars.slack-edge.com",
      "font-src 'self' data:",
      "connect-src 'self' https://accounts.google.com",
      "frame-src 'self' https://accounts.google.com",
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
