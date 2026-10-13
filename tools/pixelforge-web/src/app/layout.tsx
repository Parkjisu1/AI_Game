import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Nav from "@/components/Nav";
import MobileTabBar, { type TabItem } from "@/components/MobileTabBar";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "PixelForge",
  description: "AI Level Design Tool",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  themeColor: "#000000",
};

// 모바일 하단 탭바 — 4개라 "더보기" 불필요.
const MOBILE_TABS: TabItem[] = [
  { href: "/", label: "홈", icon: "🏠" },
  { href: "/levels", label: "레벨", icon: "📋" },
  { href: "/gallery", label: "갤러리", icon: "🖼" },
  { href: "/json-vault", label: "JSON", icon: "📦" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body className={`${inter.className} bg-gray-50 text-gray-900 min-h-screen`}>
        <Nav />
        {/* 하단 탭바 높이(약 3.5rem)만큼 모바일에서 여백 확보 */}
        <main className="max-w-7xl mx-auto px-4 sm:px-6 py-4 sm:py-6 pb-24 md:pb-6">{children}</main>
        <MobileTabBar tabs={MOBILE_TABS} />
      </body>
    </html>
  );
}
