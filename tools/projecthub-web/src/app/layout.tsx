import type { Metadata, Viewport } from "next";
import { Inter, Fraunces, DM_Sans, Geist_Mono } from "next/font/google";
import "./globals.css";
import "./theme-instrument.css";
import "./theme-paper.css";
import "./paper-components.css";
import Nav from "@/components/Nav";
import TopNav from "@/components/TopNav";
import BottomDock from "@/components/BottomDock";
import MobileTabBar, { type TabItem } from "@/components/MobileTabBar";
import InstrumentNav from "@/components/InstrumentNav";
import Rail from "@/components/paper/Rail";
import { auth } from "@/auth";

const inter = Inter({ subsets: ["latin"] });

// paper 테마 서체 3종. next/font 는 빌드 시 **자체 호스팅**하므로 CSP 를 건드릴 필요가 없다
// (Pretendard 는 CDN 이라 style-src/font-src 에 jsdelivr 를 열어 둔 상태).
// 역할이 셋 다 다르다: 디스플레이(세리프) / 본문(산세) / 수치(모노).
const displayFont = Fraunces({
  subsets: ["latin"], weight: ["400", "600", "700"],
  variable: "--font-display", display: "swap",
});
const uiFont = DM_Sans({
  subsets: ["latin"], weight: ["400", "500", "700"],
  variable: "--font-ui", display: "swap",
});
const monoFont = Geist_Mono({
  subsets: ["latin"], weight: ["400", "500"],
  variable: "--font-mono-ph", display: "swap",
});

// 설정 창은 소유자(본인)만 — 다른 계정엔 노출 안 함
const OWNER_EMAILS = new Set(["jisu.park@gameberry.co.kr"]);

export const metadata: Metadata = {
  title: "ProjectHub",
  description: "OKR · Roadmap · Tasks · Slack",
};

// APP_THEME=instrument — 계기판 테마. env 가 없으면 이 분기는 전부 기존 동작 그대로다.
// 되돌리려면 .env.production 에서 NEXT_PUBLIC_APP_THEME 을 지우고 재빌드하면 끝.
const APP_THEME = process.env.NEXT_PUBLIC_APP_THEME || "";
const IS_INSTRUMENT = APP_THEME === "instrument";
// APP_THEME=paper — 종이 테마. 되돌리려면 .env.production 에서 값을 바꾸고 재빌드하면 끝.
const IS_PAPER = APP_THEME === "paper";

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  themeColor: IS_PAPER ? "#fbf9f5" : "#0f1115",
};

// 모바일 하단 탭바 — 좌우 탭 + 중앙 FAB(새 작업) + "더보기" 시트.
const MOBILE_TABS: TabItem[] = [
  { href: "/", label: "홈", icon: "home" },
  { href: "/tasks", label: "작업", icon: "tasks" },
  { href: "/agents", label: "AI팀", icon: "cpu" },
];
const MOBILE_MORE: TabItem[] = [
  { href: "/research/supercent", label: "게임 성장 연구", icon: "search" },
  { href: "/voice", label: "음성 명령", icon: "mic" },
  { href: "/gallery", label: "디자인 갤러리", icon: "image" },
  { href: "/assets-3d", label: "3D 제작실", icon: "image" },
  { href: "/balloonflow", label: "BalloonFlow", icon: "balloon" },
  { href: "/simulator", label: "시뮬레이터", icon: "target" },
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
    /* 폰트 변수는 **html 에** 둔다 — 테마 토큰(--pp-*)이 html[data-theme] 스코프에서
       var(--font-display) 를 읽어야 하는데, body 에 두면 위로 상속되지 않아 빈 값이 된다. */
    <html
      lang="ko"
      data-theme={IS_INSTRUMENT ? "instrument" : IS_PAPER ? "paper" : undefined}
      className={IS_PAPER ? `${displayFont.variable} ${uiFont.variable} ${monoFont.variable}` : undefined}
    >
      <body className={IS_PAPER ? "min-h-screen" : `${inter.className} min-h-screen`}>
        {/* 계기판·종이 테마는 한글 타이포용 Pretendard 를 로드 (Inter/DM Sans 는 라틴 전용) */}
        {(IS_INSTRUMENT || IS_PAPER) && (
          <link
            rel="stylesheet"
            href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css"
          />
        )}
        {IS_INSTRUMENT ? (
          /* 계기판: 상태 스트립 + 그룹 탭 + 하위 탭 2단 */
          <InstrumentNav isOwner={isOwner} userLabel={userLabel} email={email} />
        ) : IS_PAPER ? (
          /* 종이: 좌측 레일 하나. 예전엔 상단 탭 9개 + 하단 독 7개 + 모바일 탭바로
             이동 수단이 셋이었는데, 정작 "지금 어디" 를 말하는 건 없었다. */
          <Rail isOwner={isOwner} userLabel={userLabel} role={role} />
        ) : (
          /* 기존: 상단 가로 네비 + 하단 아이콘 독 */
          <>
            <TopNav isOwner={isOwner} userLabel={userLabel} role={role} email={email} />
            <BottomDock isOwner={isOwner} />
          </>
        )}
        {/* 모바일: 상단 Nav + 하단 탭바 */}
        <Nav isOwner={isOwner} />
        <main className={IS_INSTRUMENT ? "instr-main" : "md:pt-14 md:pb-20"}>
          <div className="max-w-[1680px] mx-auto px-4 sm:px-6 md:px-8 py-4 sm:py-6 pb-24 md:pb-6">{children}</div>
        </main>
        <MobileTabBar tabs={MOBILE_TABS} moreLinks={moreLinks} fab={{ href: "/tasks", icon: "plus" }} />
      </body>
    </html>
  );
}
