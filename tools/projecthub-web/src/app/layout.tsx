import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Nav from "@/components/Nav";
import TopNav from "@/components/TopNav";
import BottomDock from "@/components/BottomDock";
import MobileTabBar, { type TabItem } from "@/components/MobileTabBar";
import { auth } from "@/auth";

const inter = Inter({ subsets: ["latin"] });

// 설정 창은 소유자(본인)만 — 다른 계정엔 노출 안 함
const OWNER_EMAILS = new Set(["jisu.park@gameberry.co.kr"]);

export const metadata: Metadata = {
  title: "ProjectHub",
  description: "OKR · Roadmap · Tasks · Slack",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  themeColor: "#0f1115",
};

// 모바일 하단 탭바 — 좌우 탭 + 중앙 FAB(새 작업) + "더보기" 시트.
const MOBILE_TABS: TabItem[] = [
  { href: "/", label: "홈", icon: "home" },
  { href: "/tasks", label: "작업", icon: "tasks" },
  { href: "/agents", label: "AI팀", icon: "cpu" },
];
const MOBILE_MORE: TabItem[] = [
  { href: "/voice", label: "음성 명령", icon: "mic" },
  { href: "/gallery", label: "디자인 갤러리", icon: "image" },
  { href: "/balloonflow", label: "BalloonFlow", icon: "balloon" },
  { href: "/roadmap", label: "로드맵", icon: "map" },
  { href: "/levels", label: "레벨", icon: "flag" },
  { href: "/pixelforge", label: "PixelForge", icon: "palette" },
  { href: "/settings", label: "환경 설정", icon: "gear" },
];

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const session = await auth();
  const email = (session?.user?.email || "").toLowerCase();
  const isOwner = OWNER_EMAILS.has(email);
  const userLabel = isOwner ? "Boss" : (email.split("@")[0] || "Member").replace(/^./, (c) => c.toUpperCase());
  const role = isOwner ? "Owner" : "Member";
  const moreLinks = isOwner ? MOBILE_MORE : MOBILE_MORE.filter((l) => l.href !== "/settings");
  return (
    <html lang="ko">
      <body className={`${inter.className} min-h-screen`}>
        {/* 데스크톱: 상단 가로 네비 + 하단 아이콘 독 */}
        <TopNav isOwner={isOwner} userLabel={userLabel} role={role} email={email} />
        <BottomDock isOwner={isOwner} />
        {/* 모바일: 상단 Nav + 하단 탭바 */}
        <Nav isOwner={isOwner} />
        <main className="md:pt-14 md:pb-20">
          <div className="max-w-[1680px] mx-auto px-4 sm:px-6 md:px-8 py-4 sm:py-6 pb-24 md:pb-6">{children}</div>
        </main>
        <MobileTabBar tabs={MOBILE_TABS} moreLinks={moreLinks} fab={{ href: "/tasks", icon: "plus" }} />
      </body>
    </html>
  );
}
