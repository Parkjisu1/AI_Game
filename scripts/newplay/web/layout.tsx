import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import "./theme-clean.css";
import Nav from "@/components/Nav";
import TopNav from "@/components/TopNav";
import BottomDock from "@/components/BottomDock";
import SideNav from "@/components/SideNav";
import MobileTabBar, { type TabItem } from "@/components/MobileTabBar";
import { auth } from "@/auth";

const inter = Inter({ subsets: ["latin"] });

// 설정 창은 소유자(본인)만 — 다른 계정엔 노출 안 함
const OWNER_EMAILS = new Set(["jisu.park@gameberry.co.kr"]);

export const metadata: Metadata = {
  title: process.env.NEXT_PUBLIC_APP_THEME === "clean" ? "NewPlay Hub" : "ProjectHub",
  description: "OKR · Roadmap · Tasks · Slack",
};

// APP_THEME=clean 인스턴스(비게임 팀)는 라이트 클린 테마 + 게임 메뉴 숨김
const IS_CLEAN = process.env.NEXT_PUBLIC_APP_THEME === "clean";

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  themeColor: IS_CLEAN ? "#131417" : "#0f1115",
};

// 모바일 하단 탭바 — 좌우 탭 + 중앙 FAB(새 작업) + "더보기" 시트.
const MOBILE_TABS: TabItem[] = [
  { href: "/", label: "홈", icon: "home" },
  { href: "/tasks", label: "작업", icon: "tasks" },
  { href: "/agents", label: "AI팀", icon: "cpu" },
];
const GAME_ROUTES = new Set(["/gallery", "/balloonflow", "/simulator", "/levels", "/pixelforge"]);
const MOBILE_MORE: TabItem[] = [
  // 데스크톱 SideNav 에만 넣고 여기를 빼먹으면 모바일에서는 그 화면에 아예 갈 수 없다.
  { href: "/platform", label: "플랫폼 현황", icon: "eye" },
  { href: "/data", label: "데이터", icon: "graph" },
  { href: "/voice", label: "음성 명령", icon: "mic" },
  { href: "/gallery", label: "디자인 갤러리", icon: "image" },
  { href: "/balloonflow", label: "BalloonFlow", icon: "balloon" },
  { href: "/simulator", label: "시뮬레이터", icon: "target" },
  { href: "/roadmap", label: "로드맵", icon: "map" },
  { href: "/levels", label: "레벨", icon: "flag" },
  { href: "/pixelforge", label: "PixelForge", icon: "palette" },
  { href: "/settings", label: "환경 설정", icon: "gear" },
].filter((l) => !IS_CLEAN || !GAME_ROUTES.has(l.href));

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const session = await auth();
  const email = (session?.user?.email || "").toLowerCase();
  const isOwner = OWNER_EMAILS.has(email);
  const userLabel = isOwner ? "Boss" : (email.split("@")[0] || "Member").replace(/^./, (c) => c.toUpperCase());
  const role = isOwner ? "Owner" : "Member";
  // 설정 메뉴 노출: clean(NewPlay) 인스턴스는 로그인한 허용 사용자 전원에게 보인다.
  // 페이지 안의 관리자 전용 구역(허용 사용자·감사 로그)은 API 가 ADMIN_EMAILS 로 따로 가른다.
  // 게임팀 인스턴스는 기존대로 소유자에게만.
  const showSettings = IS_CLEAN ? Boolean(email) : isOwner;
  const moreLinks = showSettings ? MOBILE_MORE : MOBILE_MORE.filter((l) => l.href !== "/settings");
  return (
    <html lang="ko" data-theme={IS_CLEAN ? "clean" : undefined}>
      <body className={`${inter.className} min-h-screen`}>
        {/* clean 인스턴스: 한글 타이포용 Pretendard (Inter는 라틴 전용이라 한글이 시스템 폰트로 떨어짐) */}
        {IS_CLEAN && (
          <link
            rel="stylesheet"
            href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css"
          />
        )}
        {IS_CLEAN ? (
          /* clean 인스턴스: Slack/Flex형 좌측 사이드바 셸 (데스크톱) */
          <SideNav isOwner={isOwner} showSettings={showSettings} email={email} userLabel={userLabel} />
        ) : (
          /* 게임팀: 상단 가로 네비 + 하단 아이콘 독 */
          <>
            <TopNav isOwner={isOwner} userLabel={userLabel} role={role} email={email} />
            <BottomDock isOwner={isOwner} />
          </>
        )}
        {/* 모바일: 상단 Nav + 하단 탭바 (공통) */}
        <Nav isOwner={isOwner} />
        <main className={IS_CLEAN ? "md:pl-60" : "md:pt-14 md:pb-20"}>
          {/* 폭 상한/가운데 정렬 없음 — 넓은 모니터에서 화면을 다 쓰고 좌측 기준으로 정렬된다.
            좌측 사이드바는 상위 <main>의 md:pl-60 이 담당하므로 여기서 다시 밀지 않는다. */}
        <div className="w-full px-4 sm:px-6 md:px-8 py-4 sm:py-6 pb-24 md:pb-6">{children}</div>
        </main>
        <MobileTabBar tabs={MOBILE_TABS} moreLinks={moreLinks} fab={{ href: "/tasks", icon: "plus" }} />
      </body>
    </html>
  );
}
