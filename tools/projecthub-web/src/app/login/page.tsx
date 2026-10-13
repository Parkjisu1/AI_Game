import { redirect } from "next/navigation";
import { auth, signIn } from "@/auth";

// 커스텀 로그인 페이지 — clean 인스턴스(APP_THEME=clean)의 signIn 페이지.
// (게임팀 인스턴스는 Auth.js 기본 페이지를 그대로 사용 — auth.ts pages 분기 참조)
const APP_NAME = process.env.NEXT_PUBLIC_APP_THEME === "clean" ? "NewPlay Hub" : "ProjectHub";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ callbackUrl?: string }>;
}) {
  const session = await auth();
  if (session?.user?.email) redirect("/");
  const { callbackUrl } = await searchParams;
  const redirectTo = callbackUrl && callbackUrl.startsWith("/") ? callbackUrl : "/";

  return (
    <div className="min-h-[80vh] flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="glass p-8 text-center">
          <div className="mx-auto mb-5 w-12 h-12 rounded-xl bg-blue-600 flex items-center justify-center">
            <span className="text-white text-xl font-bold">N</span>
          </div>
          <h1 className="text-xl font-bold text-gray-900 mb-1">{APP_NAME}</h1>
          <p className="text-sm text-gray-500 mb-7">팀 계정으로 로그인하세요</p>

          <form
            action={async () => {
              "use server";
              await signIn("google", { redirectTo });
            }}
          >
            <button
              type="submit"
              className="w-full flex items-center justify-center gap-3 rounded-xl border border-gray-300 bg-white px-4 py-3 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden>
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
              </svg>
              Google로 계속하기
            </button>
          </form>
        </div>
        <p className="mt-4 text-center text-xs text-gray-400">
          허용된 팀 계정만 접근할 수 있습니다
        </p>
      </div>
    </div>
  );
}
