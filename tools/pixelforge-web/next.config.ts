import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Mother 이식 후 projecthub-web의 rewrites로 프록시됨.
  // 모든 라우트·에셋이 /pixelforge 프리픽스로 노출됨.
  basePath: "/pixelforge",
  allowedDevOrigins: ["100.77.133.110", "aimed.tailf6f809.ts.net"],
};

export default nextConfig;
